"""Tool schemas for the AI and their executor.

Dispatching re-reads authoritative data from the DB on every call - the model's
arguments (prices, stock) are never trusted; totals are always recomputed.
"""
import json
import logging
from typing import Any

from sqlalchemy import or_, select

from app.ai.prompt import format_naira
from app.models import Business, CatalogItem, Conversation, Order
from app.models.enums import ORDER_STATUS_PENDING

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

create_order_schema = {
    "name": "create_order",
    "description": (
        "Save an order for this business. Only call AFTER the customer explicitly "
        "confirmed the full summary and total you showed them."
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

TOOLS = [search_catalog_schema, check_availability_schema, create_order_schema]


async def dispatch(
    session,
    business: Business,
    conversation: Conversation,
    name: str,
    args: dict[str, Any],
) -> str:
    if name == "search_catalog":
        result = await _search_catalog(session, business.id, args)
    elif name == "check_availability":
        result = await _check_availability(session, business.id, args)
    elif name == "create_order":
        result = await _create_order(
            session, business.id, conversation, args
        )
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


async def _create_order(
    session, business_id: str, conversation: Conversation, args: dict[str, Any]
) -> dict:
    items_arg = args.get("items") or []
    if not items_arg:
        return {"ok": False, "errors": ["No items were provided."]}

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

    if errors:
        return {"ok": False, "errors": errors}
    if not ordered:
        return {"ok": False, "errors": ["No valid items to order."]}

    order = Order(
        business_id=business_id,
        conversation_id=conversation.id,
        customer_phone=conversation.customer_phone,
        customer_name=(args.get("customer_name") or "").strip() or None,
        delivery_address=(args.get("delivery_address") or "").strip() or None,
        items=ordered,
        total_kobo=total_kobo,
        status=ORDER_STATUS_PENDING,
    )
    session.add(order)
    await session.flush()
    logger.info("created order %s for business %s (%s)", order.id, business_id, order.customer_phone)
    return {
        "ok": True,
        "order_id": order.id,
        "status": ORDER_STATUS_PENDING,
        "total": format_naira(total_kobo),
        "total_kobo": total_kobo,
        "items": [
            {"name": o["name"], "quantity": o["quantity"]} for o in ordered
        ],
    }