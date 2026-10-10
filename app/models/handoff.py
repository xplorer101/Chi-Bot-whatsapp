from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import HANDOFF_STATUS_OPEN


class Handoff(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "handoffs"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, index=True
    )
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("owners.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=HANDOFF_STATUS_OPEN, server_default=HANDOFF_STATUS_OPEN
    )
    reason: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))