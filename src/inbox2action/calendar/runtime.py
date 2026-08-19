"""Tool runtime that keeps FreeBusy observations and proposals separate."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from inbox2action.tools.mock_tools import MockToolRuntime, ToolObservation
from inbox2action.tools.schemas import (
    CheckCalendarAvailabilityArgs,
    SaveCalendarProposalArgs,
)

from .availability import CalendarAvailability, FreeBusyAdapter


class CalendarToolRuntime(MockToolRuntime):
    """Use a supplied adapter for reads and retain writes as local proposals."""

    def __init__(
        self,
        adapter: FreeBusyAdapter,
        *,
        timezone: str = "Asia/Shanghai",
        authorized_intervals: Sequence[tuple[datetime, datetime]] = (),
    ) -> None:
        super().__init__()
        self._adapter = adapter
        self.timezone = timezone
        self._authorized_intervals = tuple(authorized_intervals)
        self._last_check: tuple[datetime, datetime, CalendarAvailability] | None = None

    def check_calendar_availability(
        self,
        arguments: CheckCalendarAvailabilityArgs,
    ) -> ToolObservation:
        if arguments.timezone != self.timezone:
            return _calendar_error_observation(arguments, "trusted_timezone_mismatch")
        if not self._authorized_intervals or not _matches_any(
            arguments.start, arguments.end, self._authorized_intervals
        ):
            self._last_check = (
                arguments.start,
                arguments.end,
                CalendarAvailability(
                    available=False,
                    timezone=self.timezone,
                    error_code="candidate_not_authorized",
                ),
            )
            return _calendar_error_observation(arguments, "candidate_not_authorized")

        result = self._adapter.check(
            start=arguments.start,
            end=arguments.end,
            timezone=arguments.timezone,
        )
        self._last_check = (arguments.start, arguments.end, result)
        if result.error_code is not None:
            return _calendar_error_observation(arguments, result.error_code)
        if result.available:
            return ToolObservation(
                tool_name="check_calendar_availability",
                observation_type="calendar_availability",
                status="ok",
                data={
                    "available": True,
                    "conflict": False,
                    "timezone": result.timezone,
                },
            )
        return ToolObservation(
            tool_name="check_calendar_availability",
            observation_type="calendar_availability",
            status="conflict",
            data={
                "available": False,
                "conflict": True,
                "timezone": result.timezone,
                "busy_interval_count": len(result.busy_intervals),
            },
        )

    def save_calendar_proposal(
        self,
        arguments: SaveCalendarProposalArgs,
    ) -> ToolObservation:
        last_check = self._last_check
        if (
            last_check is None
            or not last_check[2].available
            or last_check[0] != arguments.start_time
            or last_check[1] != arguments.end_time
            or arguments.timezone != self.timezone
        ):
            raise ValueError("calendar proposal requires a matching FREE observation")
        return super().save_calendar_proposal(arguments)

    def set_authorized_intervals(
        self, intervals: Sequence[tuple[datetime, datetime]]
    ) -> None:
        self._authorized_intervals = tuple(intervals)


def _calendar_error_observation(
    arguments: CheckCalendarAvailabilityArgs,
    error_code: str,
) -> ToolObservation:
    return ToolObservation(
        tool_name="check_calendar_availability",
        observation_type="calendar_availability_error",
        status="conflict",
        data={
            "available": False,
            "conflict": True,
            "provider_error": True,
            "error_code": error_code,
            "timezone": arguments.timezone,
        },
    )


def _matches_any(
    start: datetime,
    end: datetime,
    candidates: Sequence[tuple[datetime, datetime]],
) -> bool:
    return any(start == candidate_start and end == candidate_end for candidate_start, candidate_end in candidates)
