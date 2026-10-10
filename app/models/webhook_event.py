from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import WEBHOOK_STATUS_RECEIVED


class WebhookEvent(UUIDMixin, TimestampMixin, Base):
    """Idempotency ledger for inbound Meta webhook deliveries."""

    __tablename__ = "webhook_events"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    meta_message_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=WEBHOOK_STATUS_RECEIVED,
        server_default=WEBHOOK_STATUS_RECEIVED,
    )
    error: Mapped[str | None] = mapped_column(Text)