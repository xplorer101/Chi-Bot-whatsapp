from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ORDER_STATUS_PENDING


class Order(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_business_created", "business_id", "created_at"),)

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    customer_name: Mapped[str | None] = mapped_column(String(160))
    customer_phone: Mapped[str] = mapped_column(String(32))
    delivery_address: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list] = mapped_column(JSONB, default=list)
    total_kobo: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20), default=ORDER_STATUS_PENDING, server_default=ORDER_STATUS_PENDING
    )