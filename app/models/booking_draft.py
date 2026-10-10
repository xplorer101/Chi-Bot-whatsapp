from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import DRAFT_STATUS_ACTIVE


class BookingDraft(UUIDMixin, TimestampMixin, Base):
    """A proposed appointment awaiting explicit customer confirmation.

    Mirrors OrderDraft: server-validated slot saved as a draft; promoted to a
    Booking only after a NEW customer message following the proposal.
    """

    __tablename__ = "booking_drafts"
    __table_args__ = (
        Index("ix_booking_drafts_conversation_status", "conversation_id", "status"),
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
    proposed_at_seq: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        String(20),
        default=DRAFT_STATUS_ACTIVE,
        server_default=DRAFT_STATUS_ACTIVE,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
