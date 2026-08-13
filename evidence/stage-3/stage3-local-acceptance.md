# Stage 3 Local Acceptance

Date: 2026-08-09

## Business result

Stage 3 now has one provider-neutral EmailActionAgent workflow with:

- normalization before the first durable graph checkpoint;
- validated Stage 2 `TriageResultV3` and `ActionPlanV3` handoff;
- Tool-specific Pydantic parameter validation and dependency ordering;
- real LangGraph approve, edit/revision, and reject interrupts;
- exact approved payload hashes and deterministic idempotency claims;
- multi-action execution in reviewed dependency order;
- redacted audit events and explicit failed/unknown terminal states.

All write adapters cross the same `authorize_execution` boundary. The boundary
checks the ActionPlan node, required parameter resolution, dependencies,
Tool-specific parameters, approval revision/hash, and workflow status. The
execution ledger then claims the idempotency key before the adapter is called.

## Measured evidence

- Repaired Stage 3 business slice: `10 passed`.
- Full repository regression: `263 passed, 3 skipped`.
- Ruff on the Stage 3/4 implementation and tests: passed.
- Mypy on the Stage 3/4 source: passed.

The skipped PostgreSQL test is the Stage 4 Docker integration case. Gmail,
Calendar, ClickUp, and other real provider writes are not Stage 3 evidence.
