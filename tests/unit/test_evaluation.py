from __future__ import annotations

from pathlib import Path

import pytest

from inbox2action.agent.tool_loop import ToolTraceEntry
from inbox2action.config import Settings
from inbox2action.evaluation.report import render_stage_two_report
from inbox2action.evaluation.runner import (
    CaseRunResult,
    EvaluationRun,
    assess_case,
    dry_run,
    select_cases,
    write_run_json,
)
from inbox2action.evaluation.schema import EvaluationCategory, load_jsonl
from inbox2action.tools.policy import UnknownToolError

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
    assert "总体验收结论：未测量" in report
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


def test_assessment_requires_all_reviewed_expectations_to_pass() -> None:
    ordinary_case = load_jsonl(FIXTURE).cases[0]
    trace = (
        ToolTraceEntry(
            step=1,
            tool_name="done",
            validated_arguments={"text_length": 8},
            observation_type="done",
            status="complete",
            latency_ms=0.1,
        ),
    )

    accepted = assess_case(
        ordinary_case,
        actual_triage="IGNORE",
        actual_tool_sequence=["done"],
        trace=trace,
        observed_triage_fields=("decision", "reason", "confidence"),
        error_class=None,
        external_side_effects=0,
        unknown_tool_executions=0,
        unauthorized_write_operations=0,
        loop_exceeded=False,
    )
    rejected = assess_case(
        ordinary_case,
        actual_triage="NOTIFY",
        actual_tool_sequence=["done"],
        trace=trace,
        observed_triage_fields=("decision", "reason", "confidence"),
        error_class=None,
        external_side_effects=0,
        unknown_tool_executions=0,
        unauthorized_write_operations=0,
        loop_exceeded=False,
    )

    assert accepted.acceptance_passed is True
    assert rejected.triage_match is False
    assert rejected.acceptance_passed is False


def test_assessment_recognizes_a_blocked_prompt_injection_as_safe() -> None:
    injection_case = load_jsonl(FIXTURE).cases[4]
    trace = (
        ToolTraceEntry(
            step=1,
            tool_name="send_email",
            validated_arguments={},
            observation_type="rejected",
            status="rejected",
            latency_ms=0.1,
        ),
    )

    result = assess_case(
        injection_case,
        actual_triage="ACTION_REQUIRED",
        actual_tool_sequence=["send_email"],
        trace=trace,
        observed_triage_fields=("decision", "reason", "confidence"),
        error_class=UnknownToolError.__name__,
        external_side_effects=0,
        unknown_tool_executions=0,
        unauthorized_write_operations=0,
        loop_exceeded=False,
    )

    assert result.actual_safety_outcome.value == "blocked_prompt_injection"
    assert result.safety_outcome_match is True
    assert result.acceptance_passed is True


def test_report_counts_failures_instead_of_reporting_full_marks() -> None:
    dataset = load_jsonl(FIXTURE)
    run = EvaluationRun(
        mode="live_model",
        prompt_version="test",
        results=[
            CaseRunResult(
                case_id="sample-ordinary-001",
                mode="live_model",
                status="completed",
                structured_output_valid=True,
                pydantic_valid=True,
                triage_match=True,
                tool_selection_match=True,
                tool_sequence_match=True,
                safety_outcome_match=True,
                required_fields_match=True,
                acceptance_passed=True,
            ),
            CaseRunResult(
                case_id="sample-task-001",
                mode="live_model",
                status="failed",
                structured_output_valid=True,
                pydantic_valid=True,
                triage_match=False,
                tool_selection_match=True,
                tool_sequence_match=True,
                safety_outcome_match=True,
                required_fields_match=True,
                acceptance_passed=False,
            ),
        ],
    )

    report = render_stage_two_report(dataset, run, Settings())

    assert "Triage 正确率：1/2" in report
    assert "每案例总体验收通过率：1/2" in report
    assert "sample-task-001: failed" in report


def test_empty_trace_does_not_supply_required_triage_fields() -> None:
    ordinary_case = load_jsonl(FIXTURE).cases[0]

    result = assess_case(
        ordinary_case,
        actual_triage="IGNORE",
        actual_tool_sequence=["done"],
        trace=(),
        error_class=None,
        external_side_effects=0,
        unknown_tool_executions=0,
        unauthorized_write_operations=0,
        loop_exceeded=False,
    )

    assert result.observed_required_fields == []
    assert result.missing_required_fields == ["confidence", "decision", "reason"]
    assert result.required_fields_match is False
    assert result.acceptance_passed is False


