from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import BUSINESS_STATUS_ACTIVE

if TYPE_CHECKING:
    from app.models.owner import Owner


class Business(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    opening_hours: Mapped[dict | None] = mapped_column(JSONB)
    location: Mapped[str | None] = mapped_column(String(300))
    delivery_areas: Mapped[list | None] = mapped_column(JSONB)
    payment_details: Mapped[dict | None] = mapped_column(JSONB)
    timezone: Mapped[str] = mapped_column(
        String(64), default="Africa/Lagos", server_default="Africa/Lagos"
    )
    whatsapp_phone_number_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )
    whatsapp_business_account_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(20), default=BUSINESS_STATUS_ACTIVE, server_default=BUSINESS_STATUS_ACTIVE
    )

    booking_min_notice_minutes: Mapped[int] = mapped_column(
        Integer, default=120, server_default="120"
    )
    booking_max_days_ahead: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30"
    )
    booking_slot_interval_minutes: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30"
    )
    booking_requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    booking_cancellation_window_minutes: Mapped[int] = mapped_column(
        Integer, default=120, server_default="120"
    )

    owners: Mapped[list["Owner"]] = relationship(
        back_populates="business", passive_deletes=True
    )