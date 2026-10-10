import json

from sqlalchemy import select

from app.ai import tools
from app.db import SessionLocal
from app.models import Business, Conversation, Order
from app.models.enums import ORDER_STATUS_PENDING


async def dispatch(session, tenant, name, args):
    business = await session.get(Business, tenant["business_id"])
    convo_id = tenant.get("conversation_id")
    if convo_id is not None:
        conversation = await session.get(Conversation, convo_id)
    else:
        conversation = Conversation(
            business_id=business.id, customer_phone="2340000000000"
        )
        session.add(conversation)
        await session.flush()
    raw = await tools.dispatch(session, business, conversation, name, args)
    return json.loads(raw)


async def test_search_catalog_returns_all(tenant):
    async with SessionLocal() as session:
        result = await dispatch(session, tenant, "search_catalog", {})
        names = {r["name"] for r in result["results"]}
        assert {"Kunu Drink", "Jollof Rice"} <= names
        assert "Old Stock" not in names  # unavailable items hidden


async def test_search_catalog_filters_by_query(tenant):
    async with SessionLocal() as session:
        result = await dispatch(session, tenant, "search_catalog", {"query": "jollof"})
        names = [r["name"] for r in result["results"]]
        assert names == ["Jollof Rice"]


async def test_check_availability_sufficient(tenant):
    async with SessionLocal() as session:
        result = await dispatch(
            session, tenant, "check_availability",
            {"item_id": tenant["kunu"], "quantity": 3},
        )
        assert result["available"] is True
        assert result["price"] == "NGN 1,000"


async def test_check_availability_insufficient(tenant):
    async with SessionLocal() as session:
        result = await dispatch(
            session, tenant, "check_availability",
            {"item_id": tenant["kunu"], "quantity": 9},
        )
        assert result["available"] is False


async def test_check_availability_unknown_item(tenant):
    async with SessionLocal() as session:
        result = await dispatch(
            session, tenant, "check_availability", {"name": "nothing"}
        )
        assert result["available"] is False


async def test_create_order_computes_total_from_db(tenant):
    async with SessionLocal() as session:
        from app.models import Message
        from app.models.enums import MESSAGE_ROLE_CUSTOMER

        pr = await dispatch(
            session,
            tenant,
            "propose_order",
            {
                "items": [
                    {"item_id": tenant["kunu"], "quantity": 2},
                    {"item_id": tenant["jollof"], "quantity": 1},
                ],
                "customer_name": "Ada",
                "delivery_address": "Lekki Phase 1",
            },
        )
        assert pr["ok"] is True
        assert pr["total_kobo"] == 100000 * 2 + 250000
        assert pr["total"] == "NGN 4,500"
        session.add(Message(business_id=tenant["business_id"], conversation_id=tenant["conversation_id"], role=MESSAGE_ROLE_CUSTOMER, body="yes"))
        await session.flush()
        result = await dispatch(session, tenant, "create_order", {"draft_id": pr["draft_id"]})
        assert result["ok"] is True
        assert result["status"] == ORDER_STATUS_PENDING

        order = await session.get(Order, result["order_id"])
        assert order is not None
        assert order.customer_phone == tenant["phone"]
        assert order.customer_name == "Ada"
        assert [i["name"] for i in order.items] == ["Kunu Drink", "Jollof Rice"]


async def test_create_order_insufficient_stock(tenant):
    async with SessionLocal() as session:
        result = await dispatch(
            session,
            tenant,
            "propose_order",
            {"items": [{"item_id": tenant["kunu"], "quantity": 99}]},
        )
        assert result["ok"] is False
        assert any("stock" in e.lower() for e in result["errors"])


async def test_create_order_rejects_foreign_item(tenant, other_tenant):
    async with SessionLocal() as session:
        result = await dispatch(
            session,
            tenant,
            "propose_order",
            {"items": [{"item_id": other_tenant["item"], "quantity": 1}]},
        )
        assert result["ok"] is False
        assert "not found" in result["errors"][0]


async def test_tenant_isolation_across_tools(tenant, other_tenant):
    async with SessionLocal() as session:
        mine = await dispatch(session, tenant, "search_catalog", {"query": "foreign"})
        theirs = await dispatch(
            session, other_tenant, "search_catalog", {"query": "foreign"}
        )
        assert mine["results"] == []
        assert [r["name"] for r in theirs["results"]] == ["Foreign Item"]

        orders = (
            await session.execute(
                select(Order).where(Order.business_id == tenant["business_id"])
            )
        ).scalars().all()
        assert all(o.business_id == tenant["business_id"] for o in orders)