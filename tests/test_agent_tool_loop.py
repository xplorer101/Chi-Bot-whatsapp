"""Verify the tool-use loop drives tools via the dispatcher and returns text."""

import pytest_asyncio
from sqlalchemy import select

from app.ai import provider
from app.ai.agent import generate_reply, respond
from app.ai.provider import RoundResult, ToolCall
from app.db import SessionLocal
from app.models import Business, Conversation, Order
from app.models.enums import ORDER_STATUS_PENDING


@pytest_asyncio.fixture
async def conversation(tenant):
    async with SessionLocal() as session:
        convo = Conversation(
            business_id=tenant["business_id"],
            customer_phone="23470" + tenant["phone"][-6:],
        )
        session.add(convo)
        await session.commit()
        return {"business_id": tenant["business_id"], "conversation_id": convo.id}


async def test_loop_runs_tool_then_returns_text(monkeypatch, tenant, conversation):
    calls = []

    async def fake_complete_round(system, messages, tools=None):
        calls.append(messages)
        if len(calls) == 1:
            return RoundResult(
                text="Let me check.",
                tool_use=[
                    ToolCall(id="tc1", name="search_catalog", input={"query": "jollof"})
                ],
            )
        return RoundResult(text="Final answer after the search.")

    monkeypatch.setattr(provider, "complete_round", fake_complete_round)

    async with SessionLocal() as session:
        business = await session.get(Business, tenant["business_id"])
        convo = await session.get(Conversation, conversation["conversation_id"])
        reply = await generate_reply(session, business, convo, "english")

    assert reply == "Final answer after the search."
    assert len(calls) == 2
    fed_back = calls[1][-1]
    assert fed_back["role"] == "user"
    assert fed_back["content"][0]["type"] == "tool_result"
    assert "Jollof Rice" in fed_back["content"][0]["content"]


async def test_loop_gives_up_after_max_rounds(monkeypatch, tenant, conversation):
    async def endless_tools(system, messages, tools=None):
        return RoundResult(
            tool_use=[ToolCall(id=f"tc-{len(messages)}", name="create_order", input={})]
        )

    monkeypatch.setattr(provider, "complete_round", endless_tools)

    async with SessionLocal() as session:
        business = await session.get(Business, tenant["business_id"])
        convo = await session.get(Conversation, conversation["conversation_id"])
        reply = await generate_reply(session, business, convo, "english")

    assert "Sorry" in reply


async def test_offline_mock_full_order_flow(tenant, conversation):
    """AI_MOCK scripts the real loop: propose -> summary -> confirm -> order."""
    async with SessionLocal() as session:
        business = await session.get(Business, tenant["business_id"])
        convo = await session.get(Conversation, conversation["conversation_id"])

        reply1 = await respond(session, business, convo, "I want to order jollof rice")
        assert "Total: NGN 2,500" in reply1
        assert "confirm" in reply1.lower()

        # nothing placed yet
        orders = (await session.execute(select(Order))).scalars().all()
        assert orders == []

        reply2 = await respond(session, business, convo, "yes")
        assert "received" in reply2.lower()
        await session.commit()

    async with SessionLocal() as session:
        orders = (
            await session.execute(
                select(Order).where(Order.business_id == tenant["business_id"])
            )
        ).scalars().all()
        assert len(orders) == 1
        assert orders[0].status == ORDER_STATUS_PENDING
        assert orders[0].total_kobo == 250000