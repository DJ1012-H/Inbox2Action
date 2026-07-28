"""Safe helpers for the explicit, five-case DeepSeek Pilot baseline."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from urllib.parse import urlsplit

from inbox2action.config import Settings
from inbox2action.evaluation.runner_v1 import PilotCaseRunResultV1, PilotEvaluationRunV1

PILOT_BASELINE_CASE_IDS = (
    "ordinary_simple_confirmation_001",
    "task_relative_deadline_001",
    "calendar_conflict_001",
    "multi_task_calendar_001",
    "injection_fake_observation_001",
)


class LivePilotRequestError(ValueError):
    """The explicit live-run authorization or fixed baseline was not provided."""


class LivePilotConfigurationError(ValueError):
    """A required model setting was unavailable before client construction."""

    def __init__(self, missing: Sequence[str]) -> None:
        self.missing = tuple(missing)
        super().__init__("missing required model configuration")


def validate_live_pilot_request(
    *,
    live_model: bool,
    confirm_api_cost: bool,
    case_ids: Sequence[str],
    failure_mode: str,
) -> tuple[str, ...]:
    """Require two explicit flags and exactly the approved first-run baseline."""

    if not live_model or not confirm_api_cost:
        raise LivePilotRequestError(
            "real model calls require both --live-model and --confirm-api-cost"
        )
    selected = tuple(case_ids)
    if selected != PILOT_BASELINE_CASE_IDS:
        raise LivePilotRequestError(
            "the DeepSeek Pilot requires exactly the five documented --case-id values"
        )
    if failure_mode != "continue":
        raise LivePilotRequestError("the DeepSeek Pilot requires --failure-mode continue")
    return selected


def validate_live_pilot_settings(settings: Settings) -> None:
    """Check configuration presence without returning or rendering secret values."""

    missing = []
    if not settings.llm_enabled:
        missing.append("LLM_ENABLED")
    if not settings.api_key_configured:
        missing.append("LLM_API_KEY")
    if not settings.llm_model_name:
        missing.append("LLM_MODEL_NAME")
    if not settings.llm_base_url:
        missing.append("LLM_BASE_URL")
    if missing:
        raise LivePilotConfigurationError(missing)


def redacted_pilot_summary(run: PilotEvaluationRunV1) -> dict[str, int | float]:
    """Aggregate only safe Runner fields for a terminal summary."""

    results = run.results
    return {
        "case_count": len(results),
        "accepted_count": _count(results, lambda result: result.acceptance_passed is True),
        "infrastructure_error_count": _count(
            results, lambda result: result.status == "infrastructure_error"
        ),
        "triage_accuracy": _rate(results, lambda result: result.triage_correct is True),
        "tool_selection_accuracy": _rate(
            results, lambda result: result.tool_selection_correct is True
        ),
        "tool_sequence_accuracy": _rate(
            results, lambda result: result.tool_sequence_correct is True
        ),
        "arguments_valid_rate": _rate(
            results, lambda result: result.arguments_valid is True
        ),
        "fixture_resolution_rate": _rate(
            results, lambda result: result.fixture_resolution_passed is True
        ),
        "tool_boundary_safety_pass_rate": _rate(
            results, lambda result: result.safety_passed is True
        ),
        "external_side_effects": _sum_metric(results, "external_side_effects"),
        "unknown_tool_executions": _sum_metric(results, "unknown_tool_executions"),
        "loop_exceeded_count": _count(results, lambda result: result.loop_exceeded is True),
        "total_tokens": sum(result.total_tokens for result in results),
        "average_latency_ms": _average_latency(results),
    }


def render_deepseek_pilot_summary(
    run: PilotEvaluationRunV1,
    settings: Settings,
    *,
    run_date: date,
) -> str:
    """Render commit-safe evidence without email, Tool payloads, or model content."""

    summary = redacted_pilot_summary(run)
    host = urlsplit(settings.llm_base_url).hostname or "unknown"
    rows = "\n".join(_case_row(result) for result in run.results)
    failures = _failure_summary(run.results)
    return f"""# DeepSeek Pilot v1 Baseline Summary

## Run scope

- Run date: `{run_date.isoformat()}`
- Model: `{settings.llm_model_name}`
- Base URL hostname: `{host}`
- Prompt version: `{run.prompt_version}`
- Thinking mode: `{settings.llm_thinking_mode}`
- Cases: {", ".join(f"`{case_id}`" for case_id in PILOT_BASELINE_CASE_IDS)}

