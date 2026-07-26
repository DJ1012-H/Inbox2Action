from __future__ import annotations

import os

import pytest

from inbox2action.config import Settings
from inbox2action.llm.client import OpenAIChatClient


def integration_enabled() -> bool:
    return (
        os.getenv("RUN_DEEPSEEK_INTEGRATION_TESTS", "").lower() == "true"
        and os.getenv("LLM_ENABLED", "").lower() == "true"
        and bool(os.getenv("LLM_API_KEY", ""))
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not integration_enabled(),
    reason="DeepSeek integration requires explicit opt-in and a configured key",
)
def test_deepseek_chat_integration_is_explicitly_opt_in() -> None:
    settings = Settings()
    client = OpenAIChatClient(settings)
    result = client.complete(
        [{"role": "user", "content": "请用中文回答：什么是安全测试？"}]
    )
    assert isinstance(result.content, str)
    assert result.content.strip()
