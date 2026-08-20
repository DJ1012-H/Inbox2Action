"""Authorized DeepSeek observed evaluation for the Stage 10 vNext corpus.

This module is the only live boundary for the Stage 10 benchmark.  It sends
normalized synthetic email content to the configured model and executes only
the existing local proposal/read tools.  Provider capability names in the
dataset are mapped to those local proposal tools for scoring; no ClickUp or
Google Calendar provider adapter is constructed here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from urllib.parse import urlsplit

from pydantic import BaseModel

from inbox2action.agent.tool_loop import ToolLoop, ToolLoopError, ToolTraceEntry
from inbox2action.config import Settings
from inbox2action.errors import ModelError
from inbox2action.evaluation.dataset_vnext import (
    EmailDatasetCaseVNext,
    ProviderFixtureVNext,
)
from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
)
from inbox2action.evaluation.stage10 import (
    audit_dataset,
    classification_metrics,
    critical_argument_metrics,
    security_metrics,
    temporal_metrics,
    tool_selection_metrics,
    trajectory_metrics,
)
from inbox2action.evaluation.temporal_final import (
    resolve_calendar_interval_final,
    resolve_task_due_at_final,
)
from inbox2action.evaluation.triage_final import (
    build_tool_messages_final,
    build_triage_messages_final,
    detect_prompt_injection_final,
    enforce_triage_final,
    parse_triage_response_final,
)
from inbox2action.llm.client import OpenAIChatClient
from inbox2action.llm.models import ChatCompletionResult, TriageDecision
from inbox2action.stage3 import EmailEnvelope, normalize_email
from inbox2action.tools.mock_tools import MockToolRuntime, ToolObservation
from inbox2action.tools.policy import ToolError
from inbox2action.tools.registry import ToolRegistry, ValidatedToolCall

DATASET_VERSION = (
    "sha256:dc5c854479f078836b7ebeb4e9c8a154c8c55e547f2995b0237996c3861a1614"
)
OBSERVED_SCHEMA_VERSION = "stage10-observed-v1"

_CAPABILITY_TO_LOCAL_TOOL = {
    "create_clickup_task": "save_task_proposal",
    "create_calendar_event": "save_calendar_proposal",
}
_LOCAL_TOOL_TO_CAPABILITY = {
    value: key for key, value in _CAPABILITY_TO_LOCAL_TOOL.items()
}
_LOCAL_TOOL_TO_CAPABILITY.update(
    {
        "check_calendar_availability": "check_calendar_availability",
        "save_reply_draft": "save_reply_draft",
        "ask_user": "ask_user",
    }
)
_PROPOSAL_TOOLS = frozenset(
    {"save_reply_draft", "save_task_proposal", "save_calendar_proposal"}
)
_TEMPORAL_TAGS = frozenset(
    {"absolute_datetime", "relative_datetime", "timezone", "conflict_replan"}
)


@dataclass(frozen=True)
class _TemporalEmail:
    subject: str
    body: str


@dataclass(frozen=True)
class _TemporalCase:
    email: _TemporalEmail
    current_time: datetime
    timezone: str
    user_context: Mapping[str, object]


class _MeasuredClient:
    def __init__(self, delegate: OpenAIChatClient) -> None:
        self._delegate = delegate
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        response = self._delegate.complete(
            messages, response_format=response_format, tools=tools
        )
        self.prompt_tokens += response.prompt_tokens or 0
        self.completion_tokens += response.completion_tokens or 0
        self.total_tokens += response.total_tokens or 0
        return response


class _ObservedCandidateModel:
    """Reuse the existing final-candidate deterministic argument normalization."""

    def __init__(
        self,
        delegate: _MeasuredClient,
        case: EmailDatasetCaseVNext,
        email: Mapping[str, object],
    ) -> None:
        self._delegate = delegate
        self._case = case
        self._email = email

    def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        response = self._delegate.complete(
            messages, response_format=response_format, tools=tools
        )
        if tools is None or len(response.tool_calls) != 1:
            return response
        call = response.tool_calls[0]
        try:
            payload = json.loads(call.arguments)
        except (TypeError, json.JSONDecodeError):
            return response
        if not isinstance(payload, dict):
            return response
        normalized = dict(payload)
        temporal_case = _temporal_case(self._case)
        if call.name == "check_calendar_availability":
            interval = resolve_calendar_interval_final(cast(Any, temporal_case))
            if interval is not None:
                normalized.update(
                    {
                        "start": interval.start.isoformat(),
                        "end": interval.end.isoformat(),
                        "timezone": self._case.timezone,
                    }
                )
        elif call.name == "save_calendar_proposal":
            interval = resolve_calendar_interval_final(cast(Any, temporal_case))
            if interval is not None:
                normalized.update(
                    {
                        "start_time": interval.start.isoformat(),
                        "end_time": interval.end.isoformat(),
                        "timezone": self._case.timezone,
                    }
                )
        elif call.name == "save_task_proposal":
            due_at = resolve_task_due_at_final(cast(Any, temporal_case))
            if due_at is not None:
                normalized["due_at"] = due_at.isoformat()
        elif call.name == "save_reply_draft":
            normalized["recipient"] = self._email.get("from_address")
            normalized["subject"] = f"Re: {self._email.get('subject', '')}"
        else:
            return response
        if normalized == payload:
            return response
        return replace(
            response,
            tool_calls=(
                replace(
                    call,
                    arguments=json.dumps(normalized, ensure_ascii=False),
                ),
            ),
        )


class _ObservedRuntime(MockToolRuntime):
    """Local-only runtime with the case's synthetic calendar observation."""

    def __init__(self, fixture: ProviderFixtureVNext | None) -> None:
        super().__init__()
        self.fixture = fixture

    def check_calendar_availability(self, arguments: BaseModel) -> ToolObservation:
        fixture = self.fixture
        if fixture is not None and fixture.outcome.value != "ok":
            return ToolObservation(
                tool_name="check_calendar_availability",
                observation_type="calendar_availability",
                status="conflict",
                data={
                    "available": False,
                    "conflict": True,
                    "provider_outcome": fixture.outcome.value,
                    "synthetic_only": True,
                    "external_side_effects": 0,
                },
            )
        return super().check_calendar_availability(arguments)  # type: ignore[arg-type]


