"""Booking tools: same two-phase safety as ordering.

  * check_availability_slots lists real open times (hours, breaks, notice,
    max-days-ahead, existing bookings) in the business's timezone;
  * propose_booking validates a chosen start against those slots and saves a
    DRAFT (+ draft_id) for the bot to show the customer;
  * confirm_booking(draft_id) only creates the Booking once the customer has
    sent a NEW message after the proposal;
  * cancel_booking / reschedule_booking only touch this customer's own
    bookings and respect the business's cancellation window.

Double-booking is additionally prevented at the database level by an exclude
constraint on bookings (see migration 0004), so a race that slips past the
pre-checks still cannot commit two overlapping bookings.
"""
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.ai.prompt import format_naira
from app.config import settings
from app.models import Booking, BookingDraft, Business, Conversation, Message, Service
from app.models.enums import (
    BOOKING_BLOCKING_STATUSES,
    BOOKING_STATUS_CANCELLED,
    BOOKING_STATUS_CONFIRMED,
    BOOKING_STATUS_PENDING,
    DRAFT_STATUS_ACTIVE,
    DRAFT_STATUS_EXPIRED,
    DRAFT_STATUS_PLACED,
    DRAFT_STATUS_SUPERSEDED,
    MESSAGE_ROLE_CUSTOMER,
)
from app.services import availability

logger = logging.getLogger("chibot.tools")

BOOKING_TOOL_NAMES = {
    "check_availability_slots",
    "propose_booking",
    "confirm_booking",
    "cancel_booking",
    "reschedule_booking",
}

check_availability_slots_schema = {
    "name": "check_availability_slots",
    "description": (
        "List the real open appointment times for one service on a given day. "
        "Always call this before proposing a booking - never invent times. "
        "'date' accepts 'today', 'tomorrow', a weekday name like 'saturday', or "
        "YYYY-MM-DD. Times returned are in the business's local time."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Service id (from the services list) or its name.",
            },
            "date": {
                "type": "string",
                "description": "Day to check. Defaults to today.",
            },
        },
        "required": ["service"],
    },
}

propose_booking_schema = {
    "name": "propose_booking",
    "description": (
        "Hold an appointment slot and save a DRAFT booking for the customer to "
        "confirm. Pass a start_time returned by check_availability_slots. Returns "
        "a draft_id and a summary - show it to the customer and ask them to confirm. "
        "This does NOT book yet. If the customer changes the time, call it again."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "Service id or name."},
            "start_time": {
                "type": "string",
                "description": "Start time from check_availability_slots (ISO-8601).",
            },
            "customer_name": {
                "type": "string",
                "description": "Customer's name, if known.",
            },
        },
        "required": ["service", "start_time"],
    },
}

confirm_booking_schema = {
    "name": "confirm_booking",
    "description": (
        "Confirm a booking draft you already proposed. Call this ONLY after the "
        "customer explicitly confirms the summary in a NEW message. Pass the "
        "draft_id from propose_booking. If you call it too early it is refused."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "draft_id": {
                "type": "string",
                "description": "The draft_id returned by propose_booking.",
            }
        },
        "required": ["draft_id"],
    },
}

cancel_booking_schema = {
    "name": "cancel_booking",
    "description": (
        "Cancel one of this customer's existing bookings. Only works for this "
        "customer's own bookings and only if the appointment is far enough away "
        "(the business sets a cancellation window). Pass the booking_id."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "booking_id": {"type": "string", "description": "The booking id to cancel."}
        },
        "required": ["booking_id"],
    },
}

reschedule_booking_schema = {
    "name": "reschedule_booking",
    "description": (
        "Move one of this customer's bookings to a new start time. Check "
        "check_availability_slots first and pass a valid start_time. Only works "
        "for this customer's own bookings outside the cancellation window."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "booking_id": {"type": "string", "description": "The booking id to move."},
            "start_time": {
                "type": "string",
                "description": "New start time (ISO-8601) from check_availability_slots.",
            },
        },
        "required": ["booking_id", "start_time"],
    },
}

TOOLS = [
    check_availability_slots_schema,
    propose_booking_schema,
    confirm_booking_schema,
    cancel_booking_schema,
    reschedule_booking_schema,
]


