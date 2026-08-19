"""Conservative extraction of explicitly offered meeting intervals."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DATE_PATTERN = re.compile(
    r"(?:(?P<year>20\d{2})\s*[年/-])?"
    r"(?P<month>1[0-2]|0?[1-9])\s*月?\s*"
    r"(?P<day>3[01]|[12]\d|0?[1-9])\s*日?"
)
_TIME_PATTERN = re.compile(
    r"(?P<marker>上午|下午|晚上|早上|午后)?\s*"
    r"(?P<hour>2[0-3]|[01]?\d)\s*(?:点|时)"
    r"(?:\s*(?P<minute>[0-5]?\d)\s*分?)?"
)
_DURATION_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>小时|小時|分钟|分鐘|hour|hours|minutes?)"
)


def extract_authorized_intervals(
    text: str,
    *,
    current_time: str,
    timezone: str,
) -> tuple[tuple[datetime, datetime], ...]:
    """Return explicit same-date candidates with an explicit duration."""

    try:
        zone = ZoneInfo(timezone)
        reference = datetime.fromisoformat(current_time)
        if reference.tzinfo is None or reference.utcoffset() is None:
            return ()
        reference = reference.astimezone(zone)
    except (TypeError, ValueError):
        return ()
    date_match = _DATE_PATTERN.search(text)
    if date_match is None:
        return ()
    try:
        year = int(date_match.group("year") or reference.year)
        meeting_date = datetime(
            year,
            int(date_match.group("month")),
            int(date_match.group("day")),
            tzinfo=zone,
        )
    except (TypeError, ValueError):
        return ()

    times: list[datetime] = []
    for match in _TIME_PATTERN.finditer(text):
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        marker = match.group("marker") or ""
        if marker in {"下午", "午后", "晚上"} and hour < 12:
            hour += 12
        times.append(meeting_date.replace(hour=hour, minute=minute))
    unique_times = tuple(dict.fromkeys(times))
    if not unique_times:
        return ()

    duration = _duration(text)
    if duration is None and len(unique_times) == 2:
        gap = unique_times[1] - unique_times[0]
        if gap > timedelta(0) and _has_range_marker(text):
            duration = gap
    if duration is None or duration <= timedelta(0):
        return ()
    return tuple((start, start + duration) for start in unique_times)


def _duration(text: str) -> timedelta | None:
    match = _DURATION_PATTERN.search(text)
    if match is None:
        return None
    value = float(match.group("value"))
    unit = match.group("unit").casefold()
    if "小时" in unit or "小時" in unit or "hour" in unit:
        return timedelta(minutes=value * 60)
    return timedelta(minutes=value)


def _has_range_marker(text: str) -> bool:
    return bool(re.search(r"(?:到|至|[-–—~])", text))
