"""Tests for two-phase bookings: availability engine, guards, race-safety."""
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.ai import booking_tools, tools
from app.ai.agent import respond
from app.db import SessionLocal
from app.models import (
    Booking,
    BookingDraft,
    Business,
    BusinessHours,
    Conversation,
    Message,
    Service,
)
from app.models.enums import (
    BOOKING_STATUS_CANCELLED,
    BOOKING_STATUS_CONFIRMED,
    BOOKING_STATUS_PENDING,
    DRAFT_STATUS_PLACED,
    MESSAGE_ROLE_CUSTOMER,
)
from app.services import availability

pytestmark = pytest.mark.asyncio

LAGOS = ZoneInfo("Africa/Lagos")
NOW = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)  # 07:00 Lagos, Monday
TARGET = date(2026, 10, 12)


def _utc(local_hour, local_minute=0, day=TARGET):
    return datetime(
        day.year, day.month, day.day, local_hour - 1, local_minute, tzinfo=UTC
    )


def _future_date_str(days=3):
    d = (datetime.now(UTC) + timedelta(days=days)).astimezone(LAGOS).date()
    return d.isoformat()


@pytest.fixture
async def shop():
    sid = uuid.uuid4().hex[:8]
    async with SessionLocal() as session:
        business = Business(
            name=f"Shop {sid}",
            slug=f"shop-{sid}",
            whatsapp_phone_number_id=f"77{sid}",
            timezone="Africa/Lagos",
            booking_min_notice_minutes=120,
            booking_max_days_ahead=30,
            booking_slot_interval_minutes=30,
            booking_requires_approval=True,
            booking_cancellation_window_minutes=120,
        )
        session.add(business)
        await session.flush()
        haircut = Service(
            business_id=business.id, name="Haircut", price_kobo=300000, duration_minutes=30
        )
        deluxe = Service(
            business_id=business.id, name="Deluxe Cut", price_kobo=500000, duration_minutes=60
        )
        session.add_all([haircut, deluxe])
        for weekday in range(1, 8):
            session.add(
                BusinessHours(
                    business_id=business.id, weekday=weekday, start_time=time(9, 0), end_time=time(13, 0)
                )
            )
            session.add(
                BusinessHours(
                    business_id=business.id, weekday=weekday, start_time=time(14, 0), end_time=time(18, 0)
                )
            )
        convo = Conversation(business_id=business.id, customer_phone=f"23480{sid}")
        other = Conversation(business_id=business.id, customer_phone=f"23481{sid}")
        session.add_all([convo, other])
        await session.commit()
        data = {
            "business_id": business.id,
            "haircut": haircut.id,
            "deluxe": deluxe.id,
            "conversation_id": convo.id,
            "other_conversation_id": other.id,
        }

    yield data

    async with SessionLocal() as session:
        from sqlalchemy import delete

        await session.execute(delete(Business).where(Business.id == data["business_id"]))
        await session.commit()


# --------------------------------------------------------------------------- #
# Availability engine
# ---------------------------------------------------------------------------


async def test_slots_respect_hours_break_and_timezone(shop):
    async with SessionLocal() as session:
        business = await session.get(Business, shop["business_id"])
        service = await session.get(Service, shop["haircut"])
        slots = await availability.compute_slots(session, business, service, TARGET, now=NOW)
    starts = {s["start"] for s in slots}
    assert len(slots) == 16  # 8 morning + 8 afternoon (30 min apart)
    assert slots[0]["start"] == "2026-10-12T08:00:00+00:00"  # 09:00 Lagos
    assert slots[0]["time_label"] == "9:00 AM"
    assert "2026-10-12T12:00:00+00:00" not in starts  # 13:00 Lagos is the break
    assert "2026-10-12T13:00:00+00:00" in starts  # 14:00 Lagos resumes


async def test_min_notice_blocks_early_slots(shop):
    async with SessionLocal() as session:
        business = await session.get(Business, shop["business_id"])
        business.booking_min_notice_minutes = 180
        service = await session.get(Service, shop["haircut"])
        today = NOW.astimezone(LAGOS).date()
        slots = await availability.compute_slots(session, business, service, today, now=NOW)
    assert slots[0]["start"] == "2026-10-05T09:00:00+00:00"  # 10:00 Lagos


async def test_max_days_ahead_horizon(shop):
    async with SessionLocal() as session:
        business = await session.get(Business, shop["business_id"])
        service = await session.get(Service, shop["haircut"])
        far = NOW.astimezone(LAGOS).date() + timedelta(days=31)
        assert await availability.compute_slots(session, business, service, far, now=NOW) == []


