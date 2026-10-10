"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("opening_hours", postgresql.JSONB(), nullable=True),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("delivery_areas", postgresql.JSONB(), nullable=True),
        sa.Column("payment_details", postgresql.JSONB(), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Africa/Lagos"),
        sa.Column("whatsapp_phone_number_id", sa.String(64), nullable=False),
        sa.Column("whatsapp_business_account_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_businesses_slug", "slug", unique=True),
        sa.Index("ix_businesses_whatsapp_phone_number_id", "whatsapp_phone_number_id", unique=True),
    )

    op.create_table(
        "owners",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_owners_business_id", "business_id"),
        sa.Index("ix_owners_email", "email", unique=True),
    )

    op.create_table(
        "faqs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("business_id", "question", name="uq_faqs_business_question"),
        sa.Index("ix_faqs_business_id", "business_id"),
    )

    op.create_table(
        "catalog_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_catalog_categories_business_id", "business_id"),
    )

    op.create_table(
        "catalog_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.String(36), sa.ForeignKey("catalog_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_kobo", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="NGN"),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("stock_qty", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_catalog_items_business_id", "business_id"),
        sa.Index("ix_catalog_items_category_id", "category_id"),
        sa.Index("ix_catalog_items_name", "name"),
    )

    op.create_table(
        "services",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_kobo", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_services_business_id", "business_id"),
    )

    op.create_table(
        "service_slots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", sa.String(36), sa.ForeignKey("services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("weekday >= 1 AND weekday <= 7", name="ck_service_slots_weekday_range"),
        sa.Index("ix_service_slots_business_id", "business_id"),
        sa.Index("ix_service_slots_service_id", "service_id"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_phone", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("business_id", "customer_phone", name="uq_conversations_business_customer"),
        sa.Index("ix_conversations_business_id", "business_id"),
        sa.Index("ix_conversations_last_message_at", "last_message_at"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_messages_business_id", "business_id"),
        sa.Index("ix_messages_conversation_id", "conversation_id"),
        sa.Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_name", sa.String(160), nullable=True),
        sa.Column("customer_phone", sa.String(32), nullable=False),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("items", postgresql.JSONB(), nullable=False),
        sa.Column("total_kobo", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_orders_business_id", "business_id"),
        sa.Index("ix_orders_conversation_id", "conversation_id"),
        sa.Index("ix_orders_business_created", "business_id", "created_at"),
    )

    op.create_table(
        "bookings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_id", sa.String(36), sa.ForeignKey("services.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_name", sa.String(160), nullable=True),
        sa.Column("customer_phone", sa.String(32), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_bookings_business_id", "business_id"),
        sa.Index("ix_bookings_conversation_id", "conversation_id"),
        sa.Index("ix_bookings_service_id", "service_id"),
        sa.Index("ix_bookings_business_created", "business_id", "created_at"),
    )

    op.create_table(
        "handoffs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("owners.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_handoffs_business_id", "business_id"),
        sa.Index("ix_handoffs_conversation_id", "conversation_id", unique=True),
        sa.Index("ix_handoffs_owner_id", "owner_id"),
    )

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_id", sa.String(36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meta_message_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_webhook_events_business_id", "business_id"),
        sa.Index("ix_webhook_events_meta_message_id", "meta_message_id", unique=True),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_table("handoffs")
    op.drop_table("bookings")
    op.drop_table("orders")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("service_slots")
    op.drop_table("services")
    op.drop_table("catalog_items")
    op.drop_table("catalog_categories")
    op.drop_table("faqs")
    op.drop_table("owners")
    op.drop_table("businesses")