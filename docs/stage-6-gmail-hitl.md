# Stage 6: Gmail to persistent HITL approval

Stage 6 connects the existing Stage 3 `EmailActionAgent` and Stage 4
PostgreSQL LangGraph runtime to the bounded Stage 5 Gmail transport.

## Boundary

The flow is:

```text
Gmail readonly API
  -> bounded full message parser
  -> EmailEnvelope
  -> existing normalize_email()
  -> existing final Stage 2 triage/prompt boundary
  -> local-only proposal Tool
  -> Stage2PlanningBundle
  -> prepare_workflow_state()
  -> existing EmailActionAgent graph
  -> PostgreSQL checkpoint
  -> interrupt()
  -> local approval API/UI
  -> approve/edit/clarify/reject
```

The Stage 6 planner exposes only `save_reply_draft` and
`save_task_proposal`. Both are local proposal Tools. No Gmail, Calendar, or
ClickUp write adapter is present. The existing Stage 3 authorization,
approval revision, payload hash, dependency, and execution-ledger checks are
still the execution boundary.

Raw MIME, OAuth tokens, authorization headers, complete provider responses,
and model reasoning do not enter `WorkflowState`. Gmail body and HTML data are
bounded before the provider-neutral envelope is created; the existing
normalizer removes quotes, signatures, hidden HTML, tracking parameters, and
PII before the first checkpoint.

## Durable deduplication

Migration `0003_stage6_workflow_index` adds only a discoverability/index table.
It stores `(account_id, message_id)`, the deterministic `thread_id`, bounded
header metadata, and the latest workflow status. It does not duplicate the
LangGraph workflow state. A unique identity claim prevents the same Gmail
message from creating multiple workflows.
If a process stops after the LangGraph checkpoint is committed but before this
index status is updated, the next bounded poll reconciles the existing graph
state and repairs the listing status without re-planning or re-processing the
message.

## Local commands

Create the external runtime file manually at
`$env:LOCALAPPDATA\Inbox2Action\secrets\runtime.env` (normally
`%LOCALAPPDATA%\Inbox2Action\secrets\runtime.env`) using the safe
`.env.example` template. Put the external Gmail OAuth paths, database URL, and
explicitly approved model configuration there. Do not commit that file or any
credential content.

After PostgreSQL and the external OAuth files are configured:

```powershell
docker compose up -d postgres
uv run --frozen python scripts\setup_stage4_postgres.py
uv run --frozen python scripts\run_stage6_worker.py --max-messages 1
uv run --frozen python scripts\run_stage6_approval_ui.py --port 8081
```

The worker is a bounded one-pass command. The UI binds to `127.0.0.1`; the
example uses port `8081`. Settings priority is process environment, then the
external runtime file, then safe code defaults. `--client-secrets` and
`--token-path` override the configured Gmail paths for one worker run. These
commands require explicit Gmail, model, and database authorization; ordinary
tests do not contact those services.

The PostgreSQL-only Stage 6 recovery test is separately gated:

```powershell
$env:RUN_POSTGRES_INTEGRATION_TESTS = "true"
uv run --frozen pytest tests/integration/test_stage6_postgres.py -q
```

## Current evidence boundary

Unit tests cover Gmail full-message mapping, MIME bounds, Stage 2 handoff,
deduplication, interrupt persistence through the in-memory checkpointer,
approve/edit/clarify/reject semantics, stale approval rejection, and the
no-provider-write fixture executor. The PostgreSQL recovery test is opt-in and
requires a running database. Real Gmail-to-DeepSeek-to-PostgreSQL acceptance
remains an opt-in operational run and is not established by the offline suite.
