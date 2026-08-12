# Inbox2Action

Inbox2Action is developed through staged, fail-closed safety validation.

## Current status

Stages 1 through 4 meet their acceptance criteria. Stage 4 uses the LangGraph
PostgreSQL checkpointer as the single short-term workflow state and a separate
execution ledger only for side-effect claims. Its Docker PostgreSQL
interrupt/reconnect/resume acceptance case passed on 2026-08-12.

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
checkpoint/store integration, and a durable execution claim ledger. Gmail,
Calendar, ClickUp, and all real provider writes remain out of scope until their
later stages.

Passing Tool Boundary Safety does not establish complete end-to-end Prompt
Injection response quality; refusal and risk-warning quality remain unmeasured.

## Local setup

Copy `.env.example` to `.env` only when a human explicitly enables an
integration probe. The default configuration keeps the model disabled. Formal
model runs additionally require explicit live-model, API-cost, and frozen-asset
confirmations.

For the Stage 4 database workflow, start `postgres` with
`docker compose up -d postgres`, apply the schema with
`python scripts/setup_stage4_postgres.py`, and then run
`tests/integration/test_stage4_postgres.py` with the opt-in variables shown in
`docs/stage-4-persistence.md`.
