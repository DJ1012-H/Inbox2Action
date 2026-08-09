from __future__ import annotations

from inbox2action.evaluation.report_final import assess_development_diagnostic_final
from inbox2action.evaluation.runner_final import (
    PilotCaseRunResultFinal,
    PilotEvaluationRunFinal,
)


def _passing_result(case_id: str) -> PilotCaseRunResultFinal:
    return PilotCaseRunResultFinal(
        case_id=case_id,
        mode="injected_model",
        status="completed",
        triage_correct=True,
        security_triage_passed=True,
        tool_selection_correct=True,
        tool_sequence_correct=True,
        action_plan_valid=True,
        arguments_valid=True,
        parameter_resolution_passed=True,
        action_dependencies_satisfied=True,
        fixture_resolution_passed=True,
        safety_passed=True,
        acceptance_passed=True,
        loop_exceeded=False,
        unauthorized_tool_attempts=0,
        unauthorized_tool_executions=0,
        unknown_tool_attempts=0,
        unknown_tool_executions=0,
        parameter_blocked_attempts=0,
        approval_bypass_attempts=0,
        dependency_blocked_attempts=0,
        forbidden_tool_attempts=0,
        external_side_effects=0,
        unauthorized_write_operations=0,
        approval_bypasses=0,
    )


def test_development_readiness_is_not_a_formal_pass() -> None:
    run = PilotEvaluationRunFinal(
        mode="injected_model",
        results=[_passing_result(f"case-{index}") for index in range(60)],
    )

    diagnostic = assess_development_diagnostic_final(run)

    assert diagnostic.status == "READY_FOR_FREEZE"
    assert not hasattr(diagnostic, "holdout_case_count")


def test_unmeasured_hard_counter_fails_development_readiness() -> None:
    results = [_passing_result(f"case-{index}") for index in range(60)]
    results[0] = results[0].model_copy(
        update={"unauthorized_tool_attempts": None}
    )

    diagnostic = assess_development_diagnostic_final(
        PilotEvaluationRunFinal(mode="injected_model", results=results)
    )

    assert diagnostic.status == "NEEDS_REMEDIATION"
    assert "unauthorized_tool_attempts_unmeasured" in diagnostic.readiness_reasons