This is a five-case DeepSeek Pilot baseline. It is not the complete 15-case
evaluation and not the complete 60-case formal validation. Prompt Injection is
currently scored only for Tool Boundary Safety; user-visible refusal quality is
not automatically scored.

## Per-case results

| case_id | triage | selection | sequence | arguments | fixture | safety | acceptance | error_class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
{rows}

## Aggregate results

- accepted_count: `{summary["accepted_count"]}/{summary["case_count"]}`
- triage_accuracy: `{summary["triage_accuracy"]}`
- tool_selection_accuracy: `{summary["tool_selection_accuracy"]}`
- tool_sequence_accuracy: `{summary["tool_sequence_accuracy"]}`
- arguments_valid_rate: `{summary["arguments_valid_rate"]}`
- fixture_resolution_rate: `{summary["fixture_resolution_rate"]}`
- tool_boundary_safety_pass_rate: `{summary["tool_boundary_safety_pass_rate"]}`
- infrastructure_error_count: `{summary["infrastructure_error_count"]}`
- loop_exceeded_count: `{summary["loop_exceeded_count"]}`
- total_tokens: `{summary["total_tokens"]}`
- average_latency_ms: `{summary["average_latency_ms"]}`

## Failure summary

{failures}

The saved run result and this evidence intentionally omit email bodies, complete
Tool arguments, Tool Observations, API keys, authorization values,
reasoning_content, hidden reasoning, and raw HTTP payloads.
"""


def _case_row(result: PilotCaseRunResultV1) -> str:
    return "| {case_id} | {triage} | {selection} | {sequence} | {arguments} | {fixture} | {safety} | {acceptance} | {error} |".format(
        case_id=result.case_id,
        triage=_display_bool(result.triage_correct),
        selection=_display_bool(result.tool_selection_correct),
        sequence=_display_bool(result.tool_sequence_correct),
        arguments=_display_bool(result.arguments_valid),
        fixture=_display_bool(result.fixture_resolution_passed),
        safety=_display_bool(result.safety_passed),
        acceptance=_display_bool(result.acceptance_passed),
        error=result.error_class or "-",
    )


def _failure_summary(results: Sequence[PilotCaseRunResultV1]) -> str:
    failures = [result for result in results if result.acceptance_passed is not True]
    if not failures:
        return "No failed cases."
    return "\n".join(
        "- `{case_id}`: {classification}; error_class=`{error}`; failure_reasons=`{reasons}`".format(
            case_id=result.case_id,
            classification=_failure_classification(result),
            error=result.error_class or "none",
            reasons=", ".join(result.failure_reasons) or "none",
        )
        for result in failures
    )


def _failure_classification(result: PilotCaseRunResultV1) -> str:
    infrastructure_errors = {
        "ModelNotConfiguredError",
        "ModelAuthenticationError",
        "ModelTimeoutError",
        "ModelRateLimitedError",
        "ModelUnavailableError",
        "ModelInvalidRequestError",
        "ModelProtocolError",
    }
    if result.status == "infrastructure_error" or result.error_class in infrastructure_errors:
        return "B. infrastructure failure"
    return "A. model capability failure"


def _count(
    results: Sequence[PilotCaseRunResultV1],
    predicate: Callable[[PilotCaseRunResultV1], bool],
) -> int:
    return sum(predicate(result) for result in results)


def _rate(
    results: Sequence[PilotCaseRunResultV1],
    predicate: Callable[[PilotCaseRunResultV1], bool],
) -> float:
    return _count(results, predicate) / len(results) if results else 0.0


def _sum_metric(results: Sequence[PilotCaseRunResultV1], attribute: str) -> int:
    values = [getattr(result, attribute) for result in results]
    if any(value is None for value in values):
        return -1
    return sum(values)


def _average_latency(results: Sequence[PilotCaseRunResultV1]) -> float:
    measurements = [result.elapsed_ms for result in results if result.elapsed_ms is not None]
    return round(sum(measurements) / len(measurements), 3) if measurements else 0.0


def _display_bool(value: bool | None) -> str:
    return "true" if value is True else "false" if value is False else "unmeasured"
