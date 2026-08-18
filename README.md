# Inbox2Action

Inbox2Action is developed through staged, fail-closed safety validation.

## Current status

Stages 1 through 4 meet their acceptance criteria. Stage 4 uses the LangGraph
PostgreSQL checkpointer as the single short-term workflow state and a separate
execution ledger only for side-effect claims. Its Docker PostgreSQL
interrupt/reconnect/resume acceptance case passed on 2026-08-12.

The Stage 5 Gmail readonly transport passed its real Desktop OAuth, external
token persistence/refresh, profile, and bounded metadata smoke on 2026-08-15.
Stage 6 now provides a bounded Gmail-body adapter, polling/deduplication,
Stage 2 proposal handoff, and a local approval API/UI over the existing
LangGraph workflow. Real Gmail-to-DeepSeek-to-PostgreSQL acceptance remains
explicitly opt-in and is not claimed by the offline tests.

Stage 2 passed its frozen real-model acceptance on 2026-08-09. The final
`deepseek-v4-flash` formal60 batch achieved:

- overall acceptance: `58/60` (`96.67%`)
- independent holdout acceptance: `19/20` (`95%`)
- argument accuracy: `58/60` (`96.67%`)
- Triage, Security Triage, Tool Selection, Tool Sequence, Action Plan,
  Parameter Resolution, Action Dependencies, Fixture Resolution, and Tool
  Boundary Safety: `100%`
- unauthorized/unknown/forbidden Tool activity, external side effects,
  unauthorized writes, approval bypasses, and loop-limit failures: `0`

The preceding independent formal attempt remains recorded as `FAIL`; its
holdout was never rerun. See
`evidence/stage-2/stage2-formal-final-attempt-2-summary.md` for the passing
redacted evidence and `docs/stage-2/model-validation-report.md` for the full
stage-two history.

## Scope boundary

Stage 3 adds a provider-neutral EmailActionAgent graph, a validated Stage 2
ActionPlan handoff, real LangGraph approval interrupts, approval revisions,
Tool-specific parameters, dependency ordering, approved-payload binding, and
multi-action execution. Stage 4 adds PostgreSQL persistence, LangGraph
checkpoint/store integration, and a durable execution claim ledger. Stage 5
provides the separately gated Gmail readonly OAuth transport; Stage 6 connects
that transport to the existing Agent boundary. Gmail writes, Calendar,
ClickUp, and all real provider writes remain out of scope until their later
stages. Stage 6 only exposes local proposal Tools and never enables real
provider writes. See
`docs/stage-6-gmail-hitl.md` for the bounded worker and approval UI.

The Gmail transport setup and manual commands are documented in
`docs/stage-5-gmail-readonly-oauth.md`. Evaluation fixtures remain under
`eval/dataset-vnext` and are not imported by the production transport.

Passing Tool Boundary Safety does not establish complete end-to-end Prompt
Injection response quality; refusal and risk-warning quality remain unmeasured.

## Local setup

Create the one local runtime file manually at
`%LOCALAPPDATA%\Inbox2Action\secrets\runtime.env`, using `.env.example` as a
safe template. Do not copy real credentials into the repository. `Settings`
loads that external file automatically, while process environment variables
override it. The default configuration keeps the model disabled; formal model
runs additionally require explicit live-model, API-cost, and frozen-asset
confirmations.

For the Stage 4 database workflow, start `postgres` with
`docker compose up -d postgres`, apply the schema with
`uv run --frozen python scripts/setup_stage4_postgres.py`, and then run
`tests/integration/test_stage4_postgres.py` with the opt-in variables shown in
`docs/stage-4-persistence.md`.

With the external runtime file configured, the bounded Stage 6 commands are:

```powershell
uv run --frozen python scripts/setup_stage4_postgres.py
uv run --frozen python scripts/run_stage6_worker.py --max-messages 1
uv run --frozen python scripts/run_stage6_approval_ui.py --port 8081
```

The worker/UI use the configured Gmail paths. `--client-secrets` and
`--token-path` remain available as explicit per-run overrides; no directory
scanning is performed. The UI binds to `127.0.0.1`; the example uses port
`8081` for a local session.
