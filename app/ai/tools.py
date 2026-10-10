"""Tool schemas for the AI and their executor.

Dispatching re-reads authoritative data from the DB on every call - the model's
arguments (prices, stock) are never trusted; totals are always recomputed.

Ordering is two-phase:
  * propose_order validates stock/prices and saves a DRAFT (with the
    server-computed total) for the bot to show the customer;
  * create_order(draft_id) only places the order once the customer has sent a
    NEW message after the draft was proposed (the confirmation turn).
"""
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from app.ai import booking_tools
from app.ai.prompt import format_naira
from app.config import settings
from app.models import Business, CatalogItem, Conversation, Message, Order, OrderDraft
from app.models.enums import (
    DRAFT_STATUS_ACTIVE,
    DRAFT_STATUS_EXPIRED,
    DRAFT_STATUS_PLACED,
    DRAFT_STATUS_SUPERSEDED,
    MESSAGE_ROLE_CUSTOMER,
    ORDER_STATUS_PENDING,
)

logger = logging.getLogger("chibot.tools")

MAX_SEARCH_RESULTS = 50

search_catalog_schema = {
    "name": "search_catalog",
    "description": (
        "Search this business's catalog for products. Returns matching items with "
        "their real prices, units and stock. Always call this before quoting a price "
        "or taking an order."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional search term (product name or keyword).",
            }
        },
    },
}

check_availability_schema = {
    "name": "check_availability",
    "description": (
        "Check whether an item is available and, if a quantity is given, whether "
        "that quantity is in stock."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "Catalog item id from search_catalog."},
            "name": {"type": "string", "description": "Item name if you do not have the id."},
            "quantity": {"type": "integer", "description": "How many the customer wants."},
        },
    },
}

propose_order_schema = {
    "name": "propose_order",
    "description": (
        "Validate the customer's items/quantities against real stock and prices and "
        "save a DRAFT order. Returns a draft_id and the server-computed total for you "
        "to show the customer. This does NOT place the order - the customer must "
        "confirm it first. If the customer changes anything, call this again with the "
        "new details (it replaces the previous draft)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string", "description": "Catalog item id from search_catalog."},
                        "quantity": {"type": "integer", "minimum": 1},
                    },
                    "required": ["item_id", "quantity"],
                },
                "description": "The items the customer wants to order.",
            },
            "customer_name": {"type": "string", "description": "Customer's name."},
            "delivery_address": {"type": "string", "description": "Delivery address."},
        },
        "required": ["items"],
    },
}

create_order_schema = {
    "name": "create_order",
    "description": (
        "Place an order for a draft you already proposed. Call this ONLY after the "
        "customer has explicitly confirmed the summary in a NEW message (after you "
        "proposed the draft). Pass the draft_id returned by propose_order. If you "
        "call it too early the order is refused - ask the customer to confirm."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "draft_id": {
                "type": "string",
                "description": "The draft_id returned by propose_order.",
            },
        },
        "required": ["draft_id"],
    },
}

TOOLS = [
    search_catalog_schema,
    check_availability_schema,
    propose_order_schema,
    create_order_schema,
    *booking_tools.TOOLS,
]


async def dispatch(
    session,
    business: Business,
    conversation: Conversation,
    name: str,
    args: dict[str, Any],
) -> str:
    booking_result = await booking_tools.handle(
        session, business, conversation, name, args
    )
    if booking_result is not None:
        return json.dumps(booking_result, ensure_ascii=False)
    if name == "search_catalog":
        result = await _search_catalog(session, business.id, args)
    elif name == "check_availability":
        result = await _check_availability(session, business.id, args)
    elif name == "propose_order":
        result = await _propose_order(session, business.id, conversation, args)
    elif name == "create_order":
        result = await _create_order(session, business.id, conversation, args)
    else:
        result = {"error": f"Unknown tool: {name}"}
    return json.dumps(result, ensure_ascii=False)


