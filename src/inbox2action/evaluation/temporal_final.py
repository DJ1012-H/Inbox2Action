"""Deterministic Chinese date/time resolution from trusted case context."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from inbox2action.evaluation.assets import EvaluationCaseV1

_EXPLICIT_DATE = re.compile(
    r"(?:(?P<year>\d{4})\s*年\s*)?"
    r"(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日"
)
_TIME_RANGE = re.compile(
    r"(?P<start_hour>\d{1,2})\s*:\s*(?P<start_minute>\d{2})"
    r"\s*(?:到|至|[-–—])\s*"
    r"(?P<end_hour>\d{1,2})\s*:\s*(?P<end_minute>\d{2})"
)
_DEADLINE_EXPLICIT = re.compile(
    r"(?:(?P<year>\d{4})\s*年\s*)?"
    r"(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日"
    r"(?:周[一二三四五六日天])?\s*"
    r"(?P<hour>\d{1,2})\s*:\s*(?P<minute>\d{2})\s*前"
)
_DEADLINE_WEEKDAY_TIME = re.compile(
    r"(?P<weekword>本周|下周|周)(?P<weekday>[一二三四五六日天])\s*"
    r"(?P<hour>\d{1,2})\s*:\s*(?P<minute>\d{2})\s*前"
)
_DEADLINE_WEEKDAY_WORK_END = re.compile(
    r"(?P<weekword>本周|下周|周)(?P<weekday>[一二三四五六日天])下班前"
)
_RELATIVE_WEEKDAY = re.compile(r"(?P<prefix>本周|下周)(?P<weekday>[一二三四五六日天])")
_WEEKDAY_INDEX = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


@dataclass(frozen=True)
class ResolvedIntervalFinal:
    start: datetime
    end: datetime


def resolve_calendar_interval_final(
    case: EvaluationCaseV1,
) -> ResolvedIntervalFinal | None:
    text = f"{case.email.subject}\n{case.email.body}"
    range_match = _TIME_RANGE.search(text)
    if range_match is None:
        return None
    current = case.current_time
    timezone = ZoneInfo(case.timezone)
    date_value = _date_for_position(
        text,
        position=range_match.start(),
        current=current,
    )
    if date_value is None:
        return None
    start = datetime.combine(
        date_value,
        time(
            int(range_match.group("start_hour")),
            int(range_match.group("start_minute")),
        ),
        tzinfo=timezone,
    )
    end = datetime.combine(
        date_value,
        time(
            int(range_match.group("end_hour")),
            int(range_match.group("end_minute")),
        ),
        tzinfo=timezone,
    )
    if end <= start:
        return None
    return ResolvedIntervalFinal(start=start, end=end)


def resolve_task_due_at_final(case: EvaluationCaseV1) -> datetime | None:
    text = f"{case.email.subject}\n{case.email.body}"
    timezone = ZoneInfo(case.timezone)
    current = case.current_time

    explicit = _DEADLINE_EXPLICIT.search(text)
    if explicit is not None:
        date_value = _explicit_date_value(explicit, current=current)
        return datetime.combine(
            date_value,
            time(int(explicit.group("hour")), int(explicit.group("minute"))),
            tzinfo=timezone,
        )

    if "明天中午前" in text:
        return datetime.combine(
            current.date() + timedelta(days=1),
            time(12, 0),
            tzinfo=timezone,
        )

    work_end = _DEADLINE_WEEKDAY_WORK_END.search(text)
    if work_end is not None:
        date_value = _resolve_weekday(
            current.date(),
            work_end.group("weekday"),
            prefix=_weekday_prefix(work_end.group("weekword")),
        )
        hour, minute = _work_end(case)
        return datetime.combine(
            date_value,
            time(hour, minute),
            tzinfo=timezone,
        )

    weekday_time = _DEADLINE_WEEKDAY_TIME.search(text)
    if weekday_time is not None:
        date_value = _resolve_weekday(
            current.date(),
            weekday_time.group("weekday"),
            prefix=_weekday_prefix(weekday_time.group("weekword")),
        )
        return datetime.combine(
            date_value,
            time(
                int(weekday_time.group("hour")),
                int(weekday_time.group("minute")),
            ),
            tzinfo=timezone,
        )
    return None


def _date_for_position(
    text: str,
    *,
    position: int,
    current: datetime,
) -> date | None:
    explicit_matches = [
        match for match in _EXPLICIT_DATE.finditer(text) if match.start() < position
    ]
    if explicit_matches:
        return _explicit_date_value(explicit_matches[-1], current=current)
    relative_matches = [
        match for match in _RELATIVE_WEEKDAY.finditer(text) if match.start() < position
    ]
    if relative_matches:
        match = relative_matches[-1]
        return _resolve_weekday(
            current.date(),
            match.group("weekday"),
            prefix=match.group("prefix"),
        )
    return None


def _explicit_date_value(
    match: re.Match[str],
    *,
    current: datetime,
) -> date:
    year_group = match.groupdict().get("year")
    year = int(year_group) if year_group else current.year
    value = date(
        year,
        int(match.group("month")),
        int(match.group("day")),
    )
    if year_group is None and value < current.date():
        value = value.replace(year=year + 1)
    return value


def _resolve_weekday(
    current: date,
    weekday_character: str,
    *,
    prefix: str | None,
) -> date:
    target = _WEEKDAY_INDEX[weekday_character]
    current_week_monday = current - timedelta(days=current.weekday())
    if prefix == "本周":
        candidate = current_week_monday + timedelta(days=target)
        if candidate < current:
            candidate += timedelta(days=7)
        return candidate
    if prefix == "下周":
        candidate = current_week_monday + timedelta(days=7 + target)
        # On Sunday, "下周一" can ambiguously mean tomorrow or the Monday
        # after it.  The stage-two convention treats a next-week weekday less
        # than 24 hours away as the following occurrence.
        if candidate <= current + timedelta(days=1):
            candidate += timedelta(days=7)
        return candidate
    days_ahead = (target - current.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return current + timedelta(days=days_ahead)


def _work_end(case: EvaluationCaseV1) -> tuple[int, int]:
    raw = case.user_context.get("work_hours_end", "18:00")
    if not isinstance(raw, str) or not re.fullmatch(r"\d{1,2}:\d{2}", raw):
        return (18, 0)
    hour, minute = raw.split(":", maxsplit=1)
    return (int(hour), int(minute))


def _weekday_prefix(weekword: str) -> str | None:
    return None if weekword == "周" else weekword
