from __future__ import annotations

from pydantic import JsonValue

from inbox2action.evaluation.matching_final import arguments_satisfy_final


def test_natural_language_title_allows_equivalent_concise_wording() -> None:
    assertions: dict[str, dict[str, JsonValue]] = {
        "save_task_proposal": {
            "title": "整理 Atlas 风险清单",
            "description": {"$contains_all": ["Atlas", "风险清单"]},
            "due_at": "2026-07-30T18:00:00+08:00",
            "priority": "high",
        }
    }
    observed = [
        (
            1,
            "save_task_proposal",
            {
                "title": "Atlas 风险清单整理",
                "description": "请整理 Atlas 的风险清单并确认。",
                "due_at": "2026-07-30T18:00:00+08:00",
                "priority": "high",
            },
        )
    ]

    assert arguments_satisfy_final(assertions, observed) is True


def test_structured_datetime_and_priority_remain_strict() -> None:
    assertions: dict[str, dict[str, JsonValue]] = {
        "save_task_proposal": {
            "title": "整理 Atlas 风险清单",
            "due_at": "2026-07-30T18:00:00+08:00",
            "priority": "high",
        }
    }
    observed = [
        (
            1,
            "save_task_proposal",
            {
                "title": "整理 Atlas 风险清单",
                "due_at": "2026-07-30T17:00:00+08:00",
                "priority": "medium",
            },
        )
    ]

    assert arguments_satisfy_final(assertions, observed) is False


def test_contains_all_normalizes_case_spacing_and_punctuation() -> None:
    assertions: dict[str, dict[str, JsonValue]] = {
        "save_reply_draft": {
            "body": {"$contains_all": ["Qilin", "已收到"]},
        }
    }
    observed = [
        (
            1,
            "save_reply_draft",
            {"body": "QILIN，材料已 收到；稍后核对。"},
        )
    ]

    assert arguments_satisfy_final(assertions, observed) is True


def test_revealed_legacy_contains_all_string_is_one_diagnostic_fragment() -> None:
    assertions: dict[str, dict[str, JsonValue]] = {
        "save_task_proposal": {
            "description": {"$contains_all": "Atlas 测试包"},
        }
    }
    observed = [
        (
            1,
            "save_task_proposal",
            {"description": "核对 Atlas 测试包并记录结果。"},
        )
    ]

    assert arguments_satisfy_final(assertions, observed) is True
