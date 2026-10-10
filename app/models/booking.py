from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import BOOKING_STATUS_PENDING


class Booking(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_business_created", "business_id", "created_at"),
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