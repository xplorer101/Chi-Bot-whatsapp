"""add monotonic seq to messages

Revision ID: 0002_message_seq
Revises: 0001_initial
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_message_seq"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
    )
    op.create_index("ix_messages_seq", "messages", ["seq"])


def downgrade() -> None:
    op.drop_index("ix_messages_seq", table_name="messages")
    op.drop_column("messages", "seq")