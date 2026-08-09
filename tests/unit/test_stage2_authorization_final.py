from __future__ import annotations

import json

from inbox2action.evaluation.policy_v3 import ActionNodeV3, ActionPlanV3
from inbox2action.llm.models import ToolCall
from inbox2action.tools.authorization_final import AuthorizedToolRegistryFinal


def _tool_names(registry: AuthorizedToolRegistryFinal) -> list[str]:
    return [
        str(tool["function"]["name"])  # type: ignore[index]
        for tool in registry.openai_tools()
    ]


def test_only_next_dependency_ready_action_is_exposed() -> None:
    plan = ActionPlanV3(
        actions=(
            ActionNodeV3(
                action_id="calendar",
                tool_name="check_calendar_availability",
            ),
            ActionNodeV3(
                action_id="clarify",
                tool_name="ask_user",
                depends_on=("calendar",),
            ),
            ActionNodeV3(
                action_id="finish",
                tool_name="done",
                depends_on=("calendar", "clarify"),
            ),
        )
    )
    registry = AuthorizedToolRegistryFinal(action_plan=plan)

    assert _tool_names(registry) == ["check_calendar_availability"]

    first = registry.validate_call(
        ToolCall(
            id="call-1",
            name="check_calendar_availability",
            arguments=json.dumps(
                {
                    "start": "2026-08-10T10:00:00+08:00",
                    "end": "2026-08-10T11:00:00+08:00",
                    "timezone": "Asia/Shanghai",
                }
            ),
        )
    )
    registry.execute_validated(first, tool_call_id="call-1")

    assert _tool_names(registry) == ["ask_user"]

    second = registry.validate_call(
        ToolCall(
            id="call-2",
            name="ask_user",
            arguments='{"question":"请选择新的会议时间。"}',
        )
    )
    registry.execute_validated(second, tool_call_id="call-2")

    assert _tool_names(registry) == ["done"]


def test_independent_ready_actions_follow_reviewed_plan_order() -> None:
    plan = ActionPlanV3(
        actions=(
            ActionNodeV3(action_id="reply", tool_name="save_reply_draft"),
            ActionNodeV3(action_id="task", tool_name="save_task_proposal"),
            ActionNodeV3(
                action_id="finish",
                tool_name="done",
                depends_on=("reply", "task"),
            ),
        )
    )

    registry = AuthorizedToolRegistryFinal(action_plan=plan)

    assert _tool_names(registry) == ["save_reply_draft"]