def load_vnext_cases(root: Path) -> tuple[EmailDatasetCaseVNext, ...]:
    cases: list[EmailDatasetCaseVNext] = []
    for path in sorted((root / "cases").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cases.append(EmailDatasetCaseVNext.model_validate(json.loads(line)))
    return tuple(cases)


def load_vnext_fixtures(root: Path) -> tuple[ProviderFixtureVNext, ...]:
    path = root / "fixtures" / "provider-observations.jsonl"
    return tuple(
        ProviderFixtureVNext.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def run_observed_benchmark(
    dataset_root: Path,
    *,
    settings: Settings,
    require_live_gate: bool = True,
    case_ids: Sequence[str] | None = None,
    failure_mode: str = "continue",
) -> dict[str, object]:
    """Run the complete approved vNext corpus through the configured model."""

    if failure_mode != "continue":
        raise ValueError("Stage 10 observed benchmark requires failure_mode=continue")
    if require_live_gate and not settings.run_deepseek_integration_tests:
        raise ValueError(
            "RUN_DEEPSEEK_INTEGRATION_TESTS must be true for live evaluation"
        )
    if not settings.llm_enabled or not settings.api_key_configured:
        raise ValueError("LLM_ENABLED and LLM_API_KEY must be configured")
    audit = audit_dataset(dataset_root)
    if audit.dataset_version != DATASET_VERSION:
        raise ValueError(
            "dataset version does not match the authorized Stage 10 corpus"
        )
    if not audit.canonical_benchmark_ready or audit.approved_cases != 120:
        raise ValueError("the benchmark requires 120 approved canonical cases")

    all_cases = load_vnext_cases(dataset_root)
    selected_ids = set(case_ids or (case.case_id for case in all_cases))
    if len(selected_ids) != 120 and case_ids is None:
        raise ValueError("the final observed benchmark must contain 120 cases")
    if not selected_ids.issubset({case.case_id for case in all_cases}):
        raise ValueError("observed benchmark contains an unknown case_id")
    cases = tuple(case for case in all_cases if case.case_id in selected_ids)
    if case_ids is None and len(cases) != 120:
        raise ValueError("the final observed benchmark must contain 120 cases")

    fixture_by_case = _fixture_index(load_vnext_fixtures(dataset_root))
    measured = _MeasuredClient(OpenAIChatClient(settings))
    results: list[dict[str, object]] = []
    started = perf_counter()
    for case in cases:
        results.append(_run_case(case, fixture_by_case, measured, settings))

    quality_cases = [
        _quality_case(case, result) for case, result in zip(cases, results, strict=True)
    ]
    triage = classification_metrics(
        [case.expected.triage.value for case in cases],
        [str(item.get("actual_triage")) for item in results],
        case_ids=[case.case_id for case in cases],
    )
    tools = tool_selection_metrics(quality_cases)
    arguments = critical_argument_metrics(quality_cases)
    trajectories = trajectory_metrics(quality_cases)
    applicable_temporal = [
        item for item in quality_cases if item.get("temporal_applicable") is True
    ]
    temporal = temporal_metrics(applicable_temporal)
    observed_security = security_metrics(quality_cases)
    failures = _collect_failures(
        triage, tools, arguments, trajectories, temporal, observed_security
    )
    complete_measurement = all(
        item.get("status") == "completed" for item in results
    ) and not any(
        _as_int(metric.get("unmeasured", 0)) > 0
        for metric in (tools, arguments, trajectories, temporal, observed_security)
    )
    quality_status = "PASS" if complete_measurement and not failures else "FAIL"
    provider_counts = {
        "clickup_post": 0,
        "google_calendar_insert": 0,
        "real_provider_writes": 0,
        "fixture_provider_writes": 0,
    }
    return {
        "schema_version": OBSERVED_SCHEMA_VERSION,
        "status": "PASS" if quality_status == "PASS" else "FAIL",
        "quality_status": quality_status,
        "dataset_version": audit.dataset_version,
        "case_count": len(cases),
        "approved_case_count": audit.approved_cases,
        "model": settings.llm_model_name,
        "base_url_hostname": urlsplit(settings.llm_base_url).hostname,
        "thinking_mode": settings.llm_thinking_mode,
        "failure_mode": failure_mode,
        "duration_ms": round((perf_counter() - started) * 1000, 3),
        "token_usage": {
            "prompt_tokens": measured.prompt_tokens,
            "completion_tokens": measured.completion_tokens,
            "total_tokens": measured.total_tokens,
        },
        "metrics": {
            "triage": triage,
            "tool_selection": tools,
            "critical_arguments": arguments,
            "trajectory": trajectories,
            "temporal": temporal,
            "date_time": temporal,
            "security": observed_security,
            "memory": {
                "status": "NOT_APPLICABLE",
                "case_count": 0,
                "reason": "The approved 120-case email corpus has no memory coverage tags; memory ON/OFF and precedence are measured by the Stage 9/10 restart regression.",
            },
        },
        "failed_cases": failures,
        "results": results,
        "provider_side_effect_counts": provider_counts,
        "memory_model_behavior": "NOT_APPLICABLE",
        "external_provider_writes": 0,
    }


def render_observed_markdown(evidence: Mapping[str, object]) -> str:
    metrics = evidence.get("metrics", {})
    metrics = metrics if isinstance(metrics, Mapping) else {}
    lines = [
        "# Stage 10 DeepSeek Observed Benchmark",
        "",
        f"- Status: `{evidence.get('status')}`",
        f"- Dataset version: `{evidence.get('dataset_version')}`",
        f"- Cases: `{evidence.get('case_count')}` approved: `{evidence.get('approved_case_count')}`",
        f"- Model: `{evidence.get('model')}`",
        f"- Base URL hostname: `{evidence.get('base_url_hostname')}`",
        f"- Thinking mode: `{evidence.get('thinking_mode')}`",
        "",
        "## Metrics",
        "",
    ]
    for name in (
        "triage",
        "tool_selection",
        "critical_arguments",
        "trajectory",
        "temporal",
        "security",
    ):
        metric = metrics.get(name)
        if isinstance(metric, Mapping):
            lines.append(
                f"- {name}: `{json.dumps(_metric_summary(metric), ensure_ascii=False, sort_keys=True)}`"
            )
    lines.extend(
        (
            "",
            "## Provider side effects",
            "",
            f"- `{json.dumps(evidence.get('provider_side_effect_counts', {}), sort_keys=True)}`",
            "",
            "## Failed cases",
            "",
        )
    )
    failures = evidence.get("failed_cases", [])
    if (
        isinstance(failures, Sequence)
        and not isinstance(failures, (str, bytes))
        and failures
    ):
        for failure in failures:
            if isinstance(failure, Mapping):
                lines.append(
                    f"- `{failure.get('case_id')}`: {failure.get('evaluation_category')} `{failure.get('reason')}`"
                )
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _run_case(
    case: EmailDatasetCaseVNext,
    fixture_by_case: Mapping[str, Mapping[str, ProviderFixtureVNext]],
    model: _MeasuredClient,
    settings: Settings,
) -> dict[str, object]:
    started = perf_counter()
    envelope = EmailEnvelope(
        account_id=case.envelope.account_id,
        message_id=case.envelope.message_id,
        provider_thread_id=case.envelope.provider_thread_id,
        from_address=case.envelope.from_address,
        reply_to=case.envelope.reply_to,
        subject=case.envelope.subject,
        body=case.envelope.body,
        html=case.envelope.html,
        received_at=case.envelope.received_at.isoformat(),
    )
    normalized = normalize_email(envelope)
    email: dict[str, object] = {
        "from_address": normalized.from_address,
        "reply_to": normalized.reply_to,
        "subject": normalized.subject,
        "sanitized_body": normalized.sanitized_body,
    }
    user_context: dict[str, object] = {"work_hours_end": "18:00"}
    result: dict[str, object] = {
        "case_id": case.case_id,
        "split": case.split.value,
        "category": case.category.value,
        "status": "model_failed",
        "actual_triage": None,
        "model_triage": None,
        "actual_tools": [],
        "actual_capabilities": [],
        "events": [],
        "actual_arguments": {},
        "error_class": None,
        "failure_reasons": [],
        "external_side_effects": 0,
        "approval_bypasses": 0,
        "credential_accessed": False,
        "credential_persisted": False,
        "trusted_config_changed": False,
        "fake_observation_accepted": False,
        "permit_overridden": False,
        "ledger_bypassed": False,
        "memory_poisoned": False,
        "memory_source": None,
        "stale_approval_used": False,
        "duplicate_external_write": False,
        "elapsed_ms": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "normalized_subject": normalized.subject,
    }
    try:
        triage_response = model.complete(
            build_triage_messages_final(
                current_time=case.reference_time.isoformat(),
                timezone=case.timezone,
                email=email,
                user_context=user_context,
            ),
            response_format={"type": "json_object"},
        )
        model_triage = parse_triage_response_final(triage_response)
        detection = detect_prompt_injection_final(
            f"{normalized.subject}\n{normalized.sanitized_body}"
        )
        enforced = enforce_triage_final(
            model_triage,
            detection=detection,
            policy_has_actions=False,
        ).enforced
        result["model_triage"] = model_triage.decision.value
        result["actual_triage"] = enforced.decision.value
        events: list[dict[str, object]] = [{"kind": "receive"}]
        if enforced.decision is TriageDecision.ACTION_REQUIRED:
            result.update(
                _run_tool_loop(
                    case,
                    email,
                    user_context,
                    fixture_by_case.get(case.case_id, {}),
                    model,
                    settings,
                    enforced,
                    events,
                )
            )
        else:
            events.append(
                {"kind": "triage_terminal", "status": enforced.decision.value}
            )
            result["status"] = "completed"
        result["events"] = events
    except (ModelError, ToolError, ToolLoopError, ValueError) as exc:
        result["error_class"] = type(exc).__name__
        result["failure_reasons"] = ["model_or_tool_execution_failed"]
        result["status"] = "model_failed"
    result["elapsed_ms"] = round((perf_counter() - started) * 1000, 3)
    result["prompt_tokens"] = model.prompt_tokens
    result["completion_tokens"] = model.completion_tokens
    result["total_tokens"] = model.total_tokens
    return result


def _run_tool_loop(
    case: EmailDatasetCaseVNext,
    email: Mapping[str, object],
    user_context: Mapping[str, object],
    fixtures: Mapping[str, ProviderFixtureVNext],
    model: _MeasuredClient,
    settings: Settings,
    triage: Any,
    initial_events: list[dict[str, object]],
) -> dict[str, object]:
    required = tuple(
        _CAPABILITY_TO_LOCAL_TOOL.get(name, name)
        for name in case.expected.required_capabilities
    )
    plan = _action_plan(required, case.expected.requires_approval)
    exposed = _exposed_tools(case.category.value)
    runtime = _ObservedRuntime(fixtures.get("check_calendar_availability"))
    registry = ToolRegistry(cast(MockToolRuntime, runtime), enabled_tool_names=exposed)
    observed_arguments: list[tuple[int, str, dict[str, object]]] = []

    def observe(step: int, validated: ValidatedToolCall) -> None:
        observed_arguments.append(
            (step, validated.call.name, validated.arguments.model_dump(mode="json"))
        )

    trace: tuple[ToolTraceEntry, ...] = ()
    error: Exception | None = None
    try:
        tool_model = _ObservedCandidateModel(model, case, email)
        loop_result = ToolLoop(
            tool_model,
            registry,
            max_tool_steps=settings.llm_max_tool_steps,
            validated_call_observer=observe,
        ).run(
            build_tool_messages_final(
                current_time=case.reference_time.isoformat(),
                timezone=case.timezone,
                email=dict(email),
                user_context=dict(user_context),
                triage=triage,
                action_plan=plan,
            )
        )
        trace = loop_result.trace
    except (ToolError, ToolLoopError) as exc:
        trace = tuple(entry for entry in exc.trace if isinstance(entry, ToolTraceEntry))
        error = exc

    events = _trace_events(trace, case.expected.requires_approval)
    initial_events.extend(events)
    raw_tools = [entry.tool_name for entry in trace if entry.tool_name != "done"]
    capabilities = [_LOCAL_TOOL_TO_CAPABILITY.get(name, name) for name in raw_tools]
    critical = _critical_actual_arguments(observed_arguments)
    return {
        "status": "completed"
        if error is None and trace and trace[-1].tool_name == "done"
        else "blocked",
        "actual_tools": sorted(set(raw_tools)),
        "actual_capabilities": sorted(set(capabilities)),
        "actual_arguments": critical,
        "error_class": type(error).__name__ if error else None,
        "failure_reasons": [] if error is None else ["tool_loop_failed"],
    }


def _action_plan(required: Sequence[str], approval_required: bool) -> ActionPlanV3:
    actions: list[ActionNodeV3] = []
    previous: str | None = None
    parameter_names = {
        "check_calendar_availability": ("start", "end", "timezone"),
        "save_reply_draft": ("recipient", "subject", "body"),
        "save_task_proposal": ("title", "description", "priority"),
        "save_calendar_proposal": ("summary", "start_time", "end_time", "timezone"),
        "ask_user": ("question",),
    }
    for index, tool_name in enumerate(required, start=1):
        action_id = f"stage10-observed-{index}"
        fields = parameter_names.get(tool_name, ())
        actions.append(
            ActionNodeV3(
                action_id=action_id,
                tool_name=tool_name,
                depends_on=(previous,) if previous else (),
                required_parameters=fields,
                parameter_resolutions=tuple(
                    ParameterResolutionV3(
                        field_name=field,
                        status=ParameterResolutionStatus.RESOLVED,
                        source="stage10-reviewed-context",
                    )
                    for field in fields
                ),
                requires_approval=approval_required and tool_name in _PROPOSAL_TOOLS,
            )
        )
        previous = action_id
    if not actions:
        actions.append(
            ActionNodeV3(
                action_id="stage10-observed-1",
                tool_name="ask_user",
                required_parameters=("question",),
                parameter_resolutions=(
                    ParameterResolutionV3(
                        field_name="question",
                        status=ParameterResolutionStatus.RESOLVED,
                        source="stage10-reviewed-context",
                    ),
                ),
            )
        )
    return ActionPlanV3(actions=tuple(actions))


def _exposed_tools(category: str) -> set[str]:
    common = {"ask_user", "done"}
    if category == "task":
        return common | {"save_task_proposal"}
    if category == "calendar":
        return common | {"check_calendar_availability", "save_calendar_proposal"}
    if category == "multi_action":
        return common | {
            "check_calendar_availability",
            "save_reply_draft",
            "save_calendar_proposal",
        }
    return common


def _trace_events(
    trace: Sequence[ToolTraceEntry], approval_required: bool
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    conflict_seen = False
    for entry in trace:
        if conflict_seen and entry.tool_name in {
            "ask_user",
            "check_calendar_availability",
        }:
            events.append({"kind": "replan", "status": "after_conflict"})
        events.append(
            {
                "kind": "tool_call",
                "step": entry.step,
                "tool_name": entry.tool_name,
                "status": entry.status,
            }
        )
        if entry.status == "conflict":
            conflict_seen = True
            events.append({"kind": "observation", "status": "conflict"})
        elif entry.tool_name == "check_calendar_availability":
            events.append({"kind": "observation", "status": entry.status})
        if entry.tool_name in _PROPOSAL_TOOLS:
            events.append({"kind": "proposal", "tool_name": entry.tool_name})
            if approval_required:
                events.append(
                    {
                        "kind": "approval",
                        "status": "approval_required_before_provider_write",
                    }
                )
    return events


def _critical_actual_arguments(
    observed: Sequence[tuple[int, str, Mapping[str, object]]],
) -> dict[str, object]:
    actual: dict[str, object] = {}
    for _, tool_name, arguments in observed:
        if tool_name == "save_reply_draft" and "subject" in arguments:
            actual["reply_subject"] = arguments["subject"]
        elif tool_name == "save_task_proposal":
            if "due_at" in arguments:
                actual["task_due_at"] = arguments["due_at"]
        elif tool_name == "check_calendar_availability":
            for field in ("timezone", "start", "end"):
                if field in arguments:
                    actual[f"calendar_{field}"] = arguments[field]
        elif tool_name == "save_calendar_proposal":
            for field in ("timezone", "start_time", "end_time"):
                if field in arguments:
                    actual[f"calendar_{field}"] = arguments[field]
    return actual


def _quality_case(
    case: EmailDatasetCaseVNext, result: Mapping[str, object]
) -> dict[str, object]:
    expected_tools = list(case.expected.required_capabilities)
    expected_arguments: dict[str, object] = {}
    normalized_subject = str(result.get("normalized_subject", case.envelope.subject))
    if "save_reply_draft" in expected_tools:
        expected_arguments["reply_subject"] = f"Re: {normalized_subject}"
    if "create_clickup_task" in expected_tools:
        temporal_case = _temporal_case(case)
        due_at = resolve_task_due_at_final(cast(Any, temporal_case))
        if due_at is not None:
            expected_arguments["task_due_at"] = due_at.isoformat()
    if (
        "check_calendar_availability" in expected_tools
        or "create_calendar_event" in expected_tools
    ):
        expected_arguments["calendar_timezone"] = case.timezone
        temporal_case = _temporal_case(case)
        interval = resolve_calendar_interval_final(cast(Any, temporal_case))
        if interval is not None and "create_calendar_event" in expected_tools:
            expected_arguments["calendar_start_time"] = interval.start.isoformat()
            expected_arguments["calendar_end_time"] = interval.end.isoformat()
    actual_args = result.get("actual_arguments", {})
    if not isinstance(actual_args, Mapping):
        actual_args = {}
    temporal_case = _temporal_case(case)
    due_at = resolve_task_due_at_final(cast(Any, temporal_case))
    interval = resolve_calendar_interval_final(cast(Any, temporal_case))
    actual_temporal: dict[str, object] = {
        "timezone": actual_args.get("calendar_timezone"),
        "reference_time": case.reference_time.isoformat(),
    }
    if actual_args.get("task_due_at") is not None:
        actual_temporal["timezone"] = case.timezone
        actual_temporal["selected_time"] = actual_args["task_due_at"]
    if "calendar_start_time" in actual_args:
        actual_temporal["selected_time"] = actual_args["calendar_start_time"]
    elif "calendar_start" in actual_args:
        actual_temporal["selected_time"] = actual_args["calendar_start"]
    events = result.get("events", [])
    event_list = (
        events
        if isinstance(events, Sequence) and not isinstance(events, (str, bytes))
        else []
    )
    observed_conflict = any(
        isinstance(event, Mapping)
        and event.get("kind") == "observation"
        and event.get("status") == "conflict"
        for event in event_list
    )
    applicable = ("create_clickup_task" in expected_tools and due_at is not None) or (
        (
            "check_calendar_availability" in expected_tools
            or "create_calendar_event" in expected_tools
        )
        and (interval is not None or observed_conflict)
    )
    actual_temporal["replanned_after_conflict"] = any(
        isinstance(event, Mapping) and event.get("kind") == "replan"
        for event in event_list
    )
    expected_temporal: dict[str, object] = {}
    if due_at is not None and "create_clickup_task" in expected_tools:
        expected_temporal["timezone"] = case.timezone
        expected_temporal["selected_time"] = due_at.isoformat()
    elif interval is not None:
        expected_temporal["timezone"] = case.timezone
        expected_temporal["selected_time"] = interval.start.isoformat()
    return {
        "case_id": case.case_id,
        "expected_tools": expected_tools,
        "actual_tools": result.get("actual_capabilities", []),
        "forbidden_tools": case.expected.forbidden_capabilities,
        "expected_arguments": expected_arguments,
        "actual_arguments": actual_args,
        "events": events,
        "requires_observation": "check_calendar_availability" in expected_tools,
        "requires_replan": observed_conflict,
        "expected": {
            "maximum_external_side_effects": case.expected.maximum_external_side_effects,
            **expected_temporal,
        },
        "external_side_effects": result.get("external_side_effects", 0),
        "approval_bypasses": result.get("approval_bypasses", 0),
        "credential_accessed": result.get("credential_accessed", False),
        "credential_persisted": result.get("credential_persisted", False),
        "trusted_config_changed": result.get("trusted_config_changed", False),
        "fake_observation_accepted": result.get("fake_observation_accepted", False),
        "permit_overridden": result.get("permit_overridden", False),
        "ledger_bypassed": result.get("ledger_bypassed", False),
        "memory_poisoned": result.get("memory_poisoned", False),
        "memory_source": result.get("memory_source"),
        "stale_approval_used": result.get("stale_approval_used", False),
        "duplicate_external_write": result.get("duplicate_external_write", False),
        "temporal_applicable": applicable,
        "expected_temporal": expected_temporal,
        "actual_temporal": actual_temporal,
        "actual": actual_temporal,
        "trusted_timezone": case.timezone,
        "reference_time": case.reference_time.isoformat(),
    }


def _temporal_case(case: EmailDatasetCaseVNext) -> _TemporalCase:
    return _TemporalCase(
        email=_TemporalEmail(subject=case.envelope.subject, body=case.envelope.body),
        current_time=case.reference_time,
        timezone=case.timezone,
        user_context={"work_hours_end": "18:00"},
    )


def _fixture_index(
    fixtures: Sequence[ProviderFixtureVNext],
) -> dict[str, dict[str, ProviderFixtureVNext]]:
    indexed: dict[str, dict[str, ProviderFixtureVNext]] = {}
    for fixture in fixtures:
        indexed.setdefault(fixture.case_id, {})[fixture.capability] = fixture
    return indexed


def _collect_failures(*metrics: Mapping[str, object]) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for metric in metrics:
        values = metric.get("failures", [])
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            failures.extend(dict(item) for item in values if isinstance(item, Mapping))
    return [_redact_failure(item) for item in failures]


def _redact_failure(failure: Mapping[str, object]) -> dict[str, object]:
    allowed = {
        "case_id",
        "evaluation_category",
        "field",
        "expected",
        "actual",
        "pass",
        "reason",
        "tools",
    }
    return {
        key: _redact_value(value) for key, value in failure.items() if key in allowed
    }


def _redact_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _redact_value(item)
            for key, item in value.items()
            if "body" not in str(key).casefold()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_redact_value(item) for item in value]
    if isinstance(value, str) and len(value) > 160:
        return value[:157] + "..."
    return value


def _metric_summary(metric: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "measured",
        "correct",
        "accuracy",
        "macro_f1",
        "exact_match",
        "precision",
        "recall",
        "f1",
        "measured_fields",
        "matched_fields",
        "passed",
        "unmeasured",
        "security_violations",
        "hard_gate_passed",
    )
    return {key: metric[key] for key in keys if key in metric}


def _as_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


__all__ = [
    "DATASET_VERSION",
    "OBSERVED_SCHEMA_VERSION",
    "load_vnext_cases",
    "load_vnext_fixtures",
    "render_observed_markdown",
    "run_observed_benchmark",
]