async def handle(
    session, business: Business, conversation: Conversation, name: str, args: dict[str, Any]
) -> dict | None:
    if name not in BOOKING_TOOL_NAMES:
        return None
    if name == "check_availability_slots":
        return await _check_availability_slots(session, business, args)
    if name == "propose_booking":
        return await _propose_booking(session, business, conversation, args)
    if name == "confirm_booking":
        return await _confirm_booking(session, business, conversation, args)
    if name == "cancel_booking":
        return await _cancel_booking(session, business, conversation, args)
    if name == "reschedule_booking":
        return await _reschedule_booking(session, business, conversation, args)
    return None


async def _resolve_service(session, business_id: str, value) -> Service | None:
    if not value:
        return None
    value = str(value).strip()
    service = (
        await session.execute(
            select(Service).where(
                Service.business_id == business_id, Service.id == value
            )
        )
    ).scalar_one_or_none()
    if service is not None:
        return service
    return (
        await session.execute(
            select(Service)
            .where(
                Service.business_id == business_id,
                Service.active.is_(True),
                or_(
                    Service.name.ilike(f"%{value}%"),
                    func.lower(Service.name) == value.lower(),
                ),
            )
            .order_by(Service.created_at)
        )
    ).scalars().first()


def _slot_matches(slots: list[dict], start_utc: datetime) -> dict | None:
    target = start_utc.isoformat()
    for slot in slots:
        if datetime.fromisoformat(slot["start"]) == start_utc:
            return slot
        if slot["start"] == target:
            return slot
    return None


async def _check_availability_slots(session, business: Business, args: dict) -> dict:
    service = await _resolve_service(session, business.id, args.get("service"))
    if service is None:
        return {"ok": False, "errors": ["I could not find that service."]}

    tz = availability.business_zone(business)
    local_date = availability.resolve_local_date(args.get("date"), tz)
    if local_date is None:
        return {
            "ok": False,
            "errors": ["I did not understand that day. Try 'tomorrow' or a date."],
        }

    slots = await availability.compute_slots(session, business, service, local_date)
    if not slots:
        return {
            "ok": True,
            "service_id": service.id,
            "service": service.name,
            "date": local_date.isoformat(),
            "slots": [],
            "note": "No open times on that day - suggest another day.",
        }
    return {
        "ok": True,
        "service_id": service.id,
        "service": service.name,
        "price": format_naira(service.price_kobo),
        "duration_minutes": service.duration_minutes,
        "date": local_date.isoformat(),
        "day_label": availability.format_day(
            datetime.fromisoformat(slots[0]["start"]), tz
        ),
        "slots": slots,
    }


async def _supersede_active_drafts(session, conversation_id: str) -> None:
    existing = (
        await session.execute(
            select(BookingDraft).where(
                BookingDraft.conversation_id == conversation_id,
                BookingDraft.status == DRAFT_STATUS_ACTIVE,
            )
        )
    ).scalars().all()
    for row in existing:
        row.status = DRAFT_STATUS_SUPERSEDED


async def _last_customer_seq(session, conversation_id: str) -> int:
    return (
        await session.execute(
            select(func.max(Message.seq)).where(
                Message.conversation_id == conversation_id,
                Message.role == MESSAGE_ROLE_CUSTOMER,
            )
        )
    ).scalar_one() or 0


