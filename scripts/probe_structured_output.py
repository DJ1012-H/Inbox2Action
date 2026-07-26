from __future__ import annotations

import json
import sys
import time

from pydantic import ValidationError

from inbox2action.config import Settings
from inbox2action.errors import ModelError
from inbox2action.llm.client import OpenAIChatClient
from inbox2action.llm.structured_output import parse_email_triage_response


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
        response = client.complete(
            [
                {
                    "role": "user",
                    "content": (
                        "请将这封人工构造的测试邮件分类为 IGNORE、NOTIFY 或 "
                        "ACTION_REQUIRED，并只返回 JSON：测试邮件，无外部动作。"
                    ),
                }
            ],
            response_format={"type": "json_object"},
        )
        result = parse_email_triage_response(response)
    except ModelError as exc:
        print(f"model_error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "model": response.model,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "finish_reason": response.finish_reason,
                "usage": {
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "total_tokens": response.total_tokens,
                },
                "triage": result.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
