from __future__ import annotations

import pytest

from inbox2action.compat.langchain_openai_probe import (
    bind_allowlisted_tools,
    build_chat_openai,
)
from inbox2action.config import Settings
from inbox2action.tools.registry import ToolRegistry

pytest.importorskip("langchain_openai")


def test_langchain_probe_uses_shared_settings_without_network() -> None:
    settings = Settings(LLM_ENABLED=True, LLM_API_KEY="placeholder-only")
    chat_model = build_chat_openai(settings)
    assert chat_model.model_name == settings.llm_model_name
    assert chat_model.openai_api_base == settings.llm_base_url
    assert chat_model.max_retries == settings.llm_max_retries


def test_langchain_probe_binds_only_allowlisted_tool_schemas() -> None:
    settings = Settings(LLM_ENABLED=True, LLM_API_KEY="placeholder-only")
    bound = bind_allowlisted_tools(build_chat_openai(settings), ToolRegistry())
    names = {
        tool["function"]["name"]
        for tool in bound.kwargs["tools"]
        if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
    }
    assert names == {
        "get_current_time",
        "check_calendar_availability",
        "save_reply_draft",
        "ask_user",
        "done",
    }
