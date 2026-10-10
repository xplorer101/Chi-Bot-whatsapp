from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Service(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "services"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    price_kobo: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ServiceSlot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "service_slots"
    __table_args__ = (
        CheckConstraint(
            "weekday >= 1 AND weekday <= 7", name="ck_service_slots_weekday_range"
        ),
    )

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[Time] = mapped_column(Time)
    end_time: Mapped[Time] = mapped_column(Time)
    capacity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")