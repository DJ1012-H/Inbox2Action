"""Opt-in ClickUp readonly smoke test with safe summary output."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from pydantic import ValidationError

from inbox2action.clickup import (
    ClickUpClient,
    ClickUpConfigurationError,
    ClickUpError,
)
from inbox2action.config import Settings


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # The smoke test intentionally has no unbounded provider options.
    try:
        settings = Settings()
        token = settings.clickup_api_token_value
        list_id = settings.clickup_list_id
        if token is None or list_id is None:
            raise ClickUpConfigurationError()
        client = ClickUpClient(
            api_token=token,
            list_id=list_id,
            timeout_seconds=settings.clickup_timeout_seconds,
        )
        user = client.get_authorized_user()
        tasks = client.get_list_tasks()
    except ValidationError:
        print("clickup_smoke_failed: configuration", file=sys.stderr)
        return 1
    except ClickUpError as error:
        print(f"clickup_smoke_failed: {error.code}", file=sys.stderr)
        return 1

    print("clickup_auth_ok")
    print(f"user_id={user.user_id}")
    print(f"username={user.username}")
    print("clickup_list_access_ok")
    print(f"list_id={list_id}")
    print(f"visible_task_count={len(tasks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
