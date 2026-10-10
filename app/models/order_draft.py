from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import DRAFT_STATUS_ACTIVE


class OrderDraft(UUIDMixin, TimestampMixin, Base):
    """A half-placed order awaiting explicit customer confirmation.

    Proposed server-side with validated stock and prices; only promoted to an
    Order once the customer confirms in a NEW message after the proposal.
    """

    __tablename__ = "order_drafts"
    __table_args__ = (
        Index(
            "ix_order_drafts_conversation_status", "conversation_id", "status"
        ),
    )

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    customer_phone: Mapped[str] = mapped_column(String(32))
    customer_name: Mapped[str | None] = mapped_column(String(160))
    delivery_address: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list] = mapped_column(JSONB, default=list)
    total_kobo: Mapped[int] = mapped_column(Integer)
    # Max customer message seq at proposal time; create_order requires a NEWER
    # customer message as the confirmation turn.
    proposed_at_seq: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        String(20),
        default=DRAFT_STATUS_ACTIVE,
        server_default=DRAFT_STATUS_ACTIVE,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))