from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from inbox2action.llm.models import ChatCompletionResult

ChatMessage = Mapping[str, object]


class ChatClientPort(Protocol):
    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        """Return a normalized completion without exposing SDK objects."""
