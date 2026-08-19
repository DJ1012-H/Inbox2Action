"""Persist provider-neutral resource references on execution results.

Revision ID: 0004_stage7_execution_resources
Revises: 0003_stage6_workflow_index
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_stage7_execution_resources"
down_revision: str | None = "0003_stage6_workflow_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inbox2action_execution_ledger",
        sa.Column("resource_provider", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "inbox2action_execution_ledger",
        sa.Column("resource_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "inbox2action_execution_ledger",
        sa.Column("resource_id", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "inbox2action_execution_ledger",
        sa.Column("resource_url", sa.String(length=2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inbox2action_execution_ledger", "resource_url")
    op.drop_column("inbox2action_execution_ledger", "resource_id")
    op.drop_column("inbox2action_execution_ledger", "resource_type")
    op.drop_column("inbox2action_execution_ledger", "resource_provider")
