"""add order drafts

Revision ID: 0003_order_drafts
Revises: 0002_message_seq
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_order_drafts"
down_revision: Union[str, None] = "0002_message_seq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_drafts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("business_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("customer_phone", sa.String(length=32), nullable=False),
        sa.Column("customer_name", sa.String(length=160), nullable=True),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_kobo", sa.Integer(), nullable=False),
        sa.Column("proposed_at_seq", sa.BigInteger(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="active", nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_order_drafts_business_id"), "order_drafts", ["business_id"], unique=False
    )
    op.create_index(
        op.f("ix_order_drafts_conversation_id"),
        "order_drafts",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_drafts_conversation_status",
        "order_drafts",
        ["conversation_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_order_drafts_conversation_status", table_name="order_drafts")
    op.drop_index(op.f("ix_order_drafts_conversation_id"), table_name="order_drafts")
    op.drop_index(op.f("ix_order_drafts_business_id"), table_name="order_drafts")
    op.drop_table("order_drafts")
