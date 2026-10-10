"""Tests for two-phase ordering with drafts."""
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.ai import tools
from app.db import SessionLocal, engine
from app.models import (
    Business,
    CatalogItem,
    Conversation,
    Message,
    Order,
    OrderDraft,
)
from app.models.enums import (
    CONVERSATION_STATUS_ACTIVE,
    DRAFT_STATUS_PLACED,
    MESSAGE_ROLE_CUSTOMER,
    ORDER_STATUS_PENDING,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await engine.dispose()


async def _dispatch(session, tenant, name, args):
    business = await session.get(Business, tenant["business_id"])
    conversation = await session.get(Conversation, tenant["conversation_id"])
    raw = await tools.dispatch(session, business, conversation, name, args)
    return json.loads(raw)


@pytest.fixture
async def tenant():
    import uuid

    sid = str(uuid.uuid4())[:8]
    async with SessionLocal() as session:
        b = Business(name=f"B{sid}", slug=f"b{sid}", whatsapp_phone_number_id=f"90{sid}")
        session.add(b)
        await session.flush()
        k = CatalogItem(business_id=b.id, name="Rice", price_kobo=100000, stock_qty=5)
        session.add(k)
        await session.flush()
        c = Conversation(
            business_id=b.id,
            customer_phone=f"2348000{sid}",
            status=CONVERSATION_STATUS_ACTIVE,
        )
        session.add(c)
        await session.flush()
        session.add(Message(business_id=b.id, conversation_id=c.id, role=MESSAGE_ROLE_CUSTOMER, body="hi"))
        await session.commit()
        return {
            "business_id": b.id,
            "conversation_id": c.id,
            "item": k.id,
            "phone": c.customer_phone,
        }


@pytest.fixture
async def other_tenant():
    import uuid

    sid = str(uuid.uuid4())[:8]
    async with SessionLocal() as session:
        b = Business(name=f"O{sid}", slug=f"o{sid}", whatsapp_phone_number_id=f"91{sid}")
        session.add(b)
        await session.flush()
        k = CatalogItem(business_id=b.id, name="Rice", price_kobo=100000, stock_qty=5)
        session.add(k)
        await session.flush()
        c = Conversation(
            business_id=b.id,
            customer_phone=f"2348100{sid}",
            status=CONVERSATION_STATUS_ACTIVE,
        )
        session.add(c)
        await session.flush()
        session.add(Message(business_id=b.id, conversation_id=c.id, role=MESSAGE_ROLE_CUSTOMER, body="hi"))
        await session.commit()
        return {
            "business_id": b.id,
            "conversation_id": c.id,
            "item": k.id,
            "phone": c.customer_phone,
        }


async def test_propose_order_creates_draft_and_summarises(tenant):
    async with SessionLocal() as session:
        res = await _dispatch(
            session,
            tenant,
            "propose_order",
            {"items": [{"item_id": tenant["item"], "quantity": 2}]},
        )
        assert res["ok"] is True
        assert "draft_id" in res
        assert res["total_kobo"] == 200000
        assert res["total"] == "NGN 2,000"
        draft = await session.get(OrderDraft, res["draft_id"])
        assert draft is not None
        assert draft.status == "active"


async def test_propose_order_replaces_old_draft(tenant):
    async with SessionLocal() as session:
        r1 = await _dispatch(
            session,
            tenant,
            "propose_order",
            {"items": [{"item_id": tenant["item"], "quantity": 1}]},
        )
        r2 = await _dispatch(
            session,
            tenant,
            "propose_order",
            {"items": [{"item_id": tenant["item"], "quantity": 3}]},
        )
        # old draft superseded
        old = await session.get(OrderDraft, r1["draft_id"])
        assert old.status == "superseded"
        # new active
        newd = await session.get(OrderDraft, r2["draft_id"])
        assert newd.status == "active"
        assert newd.total_kobo == 300000


async def test_create_order_refused_with_no_new_customer_message(tenant):
    async with SessionLocal() as session:
        r = await _dispatch(
            session,
            tenant,
            "propose_order",
            {"items": [{"item_id": tenant["item"], "quantity": 1}]},
        )
        cres = await _dispatch(
            session,
            tenant,
            "create_order",
            {"draft_id": r["draft_id"]},
        )
        assert cres["ok"] is False
        assert "not confirmed" in cres["errors"][0].lower()


async def test_create_order_happy_path_after_confirmation(tenant):
    async with SessionLocal() as session:
        r = await _dispatch(
            session,
            tenant,
            "propose_order",
            {"items": [{"item_id": tenant["item"], "quantity": 1}]},
        )
        session.add(Message(business_id=tenant["business_id"], conversation_id=tenant["conversation_id"], role=MESSAGE_ROLE_CUSTOMER, body="yes"))
        await session.flush()
        cres = await _dispatch(
            session,
            tenant,
            "create_order",
            {"draft_id": r["draft_id"]},
        )
        assert cres["ok"] is True
        assert cres["status"] == ORDER_STATUS_PENDING
        # draft placed
        draft = await session.get(OrderDraft, r["draft_id"])
        assert draft.status == DRAFT_STATUS_PLACED
        # order exists
        o = await session.get(Order, cres["order_id"])
        assert o is not None
        assert o.total_kobo == 100000


async def test_create_order_refused_for_other_customer(tenant, other_tenant):
    async with SessionLocal() as session:
        # propose on tenant
        r = await _dispatch(
            session,
            tenant,
            "propose_order",
            {"items": [{"item_id": tenant["item"], "quantity": 1}]},
        )
        # add confirmation msg to tenant
        session.add(Message(business_id=tenant["business_id"], conversation_id=tenant["conversation_id"], role=MESSAGE_ROLE_CUSTOMER, body="yes"))
        await session.flush()
        # try from other
        cres = await _dispatch(
            session,
            other_tenant,
            "create_order",
            {"draft_id": r["draft_id"]},
        )
        assert cres["ok"] is False
        assert "customer" in cres["errors"][0].lower()


async def test_create_order_refused_if_draft_expired(tenant):
    async with SessionLocal() as session:
        r = await _dispatch(
            session,
            tenant,
            "propose_order",
            {"items": [{"item_id": tenant["item"], "quantity": 1}]},
        )
        session.add(Message(business_id=tenant["business_id"], conversation_id=tenant["conversation_id"], role=MESSAGE_ROLE_CUSTOMER, body="yes"))
        await session.flush()
        draft = await session.get(OrderDraft, r["draft_id"])
        draft.expires_at = draft.created_at - timedelta(minutes=1)
        await session.commit()
        cres = await _dispatch(
            session,
            tenant,
            "create_order",
            {"draft_id": r["draft_id"]},
        )
        assert cres["ok"] is False
        assert "expired" in cres["errors"][0].lower()
        draft = await session.get(OrderDraft, r["draft_id"])
        assert draft.status == "expired"


async def test_propose_order_checks_stock_and_returns_errors(tenant):
    async with SessionLocal() as session:
        res = await _dispatch(
            session,
            tenant,
            "propose_order",
            {"items": [{"item_id": tenant["item"], "quantity": 99}]},
        )
        assert res["ok"] is False
        assert any("stock" in e.lower() for e in res["errors"])
        # no draft created for this tenant
        drafts = (
            await session.execute(
                select(OrderDraft).where(OrderDraft.business_id == tenant["business_id"])
            )
        ).scalars().all()
        assert all(d.status != "active" for d in drafts)
