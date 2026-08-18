"""Add the Stage 6 Gmail identity and workflow listing index.

Revision ID: 0003_stage6_workflow_index
Revises: 0002_execution_ledger
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_stage6_workflow_index"
down_revision: str | None = "0002_execution_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbox2action_workflow_index",
        sa.Column("thread_id", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("message_id", sa.String(length=256), nullable=False),
        sa.Column("from_address", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("received_at", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("thread_id"),
        sa.UniqueConstraint(
            "account_id",
            "message_id",
            name="uq_workflow_index_email_identity",
        ),
    )
    op.create_index(
        "idx_workflow_index_status_updated_at",
        "inbox2action_workflow_index",
        ["status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_workflow_index_status_updated_at",
        table_name="inbox2action_workflow_index",
    )
    op.drop_table("inbox2action_workflow_index")
