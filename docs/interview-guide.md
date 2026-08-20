# Inbox2Action interview guide

Answers below refer to the current modules and contracts, not a generic
LangGraph tutorial.

## 1. Why is the main Agent `EmailActionAgent`?

The business boundary is an action proposal from a normalized email, not a
chat assistant. In this repository the orchestration is split between the
Stage 2 planner (`GmailStage2Planner`/`CalendarStage8Planner`) and the shared
`build_email_action_graph`; this keeps model planning separate from durable
execution. The alternative would be one monolithic prompt, which would make
approval, restart and provider safety harder to inspect.

## 2. Why is the Router not an Agent?

Routing is a deterministic policy decision. `build_email_action_graph` routes
based on `WorkflowState.status`, dependencies and action status; the model does
not decide whether a write bypasses HITL. Keeping routing deterministic makes
the security contract testable.

## 3. Agent versus Workflow?

The planner/Tool Loop interprets email and proposes a bounded action sequence.
The LangGraph workflow persists state, interrupts for approval, authorizes a
permit and records results. The Agent is probabilistic; the Workflow is the
durable control plane.

## 4. What does LangGraph State contain?

`WorkflowState` contains the normalized email, triage, `ActionPlanV3`, workflow
actions, approvals/revisions, completed action IDs, audit events and status.
The checkpoint stores that current workflow state under `thread_id`; it is not
the long-term preference store.

## 5. How does the Reducer work?

Graph nodes return partial `EmailActionGraphState` updates. The graph merges
those updates into the validated `WorkflowState`; action replacement and audit
events use the explicit helpers in `stage3.graph` rather than letting a model
mutate arbitrary fields.

## 6. How does a Tool Call enter the Tool Node?

The planner invokes the bounded `ToolLoop`, which passes model tool calls to
the allowlisted `ToolRegistry`. Calls are schema-validated into
`ValidatedToolCall`; observations are appended to the next model turn. A
provider capability is not exposed merely because the email asks for it.

## 7. Why must a write Tool use HITL?

`save_reply_draft`, `save_task_proposal` and `save_calendar_proposal` create
proposals, but external execution requires an explicit approval. The graph's
`approval_interrupt` and `authorize_execution` enforce that distinction. This
prevents a prompt injection or model hallucination from becoming a write.

## 8. How does `interrupt()` resume?

The graph persists before the interrupt. `ApprovalService.decide` validates the
current action and revision, constructs `ApprovalDecision`, then invokes the
same graph with `Command(resume=...)`.

## 9. Why is the same `thread_id` important?

`thread_id` selects the durable checkpoint and the workflow identity. Resuming
with another ID creates a different workflow and loses the pending approval;
the API therefore requires the stored thread ID.

## 10. Why may an interrupt node execute again?

Process restart or resume can revisit a graph boundary. That is safe because
approval is revision-checked and the side effect is protected later by the
durable ledger. A node replay is not permission to replay a provider POST.

## 11. How are duplicate tasks prevented?

`ExecutionPermit.idempotency_key` binds account/message/action/payload. The
`PostgresExecutionLedger` claims it before `WriteExecutor.execute`. A replay
of a succeeded claim returns `ALREADY_SUCCEEDED`; no second ClickUp call is
made.

## 12. What if Calendar succeeds but the client times out?

The ledger records `UNKNOWN` and the executor's reconciliation path performs a
bounded readonly lookup by the deterministic provider identity. Only a proven
resource is promoted to success; otherwise retry is blocked.

## 13. Memory versus chat history?

`AsyncPostgresSaver` is short-term checkpoint state for the current workflow.
`AsyncPostgresStore`, accessed by `MemoryService`, stores account-scoped,
versioned preference facts for later workflows. There is no implication that
all prior email text is a trustworthy memory.

## 14. Why cannot preferences modify security policy?

Memory is explicitly a soft preference layer. `PreferenceContext` can influence
language, duration or default priority, but trusted timezone/list/configuration
and the tool policy have higher precedence. This is covered by Stage 9/10
memory precedence regression checks.

## 15. Why is prompt injection not only a prompt problem?

The enforcement boundary is code: normalized untrusted content, triage
enforcement, tool allowlists, HITL, permit binding, ledger claims and provider
contracts. Even a compromised model response cannot directly access a token or
skip the execution contract.

## 16. How is DeepSeek Tool Calling evaluated?

The authorized observed runner uses the frozen 120-case dataset and scores
actual model trajectories through the existing triage, Tool Loop and fixture
runtime. It records machine-readable triage/tool/argument/trajectory/time/
security metrics; Stage 11 reads the resulting `stage10-final.json` and never
reruns the model.

## 17. How is Tool Sequence correctness proved?

`trajectory_metrics` checks required observations, conflict replanning,
approval ordering and forbidden tools from redacted event traces. The observed
baseline measured 120/120 trajectories and zero forbidden tool invocations.

## 18. How is restart recovery proved?

The Stage 10 PostgreSQL validator runs process-A/process-B checkpoint recovery
and the Stage 9 cross-process memory validator. The demo repeats the proof with
separate API/Worker containers and the same named PostgreSQL volume.

## 19. What was designed versus referenced?

The project uses LangGraph, PostgreSQL checkpointer/store, Google OAuth client
libraries and OpenAI-compatible client libraries as infrastructure. The
project-specific contracts—`WorkflowState`, `ActionPlanV3`, approval revision,
`ExecutionPermit`, `PostgresExecutionLedger`, provider identity reconciliation,
memory precedence and the evaluation gates—are the design work being tested.
The repository keeps these boundaries visible instead of hiding them in a
provider-specific framework.

## 20. Why is this not an email classifier?

A classifier would stop at a label. Inbox2Action carries a message through
normalization, triage, multi-turn Tool Loop, proposal, human decision,
checkpoint/restart, durable execution and memory/evaluation contracts. Its
deliverable is a safe, recoverable action workflow, not only a category.