async def _search_catalog(
    session, business_id: str, args: dict[str, Any]
) -> dict:
    query = (args.get("query") or "").strip().lower()
    stmt = select(CatalogItem).where(
        CatalogItem.business_id == business_id, CatalogItem.available.is_(True)
    )
    if query:
        stmt = stmt.where(
            or_(
                CatalogItem.name.ilike(f"%{query}%"),
                CatalogItem.description.ilike(f"%{query}%"),
            )
        )
    rows = list(
        (await session.execute(stmt.order_by(CatalogItem.name))).scalars()
    )[:MAX_SEARCH_RESULTS]
    results = [
        {
            "item_id": item.id,
            "name": item.name,
            "price": format_naira(item.price_kobo),
            "unit": item.unit,
            "stock_qty": item.stock_qty if item.stock_qty is not None else "unlimited",
        }
        for item in rows
    ]
    if not results:
        return {"results": [], "note": "No matching items found in the catalog."}
    return {"results": results}


async def _check_availability(
    session, business_id: str, args: dict[str, Any]
) -> dict:
    item = await _find_item(session, business_id, args)
    if item is None:
        return {
            "available": False,
            "message": "We don't seem to have that item.",
        }
    quantity = int(args.get("quantity") or 1)
    available = item.available and (
        item.stock_qty is None or item.stock_qty >= quantity
    )
    return {
        "available": available,
        "item": item.name,
        "price": format_naira(item.price_kobo),
        "stock_qty": item.stock_qty if item.stock_qty is not None else "unlimited",
        "sufficient_for": quantity,
    }


async def _find_item(session, business_id: str, args: dict[str, Any]):
    item_id = args.get("item_id")
    if item_id:
        return (
            await session.execute(
                select(CatalogItem).where(
                    CatalogItem.id == item_id,
                    CatalogItem.business_id == business_id,
                )
            )
        ).scalar_one_or_none()
    name = (args.get("name") or "").strip()
    if name:
        return (
            await session.execute(
                select(CatalogItem).where(
                    CatalogItem.business_id == business_id,
                    CatalogItem.name.ilike(f"%{name}%"),
                )
            )
        ).scalars().first()
    return None


async def _validate_items(
    session, business_id: str, items_arg: list[dict]
) -> tuple[list[dict], int, list[str]]:
    """Validate requested items against the live catalog.

    Returns (ordered_items, total_kobo, errors). Prices and totals are always
    recomputed from the DB, never taken from the model.
    """
    ordered: list[dict] = []
    total_kobo = 0
    errors: list[str] = []
    for entry in items_arg:
        item = await session.get(CatalogItem, entry.get("item_id"))
        if item is None or item.business_id != business_id:
            errors.append(f"Item {entry.get('item_id')!r} was not found in this catalog.")
            continue
        try:
            quantity = int(entry.get("quantity") or 0)
        except (TypeError, ValueError):
            quantity = 0
        if quantity <= 0:
            errors.append(f"Quantity for {item.name} must be at least 1.")
            continue
        if not item.available:
            errors.append(f"{item.name} is not available right now.")
            continue
        if item.stock_qty is not None and quantity > item.stock_qty:
            errors.append(f"Only {item.stock_qty} of {item.name} are in stock.")
            continue
        total_kobo += item.price_kobo * quantity
        ordered.append(
            {
                "item_id": item.id,
                "name": item.name,
                "quantity": quantity,
                "unit_price_kobo": item.price_kobo,
            }
        )
    return ordered, total_kobo, errors


def _summarise(ordered: list[dict]) -> list[dict]:
    return [{"name": o["name"], "quantity": o["quantity"]} for o in ordered]