async def test_duration_overlap_with_existing_booking(shop):
    async with SessionLocal() as session:
        business = await session.get(Business, shop["business_id"])
        deluxe = await session.get(Service, shop["deluxe"])
        session.add(
            Booking(
                business_id=business.id,
                customer_phone="2340000000000",
                slot_start=_utc(10, 0),
                slot_end=_utc(10, 30),
                status=BOOKING_STATUS_CONFIRMED,
            )
        )
        await session.commit()
        slots = await availability.compute_slots(session, business, deluxe, TARGET, now=NOW)
    starts = {s["start"] for s in slots}
    assert "2026-10-12T08:30:00+00:00" not in starts  # 09:30 Lagos (60m) overlaps
    assert "2026-10-12T09:30:00+00:00" in starts  # 10:30 Lagos is free


async def test_double_booking_blocked_by_db_constraint(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        bid = b.id
        session.add(
            Booking(
                business_id=bid,
                customer_phone="a",
                slot_start=_utc(9, 0),
                slot_end=_utc(9, 30),
                status=BOOKING_STATUS_CONFIRMED,
            )
        )
        await session.commit()
        session.add(
            Booking(
                business_id=bid,
                customer_phone="b",
                slot_start=_utc(9, 15),
                slot_end=_utc(9, 45),
                status=BOOKING_STATUS_CONFIRMED,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        # cancelled rows are excluded from the constraint predicate
        session.add(
            Booking(
                business_id=bid,
                customer_phone="c",
                slot_start=_utc(9, 0),
                slot_end=_utc(9, 30),
                status=BOOKING_STATUS_CANCELLED,
            )
        )
        await session.commit()


async def test_lagos_midnight_and_naive_time():
    tz = ZoneInfo("Africa/Lagos")
    late = datetime(2026, 10, 12, 23, 30, tzinfo=UTC)  # already the 13th in Lagos
    assert availability.resolve_local_date("today", tz, late) == date(2026, 10, 13)
    assert availability.resolve_local_date("tomorrow", tz, late) == date(2026, 10, 14)
    assert availability.resolve_local_date("2026-10-12", tz, late) == date(2026, 10, 12)
    assert availability.parse_start_time("2026-10-12T16:00", tz) == datetime(
        2026, 10, 12, 15, 0, tzinfo=UTC
    )


async def test_slots_near_local_midnight(shop):
    async with SessionLocal() as session:
        business = await session.get(Business, shop["business_id"])
        service = await session.get(Service, shop["haircut"])
        # replace hours: only 23:00-23:59, 30-min service -> single slot
        for row in (
            await session.execute(
                select(BusinessHours).where(BusinessHours.business_id == business.id)
            )
        ).scalars():
            await session.delete(row)
        session.add(
            BusinessHours(
                business_id=business.id,
                weekday=TARGET.isoweekday(),
                start_time=time(23, 0),
                end_time=time(23, 59),
            )
        )
        await session.commit()
        slots = await availability.compute_slots(session, business, service, TARGET, now=NOW)
    assert len(slots) == 1
    assert slots[0]["start"] == "2026-10-12T22:00:00+00:00"  # 23:00 Lagos
    assert slots[0]["time_label"] == "11:00 PM"


async def _check(session, b, conv, service, date_str):
    return await booking_tools.handle(
        session, b, conv, "check_availability_slots", {"service": service, "date": date_str}
    )


async def test_propose_then_confirm_requires_new_message(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        conv = await session.get(Conversation, shop["conversation_id"])
        check = await _check(session, b, conv, shop["haircut"], _future_date_str())
        assert check["ok"] and check["slots"]
        prop = await booking_tools.handle(
            session, b, conv, "propose_booking",
            {"service": shop["haircut"], "start_time": check["slots"][0]["start"], "customer_name": "Ada"},
        )
        assert prop["ok"] and prop["draft_id"]
        assert prop["requires_approval"] is True

        early = await booking_tools.handle(
            session, b, conv, "confirm_booking", {"draft_id": prop["draft_id"]}
        )
        assert not early["ok"] and "not confirmed" in early["errors"][0].lower()

        session.add(
            Message(business_id=b.id, conversation_id=conv.id, role=MESSAGE_ROLE_CUSTOMER, body="yes")
        )
        await session.flush()
        conf = await booking_tools.handle(
            session, b, conv, "confirm_booking", {"draft_id": prop["draft_id"]}
        )
        assert conf["ok"] and conf["status"] == BOOKING_STATUS_PENDING
        draft = await session.get(BookingDraft, prop["draft_id"])
        assert draft.status == DRAFT_STATUS_PLACED
        booking = await session.get(Booking, conf["booking_id"])
        assert booking.reminder_due_at is not None
        assert booking.price_kobo == 300000


async def test_confirm_refused_for_other_customer(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        conv = await session.get(Conversation, shop["conversation_id"])
        other = await session.get(Conversation, shop["other_conversation_id"])
        check = await _check(session, b, conv, shop["haircut"], _future_date_str())
        prop = await booking_tools.handle(
            session, b, conv, "propose_booking",
            {"service": shop["haircut"], "start_time": check["slots"][0]["start"]},
        )
        session.add(
            Message(business_id=b.id, conversation_id=conv.id, role=MESSAGE_ROLE_CUSTOMER, body="yes")
        )
        await session.flush()
        result = await booking_tools.handle(
            session, b, other, "confirm_booking", {"draft_id": prop["draft_id"]}
        )
        assert not result["ok"] and "customer" in result["errors"][0].lower()


async def test_confirm_refused_for_other_business(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        conv = await session.get(Conversation, shop["conversation_id"])
        check = await _check(session, b, conv, shop["haircut"], _future_date_str())
        prop = await booking_tools.handle(
            session, b, conv, "propose_booking",
            {"service": shop["haircut"], "start_time": check["slots"][0]["start"]},
        )
        other_business = Business(
            name="Other", slug=f"other-{uuid.uuid4().hex[:8]}", whatsapp_phone_number_id="0000"
        )
        session.add(other_business)
        await session.flush()
        other_conv = Conversation(business_id=other_business.id, customer_phone=conv.customer_phone)
        session.add(other_conv)
        await session.flush()
        result = await booking_tools.handle(
            session, other_business, other_conv, "confirm_booking", {"draft_id": prop["draft_id"]}
        )
        assert not result["ok"] and "draft" in result["errors"][0].lower()


async def test_confirm_refused_if_draft_expired(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        conv = await session.get(Conversation, shop["conversation_id"])
        check = await _check(session, b, conv, shop["haircut"], _future_date_str())
        prop = await booking_tools.handle(
            session, b, conv, "propose_booking",
            {"service": shop["haircut"], "start_time": check["slots"][0]["start"]},
        )
        session.add(
            Message(business_id=b.id, conversation_id=conv.id, role=MESSAGE_ROLE_CUSTOMER, body="yes")
        )
        await session.flush()
        draft = await session.get(BookingDraft, prop["draft_id"])
        draft.expires_at = draft.created_at - timedelta(minutes=1)
        await session.commit()
        result = await booking_tools.handle(
            session, b, conv, "confirm_booking", {"draft_id": prop["draft_id"]}
        )
        assert not result["ok"] and "expired" in result["errors"][0].lower()


async def test_confirm_refused_when_slot_racily_taken(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        conv = await session.get(Conversation, shop["conversation_id"])
        check = await _check(session, b, conv, shop["haircut"], _future_date_str())
        slot = check["slots"][0]
        prop = await booking_tools.handle(
            session, b, conv, "propose_booking",
            {"service": shop["haircut"], "start_time": slot["start"]},
        )
        session.add(
            Booking(
                business_id=b.id,
                customer_phone="2349999999999",
                slot_start=datetime.fromisoformat(slot["start"]),
                slot_end=datetime.fromisoformat(slot["end"]),
                status=BOOKING_STATUS_CONFIRMED,
            )
        )
        session.add(
            Message(business_id=b.id, conversation_id=conv.id, role=MESSAGE_ROLE_CUSTOMER, body="yes")
        )
        await session.commit()
        result = await booking_tools.handle(
            session, b, conv, "confirm_booking", {"draft_id": prop["draft_id"]}
        )
        assert not result["ok"] and "taken" in result["errors"][0].lower()


async def test_confirmed_immediately_when_no_approval_needed(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        b.booking_requires_approval = False
        conv = await session.get(Conversation, shop["conversation_id"])
        check = await _check(session, b, conv, shop["haircut"], _future_date_str())
        prop = await booking_tools.handle(
            session, b, conv, "propose_booking",
            {"service": shop["haircut"], "start_time": check["slots"][0]["start"]},
        )
        session.add(
            Message(business_id=b.id, conversation_id=conv.id, role=MESSAGE_ROLE_CUSTOMER, body="yes")
        )
        await session.flush()
        result = await booking_tools.handle(
            session, b, conv, "confirm_booking", {"draft_id": prop["draft_id"]}
        )
        assert result["ok"] and result["status"] == BOOKING_STATUS_CONFIRMED


async def test_cancel_rules(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        conv = await session.get(Conversation, shop["conversation_id"])
        far = datetime.now(UTC) + timedelta(days=10)
        booking = Booking(
            business_id=b.id,
            conversation_id=conv.id,
            customer_phone=conv.customer_phone,
            slot_start=far,
            slot_end=far + timedelta(minutes=30),
            status=BOOKING_STATUS_CONFIRMED,
        )
        soon = datetime.now(UTC) + timedelta(minutes=30)
        soon_booking = Booking(
            business_id=b.id,
            conversation_id=conv.id,
            customer_phone=conv.customer_phone,
            slot_start=soon,
            slot_end=soon + timedelta(minutes=30),
            status=BOOKING_STATUS_CONFIRMED,
        )
        session.add_all([booking, soon_booking])
        await session.commit()

        ok = await booking_tools.handle(
            session, b, conv, "cancel_booking", {"booking_id": booking.id}
        )
        assert ok["ok"]
        again = await booking_tools.handle(
            session, b, conv, "cancel_booking", {"booking_id": booking.id}
        )
        assert not again["ok"]

        refused = await booking_tools.handle(
            session, b, conv, "cancel_booking", {"booking_id": soon_booking.id}
        )
        assert not refused["ok"]

        other = await session.get(Conversation, shop["other_conversation_id"])
        foreign = await booking_tools.handle(
            session, b, other, "cancel_booking", {"booking_id": soon_booking.id}
        )
        assert not foreign["ok"]


async def test_reschedule_rules(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        conv = await session.get(Conversation, shop["conversation_id"])
        check = await _check(session, b, conv, shop["haircut"], _future_date_str())
        first, second = check["slots"][0], check["slots"][1]
        prop = await booking_tools.handle(
            session, b, conv, "propose_booking",
            {"service": shop["haircut"], "start_time": first["start"]},
        )
        session.add(
            Message(business_id=b.id, conversation_id=conv.id, role=MESSAGE_ROLE_CUSTOMER, body="yes")
        )
        await session.flush()
        conf = await booking_tools.handle(
            session, b, conv, "confirm_booking", {"draft_id": prop["draft_id"]}
        )
        moved = await booking_tools.handle(
            session, b, conv, "reschedule_booking",
            {"booking_id": conf["booking_id"], "start_time": second["start"]},
        )
        assert moved["ok"] and moved["slot"] == second["label"]
        # occupy the old slot with someone else's booking, then try to move back
        session.add(
            Booking(
                business_id=b.id,
                customer_phone="2348880000000",
                slot_start=datetime.fromisoformat(first["start"]),
                slot_end=datetime.fromisoformat(first["end"]),
                status=BOOKING_STATUS_CONFIRMED,
            )
        )
        await session.flush()
        taken = await booking_tools.handle(
            session, b, conv, "reschedule_booking",
            {"booking_id": conf["booking_id"], "start_time": first["start"]},
        )
        assert not taken["ok"]


async def test_offline_mock_booking_flow(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        conv = Conversation(business_id=b.id, customer_phone="2347000000042")
        session.add(conv)
        await session.commit()
        conv_id = conv.id

    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        conv = await session.get(Conversation, conv_id)
        reply1 = await respond(session, b, conv, "I wan book haircut for tomorrow")
        assert "confirm" in reply1.lower()
        reply2 = await respond(session, b, conv, "yes")
        assert "booked" in reply2.lower()
        await session.commit()

    async with SessionLocal() as session:
        bookings = (
            await session.execute(select(Booking).where(Booking.conversation_id == conv_id))
        ).scalars().all()
        assert len(bookings) == 1
        assert bookings[0].status == BOOKING_STATUS_PENDING


async def test_dispatch_routes_booking_tools(shop):
    async with SessionLocal() as session:
        b = await session.get(Business, shop["business_id"])
        conv = await session.get(Conversation, shop["conversation_id"])
        raw = await tools.dispatch(
            session, b, conv, "check_availability_slots",
            {"service": shop["haircut"], "date": _future_date_str()},
        )
        assert '"slots"' in raw
