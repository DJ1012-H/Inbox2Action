"""Replace the duplicate workflow table with the execution claim ledger.

Revision ID: 0002_execution_ledger
Revises: 0001_stage4_checkpoint
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_execution_ledger"
down_revision: str | None = "0001_stage4_checkpoint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "idx_inbox2action_checkpoint_updated_at",
        table_name="inbox2action_checkpoint",
    )
    op.drop_table("inbox2action_checkpoint")
    op.create_table(
        "inbox2action_execution_ledger",
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=30), nullable=False),
        sa.Column("action_id", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.BigInteger(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('claimed', 'executing', 'succeeded', 'failed', 'unknown')",
            name="ck_execution_ledger_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 1",
            name="ck_execution_ledger_attempt_count",
        ),
        sa.PrimaryKeyConstraint("idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("inbox2action_execution_ledger")
    op.create_table(
        "inbox2action_checkpoint",
        sa.Column("thread_id", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("message_id", sa.String(length=256), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
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
