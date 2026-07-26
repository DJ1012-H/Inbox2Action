from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FailureMetadata:
    """Safe metadata for an output failure; it never stores raw content."""

    error_type: str
    content_length: int
    content_sha256: str


class ModelError(Exception):
    """Base class for errors exposed by the model boundary."""

    def __init__(
        self,
        message: str,
        *,
        metadata: FailureMetadata | None = None,
    ) -> None:
        super().__init__(message)
        self.metadata = metadata


class ModelNotConfiguredError(ModelError):
    """The model is disabled or lacks a key."""


class ModelAuthenticationError(ModelError):
    """The provider rejected authentication."""


class ModelTimeoutError(ModelError):
    """The provider request exceeded its timeout."""


class ModelRateLimitedError(ModelError):
    """The provider rate-limited the request."""


class ModelUnavailableError(ModelError):
    """The provider or network was unavailable."""


class ModelInvalidRequestError(ModelError):
    """The provider rejected the request as invalid."""


class ModelProtocolError(ModelError):
    """The SDK response did not have the expected shape."""


class ModelReasoningProtocolError(ModelProtocolError):
    """Thinking-mode tool responses lacked the required reasoning payload."""


class ModelEmptyResponseError(ModelError):
    """The provider returned no usable text response."""


class ModelOutputValidationError(ModelError):
    """The model output was not valid for the requested schema."""
