from __future__ import annotations

from pathlib import Path

import pytest

from inbox2action.config import Settings
from inbox2action.evaluation.report import render_stage_two_report
from inbox2action.evaluation.runner import dry_run, select_cases, write_run_json
from inbox2action.evaluation.schema import EvaluationCategory, load_jsonl

PROJECT_ROOT = Path(__file__).parents[2]
FIXTURE = PROJECT_ROOT / "evaluation" / "fixtures" / "checkpoint-3-sample.jsonl"


def test_sample_fixture_is_strict_and_covers_each_checkpoint_three_category() -> None:
    dataset = load_jsonl(FIXTURE)
    assert len(dataset.cases) == 5
    assert {case.category for case in dataset.cases} == {
        EvaluationCategory.ORDINARY,
        EvaluationCategory.TASK,
        EvaluationCategory.SCHEDULE,
        EvaluationCategory.MULTI_ACTION,
        EvaluationCategory.PROMPT_INJECTION,
    }


def test_evaluation_selection_is_bounded_and_filterable() -> None:
    dataset = load_jsonl(FIXTURE)
    selected = select_cases(
        dataset,
        limit=1,
        category=EvaluationCategory.SCHEDULE.value,
    )
    assert len(selected) == 1
    assert selected[0].category is EvaluationCategory.SCHEDULE

    with pytest.raises(ValueError):
        select_cases(dataset, limit=61)


def test_dry_run_has_no_model_result_and_report_does_not_claim_acceptance() -> None:
    dataset = load_jsonl(FIXTURE)
    run = dry_run(dataset.cases)
    report = render_stage_two_report(
        dataset,
        run,
        Settings(),
    )

    assert all(result.status == "not_executed" for result in run.results)
    assert "未完成" in report
    assert "不得进入阶段三" in report
    assert "Structured Output 通过率：未测量" in report


def test_evaluation_results_cannot_escape_ignored_results_directory(
    tmp_path: Path,
) -> None:
    dataset = load_jsonl(FIXTURE)
    run = dry_run(dataset.cases[:1])

    with pytest.raises(ValueError):
        write_run_json(run, tmp_path / "outside.json", project_root=PROJECT_ROOT)

    destination = write_run_json(
        run,
        PROJECT_ROOT / "evaluation" / "results" / "unit-test.json",
        project_root=PROJECT_ROOT,
    )
    assert destination.exists()
    destination.unlink()
