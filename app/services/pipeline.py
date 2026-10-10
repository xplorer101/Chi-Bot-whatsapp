import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.ai.agent import maybe_refresh_summary, respond
from app.db import SessionLocal
from app.models import Business, Conversation, WebhookEvent
from app.models.base import new_id
from app.models.enums import BUSINESS_STATUS_ACTIVE, WEBHOOK_STATUS_DONE
from app.whatsapp.client import send_text
from app.whatsapp.payload import InboundTextMessage, parse_inbound_messages

logger = logging.getLogger("chibot.pipeline")


async def process_webhook_payload(payload: dict) -> None:
    """Background entrypoint: process every inbound text message in a delivery."""
    for message in parse_inbound_messages(payload):
        try:
            await process_inbound_text(message)
        except Exception:
            logger.exception("failed to process message id=%s", message.message_id)


async def _get_business(session, phone_number_id: str) -> Business | None:
    stmt = select(Business).where(
        Business.whatsapp_phone_number_id == phone_number_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _claim_message(session, business_id: str, message_id: str) -> str | None:
    """Insert an idempotency record; return its id, or None if already seen."""
    stmt = (
        pg_insert(WebhookEvent)
        .values(id=new_id(), business_id=business_id, meta_message_id=message_id)
        .on_conflict_do_nothing(index_elements=["meta_message_id"])
        .returning(WebhookEvent.id)
    )
    row = (await session.execute(stmt)).first()
    return row[0] if row else None


async def _get_or_create_conversation(
    session, business_id: str, customer_phone: str
) -> Conversation:
    stmt = (
        pg_insert(Conversation)
        .values(id=new_id(), business_id=business_id, customer_phone=customer_phone)
        .on_conflict_do_nothing(index_elements=["business_id", "customer_phone"])
    )
    await session.execute(stmt)
    await session.flush()
    return (
        await session.execute(
            select(Conversation).where(
                Conversation.business_id == business_id,
                Conversation.customer_phone == customer_phone,
            )
        )
    ).scalar_one()


async def process_inbound_text(message: InboundTextMessage) -> bool:
    """Resolve tenant, dedupe, persist, generate an AI reply and send it."""
    async with SessionLocal() as session:
        business = await _get_business(session, message.phone_number_id)
        if business is None:
            logger.warning(
                "unknown phone_number_id=%s; dropping", message.phone_number_id
            )
            return False
        if business.status != BUSINESS_STATUS_ACTIVE:
            logger.info("business %s not active; dropping", business.id)
            return False

        event_id = await _claim_message(session, business.id, message.message_id)
        if event_id is None:
            logger.info("duplicate message id=%s; ignoring", message.message_id)
            await session.rollback()
            return False

        conversation = await _get_or_create_conversation(
            session, business.id, message.customer_phone
        )

        reply = await respond(session, business, conversation, message.text)
        await maybe_refresh_summary(session, business, conversation)

        await send_text(business.whatsapp_phone_number_id, message.customer_phone, reply)
        conversation.last_message_at = datetime.now(UTC)

        await session.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(status=WEBHOOK_STATUS_DONE)
        )
        await session.commit()
        logger.info("handled message id=%s from %s", message.message_id, message.customer_phone)
        return True