"""Create the Stage 4 workflow checkpoint table.

Revision ID: 0001_stage4_checkpoint
Revises:
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_stage4_checkpoint"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbox2action_checkpoint",
        sa.Column("thread_id", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("message_id", sa.String(length=256), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state_version >= 1", name="ck_checkpoint_state_version"),
        sa.PrimaryKeyConstraint("thread_id"),
        sa.UniqueConstraint(
            "account_id",
            "message_id",
            name="uq_checkpoint_email_identity",
        ),
    )
    op.create_index(
        "idx_inbox2action_checkpoint_updated_at",
        "inbox2action_checkpoint",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_inbox2action_checkpoint_updated_at",
        table_name="inbox2action_checkpoint",
    )
    op.drop_table("inbox2action_checkpoint")
