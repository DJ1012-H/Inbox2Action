"""Persist provider diagnostics without retaining secrets or raw bodies.

Revision ID: 0005_execution_diagnostics
Revises: 0004_stage7_execution_resources
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_execution_diagnostics"
down_revision: str | None = "0004_stage7_execution_resources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inbox2action_execution_ledger",
        sa.Column("diagnostics_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inbox2action_execution_ledger", "diagnostics_json")
