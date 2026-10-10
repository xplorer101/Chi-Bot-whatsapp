from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class FAQ(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "faqs"
    __table_args__ = (
        UniqueConstraint("business_id", "question", name="uq_faqs_business_question"),
    )

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")