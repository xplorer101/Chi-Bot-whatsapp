from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import BOOKING_STATUS_PENDING


class Booking(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_business_created", "business_id", "created_at"),
        Index("ix_bookings_business_slot", "business_id", "slot_start"),
        # Database-level double-booking guard: two overlapping (by half-open
        # [start, end) range) bookings for the same business cannot both commit.
        # Cancelled/declined bookings release their slot. Backed by btree_gist.
        ExcludeConstraint(
            (text("business_id"), "="),
            (text("tstzrange(slot_start, slot_end, '[)')"), "&&"),
            name="ex_bookings_no_overlap",
            using="gist",
            where=text("status NOT IN ('cancelled', 'declined')"),
        ),
    )

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), index=True
    )
    customer_name: Mapped[str | None] = mapped_column(String(160))
    customer_phone: Mapped[str] = mapped_column(String(32))
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), default=BOOKING_STATUS_PENDING, server_default=BOOKING_STATUS_PENDING
    )
    reminder_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    price_kobo: Mapped[int | None] = mapped_column(Integer)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
