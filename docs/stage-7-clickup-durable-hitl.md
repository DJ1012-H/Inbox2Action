# Stage 7 ClickUp durable HITL boundary

The Stage 7 runtime keeps the model and provider write paths separate:

```text
Gmail -> DeepSeek ACTION_REQUIRED -> save_task_proposal -> HITL
      -> approved edit -> ExecutionPermit -> durable claim
      -> ClickUpWriteExecutor -> ClickUp Task -> resource persistence
      -> WorkflowAction.result / approval UI
```

Only `save_task_proposal` is exposed by the Stage 6 planner. A ClickUp POST is
reachable only after the approved payload has passed `authorize_execution`,
`ledger.claim`, and `ledger.begin_execution`.

At runtime the executor discovers exactly one `Inbox2Action Key` Custom Field
of type `text` or `short_text` through the readonly List-field API. The field
is never created automatically and its provider ID is kept in process memory.
Each task receives the existing `ExecutionPermit.idempotency_key` as the
field value. Repeated claims recover the durable resource and do not POST
again.

Timeouts, connection ambiguity, 5xx responses, and untrusted successful
response bodies are never replayed blindly. The executor performs at most
three readonly custom-field searches. Exactly one match becomes a succeeded
`ExternalResourceRef`; zero matches remain `unknown`; multiple matches become
`clickup_reconciliation_conflict`. An UNKNOWN workflow restart uses the
original approved action and key, performs GET-only reconciliation, and can
promote the ledger only through `reconcile_success`.

Stage 6 continues to use `FixtureWriteExecutor`, so its worker and approval UI
cannot produce a provider write. Runtime credentials remain in the external
`%LOCALAPPDATA%\Inbox2Action\secrets\runtime.env`; no token, List ID, Task ID,
Task URL, or private email address belongs in the repository.

The live gate is intentionally separate from offline and PostgreSQL tests. It
requires the configured test List to contain the `Inbox2Action Key` field,
then a readonly preflight, followed by at most one explicitly authorized test
Task creation and a restart/no-duplicate check.
