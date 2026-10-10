from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class Message(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    # Monotonic ordering key: created_at uses the transaction timestamp, so it is
    # NOT reliable for ordering rows inserted within the same transaction.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), index=True)

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    body: Mapped[str | None] = mapped_column(Text)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")