async def _propose_booking(
    session, business: Business, conversation: Conversation, args: dict
) -> dict:
    service = await _resolve_service(session, business.id, args.get("service"))
    if service is None:
        return {"ok": False, "errors": ["I could not find that service."]}

    tz = availability.business_zone(business)
    start_utc = availability.parse_start_time(args.get("start_time"), tz)
    if start_utc is None:
        return {"ok": False, "errors": ["I did not understand that time."]}

    local_date = start_utc.astimezone(tz).date()
    slots = await availability.compute_slots(session, business, service, local_date)
    slot = _slot_matches(slots, start_utc)
    if slot is None:
        alternatives = [s["label"] for s in slots[:4]]
        return {
            "ok": False,
            "errors": ["That time is not available."],
            "available": alternatives,
            "note": "Offer one of the available times, or check another day.",
        }

    await _supersede_active_drafts(session, conversation.id)
    seq = await _last_customer_seq(session, conversation.id)

    draft = BookingDraft(
        business_id=business.id,
        conversation_id=conversation.id,
        service_id=service.id,
        customer_name=(args.get("customer_name") or "").strip() or None,
        customer_phone=conversation.customer_phone,
        slot_start=datetime.fromisoformat(slot["start"]),
        slot_end=datetime.fromisoformat(slot["end"]),
        proposed_at_seq=seq,
        status=DRAFT_STATUS_ACTIVE,
        expires_at=datetime.now(UTC)
        + timedelta(minutes=settings.booking_draft_ttl_minutes),
    )
    session.add(draft)
    await session.flush()
    logger.info(
        "proposed booking draft %s for business %s (%s)",
        draft.id,
        business.id,
        draft.customer_phone,
    )
    return {
        "ok": True,
        "draft_id": draft.id,
        "status": "awaiting_confirmation",
        "service": service.name,
        "price": format_naira(service.price_kobo),
        "slot": slot["label"],
        "start_time": slot["start"],
        "requires_approval": business.booking_requires_approval,
        "expires_in_minutes": settings.booking_draft_ttl_minutes,
        "note": (
            "Show this and ask the customer to confirm. Only call confirm_booking "
            "after they reply to confirm."
        ),
    }


async def _confirm_booking(
    session, business: Business, conversation: Conversation, args: dict
) -> dict:
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return {
            "ok": False,
            "errors": ["A draft_id is required. Call propose_booking first."],
        }

    draft = await session.get(BookingDraft, draft_id)
    if draft is None:
        return {"ok": False, "errors": ["No draft with that id. Propose the booking again."]}
    if draft.business_id != business.id or draft.customer_phone != conversation.customer_phone:
        return {"ok": False, "errors": ["That draft does not belong to this customer."]}
    if draft.status != DRAFT_STATUS_ACTIVE:
        return {
            "ok": False,
            "errors": ["That draft is no longer valid. Propose the booking again."],
        }
    if draft.expires_at <= datetime.now(UTC):
        draft.status = DRAFT_STATUS_EXPIRED
        return {"ok": False, "errors": ["That draft has expired. Propose the booking again."]}

    confirmed = await _count_new_customer_messages(
        session, draft.conversation_id, draft.proposed_at_seq
    )
    if not confirmed:
        return {
            "ok": False,
            "errors": [
                (
                    "The customer has not confirmed this draft yet. Show the summary "
                    "again and ask them to reply to confirm."
                )
            ],
        }

    free = await availability.is_slot_free(
        session, business.id, draft.slot_start, draft.slot_end
    )
    if not free:
        draft.status = DRAFT_STATUS_SUPERSEDED
        return {
            "ok": False,
            "errors": ["Sorry, that slot was just taken. Offer another time."],
        }

    service = await session.get(Service, draft.service_id) if draft.service_id else None
    status = (
        BOOKING_STATUS_PENDING
        if business.booking_requires_approval
        else BOOKING_STATUS_CONFIRMED
    )
    booking = Booking(
        business_id=business.id,
        conversation_id=draft.conversation_id,
        service_id=draft.service_id,
        customer_name=draft.customer_name,
        customer_phone=draft.customer_phone,
        slot_start=draft.slot_start,
        slot_end=draft.slot_end,
        status=status,
        reminder_due_at=draft.slot_start
        - timedelta(minutes=settings.booking_reminder_lead_minutes),
        price_kobo=service.price_kobo if service else None,
        duration_minutes=service.duration_minutes if service else None,
    )
    session.add(booking)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        session.expunge(booking)
        draft.status = DRAFT_STATUS_SUPERSEDED
        logger.warning("booking race lost for draft %s (slot taken)", draft.id)
        return {
            "ok": False,
            "errors": ["Sorry, that slot was just taken. Offer another time."],
        }

    draft.status = DRAFT_STATUS_PLACED
    await session.flush()
    tz = availability.business_zone(business)
    logger.info(
        "created booking %s from draft %s for business %s (%s)",
        booking.id,
        draft.id,
        business.id,
        booking.customer_phone,
    )
    return {
        "ok": True,
        "booking_id": booking.id,
        "draft_id": draft.id,
        "status": booking.status,
        "service": service.name if service else None,
        "slot": availability.format_slot(booking.slot_start, tz),
        "requires_approval": business.booking_requires_approval,
        "note": (
            "Tell the customer it is booked pending the business's approval."
            if booking.status == BOOKING_STATUS_PENDING
            else "Confirm the appointment to the customer."
        ),
    }


