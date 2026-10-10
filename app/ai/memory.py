from sqlalchemy import func, select

from app.models import Message
from app.models.enums import MESSAGE_ROLE_CUSTOMER, MESSAGE_ROLE_SYSTEM

HISTORY_LIMIT = 20
SUMMARY_AFTER = 30


async def load_recent_messages(session, conversation_id: str) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq.desc())
        .limit(HISTORY_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(reversed(rows))


def to_anthropic_messages(rows: list[Message]) -> list[dict]:
    """Map stored messages to Anthropic user/assistant turns, merging repeats."""
    out: list[dict] = []
    for message in rows:
        if message.role == MESSAGE_ROLE_SYSTEM or not message.body:
            continue
        role = "user" if message.role == MESSAGE_ROLE_CUSTOMER else "assistant"
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n" + message.body
        else:
            out.append({"role": role, "content": message.body})
    return out


async def count_messages(session, conversation_id: str) -> int:
    stmt = select(func.count()).select_from(Message).where(
        Message.conversation_id == conversation_id
    )
    return (await session.execute(stmt)).scalar_one() or 0


async def old_messages_beyond_history(session, conversation_id: str) -> list[Message]:
    """Return the oldest messages that no longer fit in the rolling history."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq.asc())
    )
    rows = list((await session.execute(stmt)).scalars())
    return rows[: max(0, len(rows) - HISTORY_LIMIT)]


async def require_summary_refresh(total: int) -> bool:
    """Rewrite the rolling summary when the conversation has grown noticeably."""
    return total >= SUMMARY_AFTER and total % 10 == 0