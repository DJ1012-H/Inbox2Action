from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from zoneinfo import ZoneInfo

from inbox2action.errors import ModelError
from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
)
from inbox2action.evaluation.triage_final import (
    build_tool_messages_final,
    build_triage_messages_final,
    detect_prompt_injection_final,
    enforce_triage_final,
    parse_triage_response_final,
)
from inbox2action.llm.models import ChatCompletionResult
from inbox2action.llm.protocols import ChatClientPort
from inbox2action.memory.service import MemoryService
from inbox2action.stage3.contracts import (
    ActionProposal,
    EmailEnvelope,
    Stage2PlanningBundle,
)
from inbox2action.stage3.normalization import normalize_email
from inbox2action.tools.policy import ToolError
from inbox2action.tools.registry import ToolRegistry


class Stage6PlanningError(RuntimeError):
    """A real message could not be converted into a safe Stage 2 handoff."""


_PROPOSAL_TOOLS = frozenset({"save_reply_draft", "save_task_proposal"})
_PROPOSAL_SEMANTIC_RETRY_LIMIT = 1
_PROPOSAL_REPAIR_MESSAGE = """
The previous model response violated the Stage 6 proposal contract. Return
exactly one call to one currently exposed proposal Tool, with schema-valid
arguments. Do not return ordinary text and do not call any unexposed Tool.
""".strip()
_REQUIRED_PARAMETERS: dict[str, tuple[str, ...]] = {
    "save_reply_draft": ("subject", "body"),
    "save_task_proposal": ("title", "description", "priority"),
}


class GmailStage2Planner:
    """Use the existing final Stage 2 prompts and local-only proposal Tools."""

    def __init__(
        self,
        model: ChatClientPort,
        *,
        timezone: str = "Asia/Shanghai",
        user_context: Mapping[str, object] | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        try:
            ZoneInfo(timezone)
        except Exception as exc:
            raise ValueError("timezone must be a known IANA timezone") from exc
        self._model = model
        self._timezone = timezone
        self._user_context = dict(user_context or {})
        self._memory_service = memory_service

    def plan(self, envelope: EmailEnvelope) -> Stage2PlanningBundle:
        return self._plan(envelope, user_context=self._user_context)

    async def plan_with_memory(self, envelope: EmailEnvelope) -> Stage2PlanningBundle:
        """Load bounded preferences before the existing planner decision."""

        if self._memory_service is None:
            return self.plan(envelope)
        context = await self._memory_service.load_context(envelope.account_id)
        user_context = {
            **self._user_context,
            "LONG_TERM_SOFT_PREFERENCES": context.to_prompt_context(),
        }
        return self._plan(envelope, user_context=user_context)

    def _plan(
        self,
        envelope: EmailEnvelope,
        *,
        user_context: Mapping[str, object],
    ) -> Stage2PlanningBundle:
        normalized = normalize_email(envelope)
        email_payload = normalized.model_dump(mode="json")
        current_time = datetime.now(ZoneInfo(self._timezone)).isoformat()
        try:
            triage_response = self._model.complete(
                build_triage_messages_final(
                    current_time=current_time,
                    timezone=self._timezone,
                    email=email_payload,
                    user_context=dict(user_context),
                ),
                response_format={"type": "json_object"},
            )
            model_triage = parse_triage_response_final(triage_response)
        except ModelError:
            raise
        except Exception as exc:
            raise Stage6PlanningError("triage planning failed") from exc

        detection = detect_prompt_injection_final(
            f"{normalized.subject}\n{normalized.sanitized_body}"
        )
        enforced = enforce_triage_final(
            model_triage,
            detection=detection,
            policy_has_actions=False,
        ).enforced
        if enforced.decision.value in {"IGNORE", "NOTIFY"}:
            return Stage2PlanningBundle(triage=enforced)
        if not enforced.safe_to_plan_actions:
            raise Stage6PlanningError("action planning is not safe for this message")

        candidate_plan = _candidate_plan()
        registry = ToolRegistry(enabled_tool_names=_PROPOSAL_TOOLS)
        try:
            response = _complete_proposal_with_semantic_retry(
                self._model,
                build_tool_messages_final(
                    current_time=current_time,
                    timezone=self._timezone,
                    email=email_payload,
                    user_context=dict(user_context),
                    triage=enforced,
                    action_plan=candidate_plan,
                ),
                registry,
            )
            if len(response.tool_calls) != 1:
                raise Stage6PlanningError(
                    "planner must return exactly one proposal Tool"
                )
            validated = registry.validate_call(response.tool_calls[0])
        except Stage6PlanningError:
            raise
        except (ModelError, ToolError):
            raise
        except Exception as exc:
            raise Stage6PlanningError("action proposal planning failed") from exc

        tool_name = validated.call.name
        if tool_name not in _PROPOSAL_TOOLS:
            raise Stage6PlanningError("planner selected a non-proposal Tool")
        proposal = ActionProposal(
            action_id="gmail-action-1",
            tool_name=tool_name,  # type: ignore[arg-type]
            parameters=validated.arguments.model_dump(mode="json"),
        )
        action = ActionNodeV3(
            action_id=proposal.action_id,
            tool_name=proposal.tool_name,
            required_parameters=_REQUIRED_PARAMETERS[tool_name],
            parameter_resolutions=tuple(
                ParameterResolutionV3(
                    field_name=field_name,
                    status=ParameterResolutionStatus.RESOLVED,
                    source="stage6_model_proposal",
                )
                for field_name in _REQUIRED_PARAMETERS[tool_name]
            ),
            requires_approval=True,
        )
        return Stage2PlanningBundle(
            triage=enforced,
            action_plan=ActionPlanV3(actions=(action,)),
            proposals=[proposal],
        )


def _complete_proposal_with_semantic_retry(
    model: ChatClientPort,
    messages: list[dict[str, object]],
    registry: ToolRegistry,
) -> ChatCompletionResult:
    tools = registry.openai_tools()
    response = model.complete(messages, tools=tools)
    if not _should_retry_proposal_cardinality(response):
        return response

    retry_messages: list[dict[str, object]] = [
        messages[0],
        {"role": "system", "content": _PROPOSAL_REPAIR_MESSAGE},
        *messages[1:],
    ]
    for _ in range(_PROPOSAL_SEMANTIC_RETRY_LIMIT):
        response = model.complete(retry_messages, tools=tools)
    return response


def _should_retry_proposal_cardinality(response: ChatCompletionResult) -> bool:
    tool_calls = response.tool_calls
    if len(tool_calls) == 1:
        return False
    return all(tool_call.name in _PROPOSAL_TOOLS for tool_call in tool_calls)


def _candidate_plan() -> ActionPlanV3:
    actions = tuple(
        ActionNodeV3(
            action_id=f"candidate-{index}",
            tool_name=tool_name,
            required_parameters=_REQUIRED_PARAMETERS[tool_name],
            parameter_resolutions=tuple(
                ParameterResolutionV3(
                    field_name=field_name,
                    status=ParameterResolutionStatus.RESOLVED,
                    source="stage6_allowlist",
                )
                for field_name in _REQUIRED_PARAMETERS[tool_name]
            ),
            requires_approval=True,
        )
        for index, tool_name in enumerate(sorted(_PROPOSAL_TOOLS), start=1)
    )
    return ActionPlanV3(actions=actions)
