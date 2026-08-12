from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from inbox2action.stage4.persistence import _sqlalchemy_url


def upgrade_database(database_url: str) -> None:
    """Apply the versioned Inbox2Action schema to the configured PostgreSQL DB."""

    project_root = Path(__file__).resolve().parents[3]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "db" / "alembic"))
    config.set_main_option(
        "sqlalchemy.url",
        _sqlalchemy_url(database_url).replace("%", "%%"),
    )
    command.upgrade(config, "head")
