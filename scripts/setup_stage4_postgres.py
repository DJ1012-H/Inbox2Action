from __future__ import annotations

from inbox2action.config import Settings
from inbox2action.stage4 import upgrade_database


def main() -> int:
    database_url = Settings().database_url_value
    if not database_url:
        raise SystemExit(
            "INBOX2ACTION_DATABASE_URL must be configured in runtime.env or the process environment"
        )
    upgrade_database(database_url)
    print("Stage 4 PostgreSQL schema is at the latest revision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
