"""Verify the tool-use loop drives tools via the dispatcher and returns text."""

import pytest_asyncio

from app.ai import provider
from app.ai.agent import generate_reply
from app.ai.provider import RoundResult, ToolCall
from app.db import SessionLocal
from app.models import Business, Conversation


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