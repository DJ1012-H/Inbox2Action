"""Deterministic precedence helpers for memory as a soft preference."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from inbox2action.memory.context import PreferenceContext


def apply_task_preference(
    parameters: Mapping[str, Any], context: PreferenceContext
) -> dict[str, Any]:
    """Fill an absent priority only; an explicit current request always wins."""

    result = dict(parameters)
    if "priority" not in result and context.task.default_priority is not None:
        result["priority"] = context.task.default_priority
    return result


def preferred_calendar_duration(
    explicit_duration_minutes: int | None, context: PreferenceContext
) -> int | None:
    """Use an explicit current duration before a remembered soft preference."""

    if explicit_duration_minutes is not None:
        return explicit_duration_minutes
    return context.calendar.preferred_duration_minutes


def free_calendar_candidates(
    candidates: Sequence[tuple[str, bool]], context: PreferenceContext
) -> tuple[str, ...]:
    """Rank preferred windows after removing BUSY observations entirely."""

    free = [time for time, is_free in candidates if is_free]
    preferred = set(context.calendar.preferred_windows)
    return tuple(sorted(free, key=lambda item: (item not in preferred, item)))


def trusted_calendar_timezone(trusted_timezone: str, context: PreferenceContext) -> str:
    """Memory has no authority to replace the canonical business timezone."""

    del context
    return trusted_timezone


def trusted_clickup_list_id(trusted_list_id: str, context: PreferenceContext) -> str:
    """Memory never selects the provider write target."""

    del context
    return trusted_list_id
