from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class InboundTextMessage:
    phone_number_id: str
    customer_phone: str
    message_id: str
    text: str
    contact_name: str | None = None


def parse_inbound_messages(payload: dict[str, Any]) -> list[InboundTextMessage]:
    """Extract inbound text messages from a Meta WhatsApp webhook payload.

    Non-text messages (images, audio, ...) are ignored in this build.
    """
    messages: list[InboundTextMessage] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            if not phone_number_id:
                continue
            contacts = value.get("contacts") or []
            contact_name = None
            if contacts:
                contact_name = (contacts[0].get("profile") or {}).get("name")

            for msg in value.get("messages") or []:
                if msg.get("type") != "text":
                    continue
                text = (msg.get("text") or {}).get("body")
                if not text:
                    continue
                messages.append(
                    InboundTextMessage(
                        phone_number_id=phone_number_id,
                        customer_phone=msg.get("from", ""),
                        message_id=msg.get("id", ""),
                        text=text,
                        contact_name=contact_name,
                    )
                )
    return messages