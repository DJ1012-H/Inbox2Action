"""Model boundary and structured-output helpers."""

from inbox2action.llm.client import OpenAIChatClient
from inbox2action.llm.models import (
    ChatCompletionResult,
    EmailTriageResult,
    TriageDecision,
)
from inbox2action.llm.structured_output import parse_email_triage_response

__all__ = [
    "ChatCompletionResult",
    "EmailTriageResult",
    "OpenAIChatClient",
    "TriageDecision",
    "parse_email_triage_response",
]
