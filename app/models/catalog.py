from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class CatalogCategory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "catalog_categories"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class CatalogItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "catalog_items"

    business_id: Mapped[str] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_categories.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    price_kobo: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(
        String(3), default="NGN", server_default="NGN"
    )
    unit: Mapped[str | None] = mapped_column(String(32))
    available: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    stock_qty: Mapped[int | None] = mapped_column(Integer)