"""Dependency-ready Tool exposure for the converged stage-two candidate."""

from __future__ import annotations

from inbox2action.evaluation.policy_v3 import ActionNodeV3, ActionPlanV3
from inbox2action.tools.authorization_v3 import AuthorizedToolRegistryV3
from inbox2action.tools.mock_tools import MockToolRuntime


class AuthorizedToolRegistryFinal(AuthorizedToolRegistryV3):
    """Expose only the next reviewed Action whose dependencies are complete.

    The v3 registry correctly rejected repeats and dependency violations, but it
    exposed every Tool in the Action DAG on every turn.  That made a completed
    or future Tool look selectable to the model.  V4 keeps the same fail-closed
    validation boundary while making the advertised capability match the
    current authorization state.
    """

    def __init__(
        self,
        runtime: MockToolRuntime | None = None,
        *,
        action_plan: ActionPlanV3,
        approved_action_ids: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        super().__init__(
            runtime,
            action_plan=action_plan,
            approved_action_ids=approved_action_ids,
        )
        self._ordered_action_plan = action_plan

    @property
    def current_action(self) -> ActionNodeV3 | None:
        """Return one deterministic, dependency-ready pending Action."""

        bound = set(self._call_bindings.values())
        for action in self._ordered_action_plan.actions:
            if action.action_id in self._completed_action_ids:
                continue
            if action.action_id in bound:
                continue
            if not set(action.depends_on).issubset(self._completed_action_ids):
                continue
            return action
        return None

    def openai_tools(self) -> list[dict[str, object]]:
        current = self.current_action
        if current is None:
            return []
        tools = super().openai_tools()
        selected = [
            tool
            for tool in tools
            if tool["function"]["name"] == current.tool_name  # type: ignore[index]
        ]
        for tool in selected:
            function = tool["function"]
            if not isinstance(function, dict):
                continue
            required = ", ".join(current.required_parameters) or "none"
            function["description"] = (
                f"{function.get('description', '')} "
                "This is the only currently dependency-ready reviewed Action. "
                f"Required business parameters: {required}."
            ).strip()
        return selected

    def openai_tool_names(self) -> tuple[str, ...]:
        """Report the complete bounded capability set for loop construction."""

        return tuple(
            dict.fromkeys(
                action.tool_name for action in self._ordered_action_plan.actions
            )
        )