async def _count_new_customer_messages(session, conversation_id, proposed_at_seq) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == MESSAGE_ROLE_CUSTOMER,
                Message.seq > proposed_at_seq,
            )
        )
    ).scalar_one()


async def _cancel_booking(
    session, business: Business, conversation: Conversation, args: dict
) -> dict:
    booking_id = (args.get("booking_id") or "").strip()
    if not booking_id:
        return {"ok": False, "errors": ["A booking_id is required."]}
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.business_id != business.id:
        return {"ok": False, "errors": ["I could not find that booking."]}
    if booking.customer_phone != conversation.customer_phone:
        return {"ok": False, "errors": ["That booking is not on this number."]}
    if booking.status not in BOOKING_BLOCKING_STATUSES:
        return {"ok": False, "errors": ["That booking is already cancelled."]}

    now = datetime.now(UTC)
    if not _can_change(business, booking, now):
        return {
            "ok": False,
            "errors": [
                (
                    "That appointment is too close to change online. Please contact "
                    "the business directly."
                )
            ],
        }

    booking.status = BOOKING_STATUS_CANCELLED
    booking.reminder_due_at = None
    await session.flush()
    tz = availability.business_zone(business)
    return {
        "ok": True,
        "booking_id": booking.id,
        "status": booking.status,
        "slot": availability.format_slot(booking.slot_start, tz),
    }


async def _reschedule_booking(
    session, business: Business, conversation: Conversation, args: dict
) -> dict:
    booking_id = (args.get("booking_id") or "").strip()
    if not booking_id:
        return {"ok": False, "errors": ["A booking_id is required."]}
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.business_id != business.id:
        return {"ok": False, "errors": ["I could not find that booking."]}
    if booking.customer_phone != conversation.customer_phone:
        return {"ok": False, "errors": ["That booking is not on this number."]}
    if booking.status not in BOOKING_BLOCKING_STATUSES:
        return {"ok": False, "errors": ["That booking is already cancelled."]}

    now = datetime.now(UTC)
    if not _can_change(business, booking, now):
        return {
            "ok": False,
            "errors": [
                (
                    "That appointment is too close to move online. Please contact the "
                    "business directly."
                )
            ],
        }

    service = await session.get(Service, booking.service_id) if booking.service_id else None
    if service is None:
        return {"ok": False, "errors": ["I could not find the service for that booking."]}

    tz = availability.business_zone(business)
    start_utc = availability.parse_start_time(args.get("start_time"), tz)
    if start_utc is None:
        return {"ok": False, "errors": ["I did not understand that time."]}

    local_date = start_utc.astimezone(tz).date()
    slots = await availability.compute_slots(session, business, service, local_date)
    slot = _slot_matches(slots, start_utc)
    if slot is None:
        return {
            "ok": False,
            "errors": ["That time is not available."],
            "available": [s["label"] for s in slots[:4]],
        }

    booking.slot_start = datetime.fromisoformat(slot["start"])
    booking.slot_end = datetime.fromisoformat(slot["end"])
    booking.reminder_due_at = booking.slot_start - timedelta(
        minutes=settings.booking_reminder_lead_minutes
    )
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        return {"ok": False, "errors": ["Sorry, that slot was just taken. Offer another time."]}

    tz = availability.business_zone(business)
    return {
        "ok": True,
        "booking_id": booking.id,
        "status": booking.status,
        "slot": availability.format_slot(booking.slot_start, tz),
    }


def _can_change(business: Business, booking: Booking, now: datetime) -> bool:
    if booking.status not in BOOKING_BLOCKING_STATUSES:
        return False
    window = business.booking_cancellation_window_minutes or 0
    return booking.slot_start - now >= timedelta(minutes=window)
