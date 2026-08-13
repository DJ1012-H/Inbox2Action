from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict

from inbox2action.stage3.contracts import ExecutionPermit, ExecutionResult
from inbox2action.stage3.workflow import Stage3WorkflowError

READ_TOOL_NAMES = frozenset(
    {
        "get_current_time",
        "get_email_thread",
        "read_user_preferences",
        "check_calendar_availability",
    }
)


class FixtureToolError(Stage3WorkflowError):
    """A deterministic fixture rejected a scoped request."""


class UnknownFixtureToolError(FixtureToolError):
    """The requested fixture capability is not allowlisted."""


class FixtureObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    status: Literal["ok", "conflict"]
    data: dict[str, object]


class FixtureToolAdapter:
    """Provider-neutral deterministic read fixtures."""

    def __init__(self, *, thread_id: str) -> None:
        self.thread_id = thread_id
        self.read_calls: list[str] = []

    def read(
        self,
        tool_name: str,
        parameters: Mapping[str, object],
    ) -> FixtureObservation:
        if tool_name not in READ_TOOL_NAMES:
            raise UnknownFixtureToolError("fixture read Tool is not allowlisted")
        data: dict[str, object]
        if tool_name == "get_current_time":
            _require_exact_keys(tool_name, parameters, ())
            data = {"now": "2026-08-09T09:00:00+08:00", "timezone": "Asia/Shanghai"}
        elif tool_name == "get_email_thread":
            _require_exact_keys(tool_name, parameters, ("thread_id",))
            if parameters["thread_id"] != self.thread_id:
                raise FixtureToolError("email thread is outside current workflow")
            data = {"thread_id": self.thread_id, "message_count": 1}
        elif tool_name == "read_user_preferences":
            _require_exact_keys(tool_name, parameters, ())
            data = {"timezone": "Asia/Shanghai", "reply_style": "concise"}
        else:
            _require_exact_keys(tool_name, parameters, ("start", "end"))
            if not all(isinstance(parameters[key], str) for key in ("start", "end")):
                raise FixtureToolError("calendar interval must use ISO strings")
            data = {"available": True, "conflict": False}
        self.read_calls.append(tool_name)
        return FixtureObservation(tool_name=tool_name, status="ok", data=data)


class FixtureWriteExecutor:
    """Observable local write executor used after approval and ledger claim."""

    def __init__(
        self,
        *,
        outcome: Literal["succeeded", "failed", "unknown"] = "succeeded",
    ) -> None:
        self.outcome = outcome
        self.calls: list[ExecutionPermit] = []

    async def execute(self, permit: ExecutionPermit) -> ExecutionResult:
        self.calls.append(permit)
        error_code = None if self.outcome == "succeeded" else f"fixture_{self.outcome}"
        return ExecutionResult(status=self.outcome, error_code=error_code)


def _require_exact_keys(
    tool_name: str,
    parameters: Mapping[str, object],
    required: tuple[str, ...],
) -> None:
    if set(parameters) != set(required):
        raise FixtureToolError(f"{tool_name} parameters are outside its fixture schema")
