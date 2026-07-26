from __future__ import annotations

import json
import sys
import time

from pydantic import ValidationError

from inbox2action.config import Settings
from inbox2action.errors import ModelError
from inbox2action.llm.client import OpenAIChatClient


def main() -> int:
    try:
        settings = Settings()
    except ValidationError:
        print("Invalid model configuration.", file=sys.stderr)
        return 2

    client = OpenAIChatClient(settings)
    if not client.is_configured:
        print("Model is disabled or missing LLM_API_KEY.", file=sys.stderr)
        return 2

    started = time.perf_counter()
    try:
        result = client.complete(
            [
                {
                    "role": "user",
                    "content": "请用中文简短回答：什么是安全的增量开发？",
                }
            ]
        )
    except ModelError as exc:
        print(f"model_error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    print(
        json.dumps(
            {
                "model": result.model,
                "elapsed_ms": elapsed_ms,
                "finish_reason": result.finish_reason,
                "usage": {
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "total_tokens": result.total_tokens,
                },
                "content": result.content,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
