import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.client import get_client
from app.config import settings

logger = logging.getLogger("chibot.ai")


class AIUnavailable(Exception):
    """Raised when no AI provider is configured and mock mode is off."""


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class RoundResult:
    text: str | None = None
    tool_use: list[ToolCall] = field(default_factory=list)


async def complete_round(
    system: str, messages: list[dict], tools: list[dict] | None = None
) -> RoundResult:
    """One model turn: may return text, tool calls, or both."""
    if settings.ai_mock:
        return RoundResult(text=_mock_answer(system, messages))

    client = get_client()
    if client is None:
        raise AIUnavailable("ANTHROPIC_API_KEY is not set")

    kwargs: dict[str, Any] = {
        "model": settings.anthropic_model,
        "max_tokens": settings.ai_max_tokens,
        "system": system,
        "temperature": 0.3,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    resp = await client.messages.create(**kwargs)

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in resp.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(
                ToolCall(id=block.id, name=block.name, input=dict(block.input or {}))
            )
    return RoundResult(text="".join(text_parts) or None, tool_use=tool_calls)


async def summarize(extra_lines: list[str]) -> str:
    """Build/rebuild the running conversation summary from older turns.

    The summary is rebuilt from scratch on each refresh so it stays
    self-contained (no accumulation/duplication of old turns).
    """
    if settings.ai_mock:
        return " | ".join(line[:80] for line in extra_lines)

    client = get_client()
    if client is None:
        raise AIUnavailable("ANTHROPIC_API_KEY is not set")
    prompt = (
        "Summarise this WhatsApp conversation between a customer and a Nigerian "
        "business assistant. Keep it under 120 words and preserve facts like names, "
        "items, prices and agreed details.\n\n"
        "Turns:\n" + "\n".join(extra_lines)
    )
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _mock_answer(system: str, messages: list[dict]) -> str:
    """Deterministic offline stand-in used for local dev / tests (AI_MOCK=true)."""
    last = messages[-1].get("content", "") if messages else ""
    if not isinstance(last, str):
        last = ""
    faqs = _parse_faqs(system)
    words = _keywords(last)
    best, best_score = None, 0
    for question, answer in faqs:
        score = len(words & _keywords(question))
        if score > best_score:
            best, best_score = answer, score
    if best and best_score > 0:
        return best
    if _looks_pidgin(last):
        return "Ah, I no get that info for now. Make I link you with somebody wey go help you."
    return "I don't have that information yet, but I can connect you with someone who can help."


def _parse_faqs(system: str) -> list[tuple[str, str]]:
    pairs = re.findall(r"^Q: (.+)\nA: (.+)$", system, flags=re.MULTILINE)
    return [(q, a) for q, a in pairs]


_STOPWORDS = {
    "what",
    "are",
    "your",
    "you",
    "is",
    "the",
    "a",
    "an",
    "do",
    "does",
    "how",
    "i",
    "to",
    "of",
    "for",
    "my",
    "and",
    "or",
    "be",
    "am",
    "we",
    "it",
    "can",
    "me",
    "much",
}


def _keywords(text: str) -> set[str]:
    words = set(re.findall(r"[a-z']+", text.lower()))
    return words - _STOPWORDS


def _looks_pidgin(text: str) -> bool:
    markers = {"dey", "na", "abeg", "wetin", "sabi", "don", "wey", "una", "chop"}
    return bool(set(re.findall(r"[a-z']+", text.lower())) & markers)