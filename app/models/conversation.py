from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import CONVERSATION_STATUS_ACTIVE

if TYPE_CHECKING:
    from app.models.message import Message


class Conversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "customer_phone", name="uq_conversations_business_customer"
        ),
    )

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    customer_phone: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(20),
        default=CONVERSATION_STATUS_ACTIVE,
        server_default=CONVERSATION_STATUS_ACTIVE,
    )
    summary: Mapped[str | None] = mapped_column(Text)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", passive_deletes=True
    )