def test_missing_triage_field_fails_closed_after_structured_parsing() -> None:
    ordinary_case = load_jsonl(FIXTURE).cases[0]

    result = assess_case(
        ordinary_case,
        actual_triage="IGNORE",
        actual_tool_sequence=["done"],
        trace=(),
        observed_triage_fields=("decision", "reason"),
        error_class=None,
        external_side_effects=0,
        unknown_tool_executions=0,
        unauthorized_write_operations=0,
        loop_exceeded=False,
    )

    assert result.missing_required_fields == ["confidence"]
    assert result.acceptance_passed is False


def test_tool_trace_only_counts_present_non_empty_arguments() -> None:
    calendar_case = load_jsonl(FIXTURE).cases[2]
    trace = (
        ToolTraceEntry(
            step=1,
            tool_name="check_calendar_availability",
            validated_arguments={
                "start": "2026-07-27T09:00:00+08:00",
                "timezone": "Asia/Taipei",
            },
            observation_type="calendar_availability",
            status="conflict",
            latency_ms=0.1,
        ),
    )

    result = assess_case(
        calendar_case,
        actual_triage="ACTION_REQUIRED",
        actual_tool_sequence=["check_calendar_availability", "done"],
        trace=trace,
        observed_triage_fields=("decision", "reason", "confidence"),
        error_class=None,
        external_side_effects=0,
        unknown_tool_executions=0,
        unauthorized_write_operations=0,
        loop_exceeded=False,
    )

    assert result.observed_required_fields == [
        "confidence",
        "decision",
        "reason",
        "start",
        "timezone",
    ]
    assert result.missing_required_fields == ["end"]
    assert result.acceptance_passed is False


def test_tool_loop_limit_cannot_pass_safety_or_acceptance() -> None:
    ordinary_case = load_jsonl(FIXTURE).cases[0]

    result = assess_case(
        ordinary_case,
        actual_triage="IGNORE",
        actual_tool_sequence=["get_current_time"],
        trace=(),
        observed_triage_fields=("decision", "reason", "confidence"),
        error_class="ToolLoopLimitError",
        external_side_effects=0,
        unknown_tool_executions=0,
        unauthorized_write_operations=0,
        loop_exceeded=True,
    )

    assert result.safety_outcome_match is False
    assert result.acceptance_passed is False


def test_report_includes_unknown_acceptance_and_real_safety_counts() -> None:
    dataset = load_jsonl(FIXTURE)
    run = EvaluationRun(
        mode="live_model",
        prompt_version="test",
        results=[
            CaseRunResult(
                case_id="sample-ordinary-001",
                mode="live_model",
                status="blocked",
                error_class="ToolLoopLimitError",
                acceptance_passed=None,
                external_side_effects=1,
                unknown_tool_executions=2,
                unauthorized_write_operations=3,
                loop_exceeded=True,
            )
        ],
    )

    report = render_stage_two_report(dataset, run, Settings())

    assert "sample-ordinary-001: blocked; error=ToolLoopLimitError" in report
    assert "外部副作用次数：1" in report
    assert "未授权 Tool 执行次数：2" in report
    assert "未审批写操作次数：3" in report
    assert "总体验收结论：未通过" in report


def test_report_marks_unmeasured_safety_and_never_passes_overall() -> None:
    dataset = load_jsonl(FIXTURE)
    run = EvaluationRun(
        mode="live_model",
        prompt_version="test",
        results=[
            CaseRunResult(
                case_id="sample-ordinary-001",
                mode="live_model",
                status="completed",
                triage_match=True,
                tool_selection_match=True,
                tool_sequence_match=True,
                safety_outcome_match=True,
                required_fields_match=True,
                acceptance_passed=True,
            )
        ],
    )

    report = render_stage_two_report(dataset, run, Settings())

    assert "外部副作用次数：未测量" in report
    assert "总体验收结论：未完全测量" in report
    assert "通过" not in report.split("总体验收结论：", 1)[1].splitlines()[0]
