import json
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
        return _mock_round(system, messages)

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


def _mock_round(system: str, messages: list[dict]) -> RoundResult:
    """Deterministic offline stand-in (AI_MOCK=true).

    Scripts the full order flow so it can be demoed without an API key:
      customer order message -> propose_order (draft) -> summary text to show
      customer confirmation -> create_order(draft_id) -> receipt text
    Everything else falls back to FAQ / Pidgin / generic replies.
    """
    last = messages[-1] if messages else None
    if last is None:
        return RoundResult(text=_mock_answer(system, ""))

    content = last.get("content")
    if isinstance(content, list) and content and content[0].get("type") == "tool_result":
        return RoundResult(text=_mock_react_to_tool_result(content))

    text = _message_text(last)
    draft_id = _draft_id_from_system(system)
    if draft_id and _is_confirmation(text):
        return RoundResult(
            tool_use=[ToolCall(id="tc-confirm", name="create_order", input={"draft_id": draft_id})]
        )
    if _has_order_intent(system, text):
        return RoundResult(
            tool_use=[ToolCall(id="tc-propose", name="propose_order", input=_build_proposal(text, system))]
        )
    return RoundResult(text=_mock_answer(system, text))


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text") for b in content if b.get("type") == "text"]
        return "\n".join(parts)
    return ""


def _catalog_from_system(system: str) -> list[dict]:
    """Parse `- <id> <name>: NGN <price>/<unit>` catalog lines from the prompt."""
    out: list[dict] = []
    for m in re.finditer(
        r"^- (\S+) (.+?): NGN ([0-9,]+)/([^,\n]+)", system, flags=re.MULTILINE
    ):
        out.append(
            {
                "id": m.group(1),
                "name": m.group(2).strip(),
                "unit": m.group(4).strip(),
                "price_kobo": int(m.group(3).replace(",", "")),
            }
        )
    return out


def _draft_id_from_system(system: str) -> str | None:
    m = re.search(r"- draft_id: (\S+)", system)
    return m.group(1) if m else None


_CONFIRM_PHRASES = {
    "yes",
    "ok",
    "okay",
    "yeah",
    "yep",
    "sure",
    "correct",
    "confirm",
    "confirmed",
    "fine",
    "go ahead",
    "place it",
    "place the order",
    "i confirm",
    "that's correct",
    "that is correct",
    "yes confirm",
    "yes na",
    "okay na",
    "abeg place am",
}


def _is_confirmation(text: str) -> bool:
    t = " ".join(text.lower().split())
    if t in _CONFIRM_PHRASES:
        return True
    return any(phrase in t for phrase in _CONFIRM_PHRASES if len(phrase) > 3)


_ORDER_WORDS = {"order", "buy", "want", "interested", "need", "get", "take"}
_MOCK_SKIP_WORDS = {"for", "i", "am", "to", "please", "na", "we", "me", "the", "a", "an"}


def _has_order_intent(system: str, text: str) -> bool:
    words = set(re.findall(r"[a-z']+", text.lower()))
    if words & _ORDER_WORDS:
        return True
    tokens = {w for w in words if len(w) >= 3 and w not in _MOCK_SKIP_WORDS}
    for item in _catalog_from_system(system):
        item_tokens = set(re.findall(r"[a-z']+", item["name"].lower()))
        if tokens & item_tokens:
            return True
    return False


def _build_proposal(text: str, system: str) -> dict:
    """Pick catalog items mentioned in the message (first item if none named)."""
    catalog = _catalog_from_system(system)
    if not catalog:
        return {}
    words = set(re.findall(r"[a-z']+", text.lower()))
    tokens = {w for w in words if len(w) >= 3 and w not in _MOCK_SKIP_WORDS}
    chosen = [
        item
        for item in catalog
        if tokens & set(re.findall(r"[a-z']+", item["name"].lower()))
    ]
    if not chosen:
        chosen = [catalog[0]]

    qty_match = re.search(r"(\d+)", text)
    quantity = max(1, int(qty_match.group(1))) if qty_match else 1

    name_match = re.search(r"(?:name is|call me)\s+([A-Za-z]+)", text, flags=re.IGNORECASE)
    customer_name = name_match.group(1).title() if name_match else "Customer"
    address_match = re.search(r"(?:address is|deliver to|send it to)\s+(.+)", text, flags=re.IGNORECASE)
    delivery_address = address_match.group(1).strip().title() if address_match else None

    return {
        "items": [{"item_id": item["id"], "quantity": quantity} for item in chosen],
        "customer_name": customer_name,
        "delivery_address": delivery_address,
    }


def _mock_react_to_tool_result(content: list[dict]) -> str:
    for block in content:
        if block.get("type") != "tool_result":
            continue
        payload = block.get("content", "")
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return "I could not process that. Please try again."
        if data.get("ok"):
            if "draft_id" in data and "order_id" not in data:
                lines = ["Here is your order summary:"]
                lines += [
                    f"- {item['name']} x{item['quantity']}" for item in data["items"]
                ]
                lines.append(f"Total: {data['total']}")
                lines.append("Reply to confirm and I'll place the order for you.")
                return "\n".join(lines)
            if "order_id" in data:
                return (
                    "Your order has been received and the business will confirm it "
                    "shortly. Thank you!"
                )
        errors = "; ".join(data.get("errors", ["Something went wrong."]))
        return f"I'm sorry, I couldn't do that: {errors} Let me help you fix it."


def _mock_answer(system: str, text: str) -> str:
    """Deterministic offline stand-in for plain Q&A (no order flow)."""
    faqs = _parse_faqs(system)
    words = _keywords(text)
    best, best_score = None, 0
    for question, answer in faqs:
        score = len(words & _keywords(question))
        if score > best_score:
            best, best_score = answer, score
    if best and best_score > 0:
        return best
    if _looks_pidgin(text):
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