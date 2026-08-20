from __future__ import annotations

from inbox2action.memory import MemoryCategory, PreferenceContext, TaskPreferences
from inbox2action.memory.policy import (
    apply_task_preference,
    free_calendar_candidates,
    preferred_calendar_duration,
    trusted_calendar_timezone,
    trusted_clickup_list_id,
)


def test_explicit_current_request_beats_task_memory() -> None:
    context = PreferenceContext(task=TaskPreferences(default_priority="high"))
    assert apply_task_preference({"priority": "low"}, context)["priority"] == "low"
    assert apply_task_preference({}, context)["priority"] == "high"


def test_freebusy_beats_calendar_window_memory() -> None:
    context = PreferenceContext(calendar={"preferred_windows": ("16:00", "17:00")})
    assert free_calendar_candidates(
        [("16:00", False), ("17:00", True), ("15:00", True)], context
    ) == ("17:00", "15:00")


def test_explicit_duration_and_trusted_targets_beat_memory() -> None:
    context = PreferenceContext(calendar={"preferred_duration_minutes": 30})
    assert preferred_calendar_duration(60, context) == 60
    assert preferred_calendar_duration(None, context) == 30
    assert trusted_calendar_timezone("Asia/Shanghai", context) == "Asia/Shanghai"
    assert trusted_clickup_list_id("123456", context) == "123456"
    assert MemoryCategory.CALENDAR.value == "calendar_preferences"
