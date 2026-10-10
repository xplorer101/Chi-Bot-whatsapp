
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    SmallInteger,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class BusinessHours(UUIDMixin, TimestampMixin, Base):
    """Weekly opening hours, wall-clock in the business's timezone.

    Multiple rows per weekday express breaks (the gaps between them). Times are
    stored as local wall-clock `time` values, not UTC.
    """

    __tablename__ = "business_hours"
    __table_args__ = (
        CheckConstraint(
            "weekday >= 1 AND weekday <= 7", name="ck_business_hours_weekday_range"
        ),
    )

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    # 1 = Monday ... 7 = Sunday (matches date.isoweekday()).
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[object] = mapped_column(Time)
    end_time: Mapped[object] = mapped_column(Time)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")