from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from inbox2action.config import Settings
from inbox2action.errors import ModelNotConfiguredError
from inbox2action.tools.registry import ToolRegistry


def build_chat_openai(settings: Settings) -> Any:
    """Build only an optional compatibility object from the shared Settings."""

    if (
        not settings.llm_enabled
        or not settings.api_key_configured
        or settings.llm_api_key is None
    ):
        raise ModelNotConfiguredError(
            "The optional LangChain probe requires explicit model configuration."
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.llm_model_name,
        api_key=SecretStr(settings.llm_api_key.get_secret_value()),
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        temperature=0,
    )


def bind_allowlisted_tools(chat_model: Any, registry: ToolRegistry) -> Any:
    """Bind only the existing Tool Registry schema; no second policy is defined."""

    return chat_model.bind_tools(registry.openai_tools())
