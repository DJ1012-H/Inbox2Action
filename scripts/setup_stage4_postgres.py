from __future__ import annotations

import os

from inbox2action.stage4 import upgrade_database


def main() -> int:
    database_url = os.getenv("INBOX2ACTION_DATABASE_URL")
    if not database_url:
        raise SystemExit("INBOX2ACTION_DATABASE_URL is required")
    upgrade_database(database_url)
    print("Stage 4 PostgreSQL schema is at the latest revision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
