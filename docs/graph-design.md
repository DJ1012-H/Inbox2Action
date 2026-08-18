# Stage 3 Graph Design

## Goal

Stage 3 turns the bounded Stage 2 tool loop into a stateful workflow while
keeping all untrusted email content below the instruction boundary. The graph
is one EmailActionAgent operating over validated state; TriageRouter is a
workflow node, not another agent.

    EmailIngestion
        -> EmailNormalization (before durable graph state)
        -> Stage2PlanningBundle
        -> TriageRouter
           -> IGNORE ------------------------------> Finalize
           -> NOTIFY ------------------------------> Finalize
           -> ACTION_REQUIRED
                -> SelectDependencyReadyAction
                -> ApprovalInterrupt
                   -> edit ------------------------> ApprovalInterrupt
                   -> rejected --------------------> Finalize
                   -> approved --------------------> ExecutionClaim
                -> ToolExecution
                -> SelectDependencyReadyAction
                -> Finalize

## State contract

The persisted state is the minimum needed to resume safely:

- thread_id: stable workflow identity;
- account_id and provider message identity: deduplication scope;
- normalized email metadata and bounded sanitized body;
- triage decision and reason, with model output treated as untrusted data;
- the validated Stage 2 `ActionPlanV3`, action dependencies, and parameter
  resolutions;
- tool observations and redacted execution trace;
- approval status, approval revision, approved payload hash, and execution
  result;
- retry/recovery metadata and terminal status.

Secrets, provider access tokens, complete authorization payloads, raw MIME,
complete model reasoning, unrestricted email content, and the provider
`EmailEnvelope` are not state fields. Ingestion normalizes the envelope before
the first checkpointed graph invocation.

## Node contracts

### EmailIngestion

Accepts a provider-neutral message envelope. It must deduplicate on the
account/message identity before creating a new workflow. It does not send,
modify, or delete mail.

### EmailNormalization

Parses and bounds MIME/HTML content, removes signatures and quoted history,
removes hidden text and tracking parameters, and applies the project redaction
policy before constructing `WorkflowState`. Failure prevents graph invocation;
raw content is never a checkpointer channel.

### TriageRouter

Routes only to IGNORE, NOTIFY, or ACTION_REQUIRED. An absent, contradictory,
or unmeasured decision is not treated as IGNORE.

### EmailActionAgent

Consumes a `Stage2PlanningBundle` containing enforced triage, reviewed
`ActionPlanV3`, and schema-valid proposals. It selects one dependency-ready
write at a time and may not execute it before approval and a durable execution
claim.

### ApprovalInterrupt

Uses LangGraph `interrupt()` to persist the exact proposed action and wait for
approve, edit, or reject. Resume uses `Command(resume=...)`. Edit validates the
replacement Tool parameters, creates a new revision/hash, and interrupts again.

### ToolExecution

Revalidates the action plan, dependencies, Tool-specific Pydantic parameters,
approval state, and payload hash immediately before the provider adapter. A
durable idempotency claim is created first and atomically moved to `executing`.
A replay of an executing/unknown claim is blocked for reconciliation.

### MemoryUpdate

Updates only explicitly user-editable preference data. Tool results,
approvals, safety decisions, idempotency records, and provider permissions
cannot mutate preferences.

### Finalize

Writes a terminal, auditable outcome. It must distinguish completed,
waiting-for-user, blocked, failed, and duplicate outcomes; it must never
convert an unknown or unmeasured result into success.

## Recovery and idempotency

Every interrupt and node boundary is checkpointable. The graph rejects a
`configurable.thread_id` that differs from the stable workflow thread ID. On
restart, the worker resumes the existing checkpoint and replays only safe
transitions.
External writes require both:

1. a unique idempotency key based on email identity, action type, and the
   normalized payload; and
2. approved_payload_hash == executed_payload_hash.

An already-completed idempotency key is recovered as success without calling
the provider. A claim left in `executing` or `unknown` is not replayed and must
be reconciled.

## Implemented delivery sequence

1. Define and test state/transition contracts with local fixtures.
2. Normalize provider envelopes before the durable graph boundary.
3. Bind validated Stage 2 plans to real LangGraph approval interrupts.
4. Execute dependency-ready fixture actions behind the authorization and
   durable claim boundaries.
5. Add PostgreSQL graph persistence and execution-ledger recovery in Stage 4.

Stage 6 adds a bounded Gmail polling adapter and a discoverability index while
keeping this graph as the single workflow implementation. Real provider write
adapters remain later-stage work.
