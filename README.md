# Inbox2Action

Inbox2Action is developed through staged, fail-closed safety validation.

## Current status

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

Stage 2 validates bounded inbox Triage, reviewed Action DAG authorization,
local proposal Tools, deterministic fixtures, and fail-closed evaluation. It
does not include Gmail, Calendar, ClickUp, PostgreSQL, production workflows, or
real external writes.

Stage 3 has not started. Passing Tool Boundary Safety does not establish
complete end-to-end Prompt Injection response quality; refusal and risk-warning
quality remain unmeasured.

## Local setup

Copy `.env.example` to `.env` only when a human explicitly enables an
integration probe. The default configuration keeps the model disabled. Formal
model runs additionally require explicit live-model, API-cost, and frozen-asset
confirmations.
