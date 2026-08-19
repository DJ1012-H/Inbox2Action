from __future__ import annotations

import json
from collections.abc import Mapping

from pydantic import BaseModel

ALLOWED_TOOL_NAMES = frozenset(
    {
        "get_current_time",
        "check_calendar_availability",
        "save_reply_draft",
        "save_task_proposal",
        "save_calendar_proposal",
        "ask_user",
        "done",
    }
)


class ToolError(Exception):
    """Base class for safe, actionable tool-boundary errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.trace: tuple[object, ...] = ()


class UnknownToolError(ToolError):
    """The requested name is not on the allowlist."""


class InvalidToolArgumentsError(ToolError):
    """Arguments failed JSON or Pydantic validation."""


class ToolExecutionError(ToolError):
    """A validated Mock Tool raised during execution."""


class ObservationValidationError(ToolError):
    """A tool did not return the required observation shape."""


class ToolIdMismatchError(ToolError):
    """The observation did not match the originating tool call."""


def require_allowed_tool(name: str) -> None:
    if name not in ALLOWED_TOOL_NAMES:
        raise UnknownToolError("Tool is not allowlisted.")


def canonical_arguments(arguments: BaseModel) -> str:
    return json.dumps(
        arguments.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def trace_arguments(name: str, arguments: BaseModel) -> Mapping[str, object]:
    """Return validated but redacted arguments for a public execution trace."""

    payload = arguments.model_dump(mode="json")
    if name == "save_reply_draft":
        return {
            "recipient_present": bool(payload.get("recipient")),
            "subject_length": len(str(payload.get("subject", ""))),
            "body_length": len(str(payload.get("body", ""))),
        }
    if name == "save_task_proposal":
        return {
            "title_length": len(str(payload.get("title", ""))),
            "description_length": len(str(payload.get("description", ""))),
            "due_at_present": payload.get("due_at") is not None,
            "priority": payload.get("priority"),
        }
    if name == "save_calendar_proposal":
        return {
            "summary_length": len(str(payload.get("summary", ""))),
            "description_length": len(str(payload.get("description", "") or "")),
            "start_time": payload.get("start_time"),
            "end_time": payload.get("end_time"),
            "timezone": payload.get("timezone"),
            "location_present": bool(payload.get("location")),
        }
    if name in {"ask_user", "done"}:
        text = payload.get("question", payload.get("summary", ""))
        return {"text_length": len(str(text))}
    return payload