async def _propose_order(
    session, business_id: str, conversation: Conversation, args: dict[str, Any]
) -> dict:
    items_arg = args.get("items") or []
    if not items_arg:
        return {"ok": False, "errors": ["No items were provided."]}

    ordered, total_kobo, errors = await _validate_items(session, business_id, items_arg)
    if errors:
        return {"ok": False, "errors": errors}
    if not ordered:
        return {"ok": False, "errors": ["No valid items to order."]}

    # A new proposal replaces any earlier unconfirmed draft for this chat.
    existing = (
        await session.execute(
            select(OrderDraft).where(
                OrderDraft.conversation_id == conversation.id,
                OrderDraft.status == DRAFT_STATUS_ACTIVE,
            )
        )
    ).scalars().all()
    for row in existing:
        row.status = DRAFT_STATUS_SUPERSEDED

    # Remember where the conversation was so a NEW customer message is required
    # before the order can be placed.
    last_customer_seq = (
        await session.execute(
            select(func.max(Message.seq)).where(
                Message.conversation_id == conversation.id,
                Message.role == MESSAGE_ROLE_CUSTOMER,
            )
        )
    ).scalar_one() or 0

    draft = OrderDraft(
        business_id=business_id,
        conversation_id=conversation.id,
        customer_phone=conversation.customer_phone,
        customer_name=(args.get("customer_name") or "").strip() or None,
        delivery_address=(args.get("delivery_address") or "").strip() or None,
        items=ordered,
        total_kobo=total_kobo,
        proposed_at_seq=last_customer_seq,
        status=DRAFT_STATUS_ACTIVE,
        expires_at=datetime.now(UTC)
        + timedelta(minutes=settings.order_draft_ttl_minutes),
    )
    session.add(draft)
    await session.flush()
    logger.info(
        "proposed order draft %s for business %s (%s)",
        draft.id,
        business_id,
        draft.customer_phone,
    )
    return {
        "ok": True,
        "draft_id": draft.id,
        "status": "awaiting_confirmation",
        "total": format_naira(total_kobo),
        "total_kobo": total_kobo,
        "items": _summarise(ordered),
        "expires_in_minutes": settings.order_draft_ttl_minutes,
        "note": (
            "Show this summary and total to the customer and ask them to confirm. "
            "Only call create_order after they reply to confirm."
        ),
    }


async def _create_order(
    session, business_id: str, conversation: Conversation, args: dict[str, Any]
) -> dict:
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return {
            "ok": False,
            "errors": ["A draft_id is required. Call propose_order first."],
        }

    draft = await session.get(OrderDraft, draft_id)
    if draft is None:
        return {"ok": False, "errors": ["No draft with that id. Propose the order again."]}
    if draft.business_id != business_id or draft.customer_phone != conversation.customer_phone:
        return {
            "ok": False,
            "errors": ["That draft does not belong to this customer."],
        }
    if draft.status != DRAFT_STATUS_ACTIVE:
        return {
            "ok": False,
            "errors": [
                ("That draft is no longer valid. Propose the order again and ask the "
                "customer to confirm.")
            ],
        }
    if draft.expires_at <= datetime.now(UTC):
        draft.status = DRAFT_STATUS_EXPIRED
        return {
            "ok": False,
            "errors": ["That draft has expired. Propose the order again."],
        }

    confirmed = (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == draft.conversation_id,
                Message.role == MESSAGE_ROLE_CUSTOMER,
                Message.seq > draft.proposed_at_seq,
            )
        )
    ).scalar_one()
    if not confirmed:
        return {
            "ok": False,
            "errors": [
                ("The customer has not confirmed this draft yet. Show them the summary "
                "and total again and ask them to reply to confirm before placing the order.")
            ],
        }

    order = Order(
        business_id=draft.business_id,
        conversation_id=draft.conversation_id,
        customer_phone=draft.customer_phone,
        customer_name=draft.customer_name,
        delivery_address=draft.delivery_address,
        items=draft.items,
        total_kobo=draft.total_kobo,
        status=ORDER_STATUS_PENDING,
    )
    session.add(order)
    draft.status = DRAFT_STATUS_PLACED
    await session.flush()
    logger.info(
        "placed order %s from draft %s for business %s (%s)",
        order.id,
        draft.id,
        business_id,
        order.customer_phone,
    )
    return {
        "ok": True,
        "order_id": order.id,
        "draft_id": draft.id,
        "status": ORDER_STATUS_PENDING,
        "total": format_naira(draft.total_kobo),
        "total_kobo": draft.total_kobo,
        "items": _summarise(draft.items),
    }
