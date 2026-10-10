"""booking schema: hours, booking drafts, booking settings, no-overlap guard

Revision ID: 0004_bookings
Revises: 0003_order_drafts
Create Date: 2026-10-10 16:34:26.126514

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_bookings"
down_revision: Union[str, None] = "0003_order_drafts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EXCLUDE_CONSTRAINT = "ex_bookings_no_overlap"


def upgrade() -> None:
    # DB-level double-booking prevention: GIST over (business_id, time range).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "business_hours",
        sa.Column("business_id", sa.String(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.String(), nullable=False),
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
        sa.CheckConstraint(
            "weekday >= 1 AND weekday <= 7", name="ck_business_hours_weekday_range"
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_business_hours_business_id"),
        "business_hours",
        ["business_id"],
        unique=False,
    )
    op.create_table(
        "booking_drafts",
        sa.Column("business_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("service_id", sa.String(), nullable=True),
        sa.Column("customer_name", sa.String(length=160), nullable=True),
        sa.Column("customer_phone", sa.String(length=32), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("proposed_at_seq", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
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
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_booking_drafts_business_id"),
        "booking_drafts",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_booking_drafts_conversation_id"),
        "booking_drafts",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_booking_drafts_conversation_status",
        "booking_drafts",
        ["conversation_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_booking_drafts_service_id"),
        "booking_drafts",
        ["service_id"],
        unique=False,
    )

    op.add_column(
        "bookings", sa.Column("reminder_due_at", sa.DateTime(timezone=True))
    )
    op.add_column("bookings", sa.Column("price_kobo", sa.Integer()))
    op.add_column("bookings", sa.Column("duration_minutes", sa.Integer()))
    op.create_index(
        "ix_bookings_business_slot",
        "bookings",
        ["business_id", "slot_start"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bookings_reminder_due_at"),
        "bookings",
        ["reminder_due_at"],
        unique=False,
    )

    op.execute(
        f"""
        ALTER TABLE bookings
        ADD CONSTRAINT {EXCLUDE_CONSTRAINT}
        EXCLUDE USING gist (
            business_id WITH =,
            tstzrange(slot_start, slot_end, '[)') WITH &&
        )
        WHERE (status NOT IN ('cancelled', 'declined'))
        """
    )

    op.add_column(
        "businesses",
        sa.Column(
            "booking_min_notice_minutes",
            sa.Integer(),
            server_default="120",
            nullable=False,
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "booking_max_days_ahead",
            sa.Integer(),
            server_default="30",
            nullable=False,
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "booking_slot_interval_minutes",
            sa.Integer(),
            server_default="30",
            nullable=False,
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "booking_requires_approval",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "booking_cancellation_window_minutes",
            sa.Integer(),
            server_default="120",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("businesses", "booking_cancellation_window_minutes")
    op.drop_column("businesses", "booking_requires_approval")
    op.drop_column("businesses", "booking_slot_interval_minutes")
    op.drop_column("businesses", "booking_max_days_ahead")
    op.drop_column("businesses", "booking_min_notice_minutes")

    op.execute(f"ALTER TABLE bookings DROP CONSTRAINT IF EXISTS {EXCLUDE_CONSTRAINT}")

    op.drop_index(op.f("ix_bookings_reminder_due_at"), table_name="bookings")
    op.drop_index("ix_bookings_business_slot", table_name="bookings")
    op.drop_column("bookings", "duration_minutes")
    op.drop_column("bookings", "price_kobo")
    op.drop_column("bookings", "reminder_due_at")

    op.drop_index(op.f("ix_booking_drafts_service_id"), table_name="booking_drafts")
    op.drop_index("ix_booking_drafts_conversation_status", table_name="booking_drafts")
    op.drop_index(
        op.f("ix_booking_drafts_conversation_id"), table_name="booking_drafts"
    )
    op.drop_index(op.f("ix_booking_drafts_business_id"), table_name="booking_drafts")
    op.drop_table("booking_drafts")

    op.drop_index(op.f("ix_business_hours_business_id"), table_name="business_hours")
    op.drop_table("business_hours")
