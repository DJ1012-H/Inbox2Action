from __future__ import annotations

import asyncio
import selectors
import sys
from collections.abc import Callable

import pytest


def pytest_asyncio_loop_factories(
    config: pytest.Config,
    item: pytest.Item,
) -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    """Create event loops supported by psycopg async connections on Windows."""

    del config, item
    if sys.platform == "win32":
        return {
            "windows-selector": lambda: asyncio.SelectorEventLoop(
                selectors.SelectSelector()
            )
        }
    return {"default": asyncio.new_event_loop}
