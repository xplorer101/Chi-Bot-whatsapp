"""Slot computation for bookings.

All persistence is UTC; opening hours are wall-clock in the business's
timezone (default Africa/Lagos). Everything here is pure except the
read-only `async` helpers.
"""
from datetime import UTC, datetime, time, timedelta
from datetime import date as _date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.config import settings
from app.models.booking import Booking
from app.models.business import Business
from app.models.business_hours import BusinessHours
from app.models.enums import BOOKING_BLOCKING_STATUSES

_WEEKDAYS = {
    "monday": 1,
    "mon": 1,
    "tuesday": 2,
    "tue": 2,
    "tues": 2,
    "wednesday": 3,
    "wed": 3,
    "thursday": 4,
    "thu": 4,
    "friday": 5,
    "fri": 5,
    "saturday": 6,
    "sat": 6,
    "sunday": 7,
    "sun": 7,
}


def business_zone(business: Business) -> ZoneInfo:
    try:
        return ZoneInfo(business.timezone or "Africa/Lagos")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Africa/Lagos")


def local_now(tz: ZoneInfo, now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)).astimezone(tz)


def resolve_local_date(value, tz: ZoneInfo, now: datetime | None = None):
    """Resolve 'today' / 'tomorrow' / 'friday' / '2026-10-11' to a local date."""
    if value is None:
        return None
    s = str(value).strip().lower()
    today = local_now(tz, now).date()
    if s in ("", "today"):
        return today
    if s == "tomorrow":
        return today + timedelta(days=1)
    if s == "yesterday":
        return today - timedelta(days=1)
    stripped = s.removeprefix("next ")
    if stripped in _WEEKDAYS:
        delta = (_WEEKDAYS[stripped] - today.isoweekday()) % 7
        if s.startswith("next ") and delta == 0:
            delta = 7
        return today + timedelta(days=delta)
    try:
        return _date.fromisoformat(s)
    except ValueError:
        return None


def parse_start_time(value, tz: ZoneInfo):
    """Parse an ISO-8601 start; naive values are interpreted in the business tz."""
    if not value:
        return None
    s = str(value).strip()
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(UTC)


def format_slot(dt_utc: datetime, tz: ZoneInfo) -> str:
    return dt_utc.astimezone(tz).strftime("%a %d %b, %-I:%M %p")


def format_day(dt_utc: datetime, tz: ZoneInfo) -> str:
    return dt_utc.astimezone(tz).strftime("%A %d %B")


async def _blocking_intervals(session, business_id: str, day_start, day_end):
    rows = await session.execute(
        select(Booking.slot_start, Booking.slot_end).where(
            Booking.business_id == business_id,
            Booking.status.in_(BOOKING_BLOCKING_STATUSES),
            Booking.slot_start < day_end,
            Booking.slot_end > day_start,
        )
    )
    return [(r[0], r[1]) for r in rows.all()]


async def is_slot_free(
    session, business_id: str, start_utc: datetime, end_utc: datetime
) -> bool:
    result = await session.execute(
        select(Booking.id).where(
            Booking.business_id == business_id,
            Booking.status.in_(BOOKING_BLOCKING_STATUSES),
            Booking.slot_start < end_utc,
            Booking.slot_end > start_utc,
        )
    )
    return result.first() is None


async def compute_slots(
    session,
    business: Business,
    service,
    local_date,
    now: datetime | None = None,
) -> list[dict]:
    """Open, unbooked, notice-compliant starts for `service` on `local_date`."""
    tz = business_zone(business)
    now_utc = now or datetime.now(UTC)
    if local_date is None:
        return []
    today = local_now(tz, now_utc).date()
    if local_date < today:
        return []
    if local_date > today + timedelta(days=business.booking_max_days_ahead or 30):
        return []

    duration = int(getattr(service, "duration_minutes", None) or 30)
    interval = max(int(business.booking_slot_interval_minutes or 30), 5)
    earliest = now_utc + timedelta(minutes=business.booking_min_notice_minutes or 0)
    weekday = local_date.isoweekday()

    rows = (
        await session.execute(
            select(BusinessHours)
            .where(BusinessHours.business_id == business.id)
            .where(BusinessHours.weekday == weekday)
            .where(BusinessHours.active.is_(True))
            .order_by(BusinessHours.start_time)
        )
    ).scalars().all()

    day_start = datetime.combine(local_date, time.min, tzinfo=tz).astimezone(UTC)
    day_end = day_start + timedelta(days=1)
    blocked = await _blocking_intervals(session, business.id, day_start, day_end)

    out: list[dict] = []
    for row in rows:
        cursor = datetime.combine(local_date, row.start_time, tzinfo=tz)
        seg_end = datetime.combine(local_date, row.end_time, tzinfo=tz)
        while cursor + timedelta(minutes=duration) <= seg_end:
            start_local = cursor
            cursor = cursor + timedelta(minutes=interval)
            start_utc = start_local.astimezone(UTC)
            end_utc = start_utc + timedelta(minutes=duration)
            if start_utc < earliest:
                continue
            if any(s < end_utc and e > start_utc for s, e in blocked):
                continue
            out.append(
                {
                    "start": start_utc.isoformat(),
                    "end": end_utc.isoformat(),
                    "label": format_slot(start_utc, tz),
                    "time_label": start_local.strftime("%-I:%M %p"),
                }
            )

    out.sort(key=lambda s: s["start"])
    return out[: settings.max_slots_returned]
