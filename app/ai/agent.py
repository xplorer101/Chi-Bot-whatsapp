import logging
from datetime import UTC, datetime

from app.ai import provider, tools
from app.ai.memory import (
    load_recent_messages,
    old_messages_beyond_history,
    require_summary_refresh,
    to_anthropic_messages,
)
from app.ai.pidgin import detect_language
from app.ai.prompt import build_system_prompt
from app.models import Business, Conversation, Message
from app.models.enums import MESSAGE_ROLE_BOT, MESSAGE_ROLE_CUSTOMER
from app.services.context import load_faqs, load_items, load_services

logger = logging.getLogger("chibot.ai")

MAX_TOOL_ROUNDS = 6


def fallback_reply(business: Business) -> str:
    return (
        f"Sorry, I can't answer that right now. Let me get someone from "
        f"{business.name} to help you."
    )


async def respond(
    session, business: Business, conversation: Conversation, user_text: str
) -> str:
    """Persist the customer turn, generate a reply, persist it, return the text."""
    language = detect_language(user_text)

    session.add(
        Message(
            business_id=business.id,
            conversation_id=conversation.id,
            role=MESSAGE_ROLE_CUSTOMER,
            body=user_text,
        )
    )
    await session.flush()

    try:
        text = await generate_reply(session, business, conversation, language)
    except provider.AIUnavailable:
        logger.warning("AI unavailable; using fallback reply")
        text = fallback_reply(business)

    text = text.strip()
    session.add(
        Message(
            business_id=business.id,
            conversation_id=conversation.id,
            role=MESSAGE_ROLE_BOT,
            body=text,
        )
    )
    conversation.last_message_at = datetime.now(UTC)
    await session.flush()
    return text


async def generate_reply(
    session, business: Business, conversation: Conversation, language: str
) -> str:
    history = to_anthropic_messages(
        await load_recent_messages(session, conversation.id)
    )

    faqs = await load_faqs(session, business.id)
    items = await load_items(session, business.id)
    services = await load_services(session, business.id)
    system = build_system_prompt(
        business,
        faqs,
        items,
        services,
        summary=conversation.summary,
        language=language,
    )

    working: list[dict] = list(history)
    for _ in range(MAX_TOOL_ROUNDS):
        result = await provider.complete_round(system, working, tools=tools.TOOLS)
        if not result.tool_use:
            return result.text or fallback_reply(business)

        assistant_content: list[dict] = []
        if result.text:
            assistant_content.append({"type": "text", "text": result.text})
        for call in result.tool_use:
            assistant_content.append(
                {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.name,
                    "input": call.input,
                }
            )
        working.append({"role": "assistant", "content": assistant_content})

        tool_results: list[dict] = []
        for call in result.tool_use:
            output = await tools.dispatch(
                session, business, conversation, call.name, call.input
            )
            logger.info("tool %s -> %s", call.name, output[:200])
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": output,
                }
            )
        working.append({"role": "user", "content": tool_results})

    logger.warning("tool loop exceeded %s rounds", MAX_TOOL_ROUNDS)
    return fallback_reply(business)


async def maybe_refresh_summary(
    session, business: Business, conversation: Conversation
) -> None:
    from app.ai.memory import count_messages

    total = await count_messages(session, conversation.id)
    if not await require_summary_refresh(total):
        return
    old = await old_messages_beyond_history(session, conversation.id)
    if not old:
        return
    lines = [f"{m.role}: {m.body}" for m in old if m.body]
    try:
        conversation.summary = await provider.summarize(lines)
        logger.info("refreshed summary for conversation %s", conversation.id)
    except provider.AIUnavailable:
        logger.warning("AI unavailable; skipping summary refresh")