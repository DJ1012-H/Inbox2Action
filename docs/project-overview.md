# Project overview

Inbox2Action solves a reliability problem at the boundary between untrusted
email and external side effects. It is not primarily an email classifier. Its
central question is:

> Can an Agent propose an action from untrusted email and execute it reliably
> under human supervision, durable state, idempotency and recovery constraints?

The answer is implemented as a chain of explicit contracts:

```text
Stateful Agent
  -> bounded Tool Loop
  -> HITL proposal review
  -> PostgreSQL checkpoint
  -> ExecutionPermit and durable ledger
  -> provider execution or readonly reconciliation
  -> account-scoped long-term memory
  -> offline and observed evaluation
  -> security regression
```

The design keeps authority outside the email. A message can describe a task,
meeting or reply, but it cannot enable a tool, alter a trusted calendar/list,
approve its own proposal, or provide a replacement for a provider observation.
Human approval is bound to a payload hash and revision. A provider timeout is
an ambiguous result requiring identity reconciliation, not permission to send
the POST again.

The Stage 11 deliverable packages this already validated boundary for local
deployment and explanation. It adds the one-shot migration service, a
reproducible image built from `uv.lock`, a persistent PostgreSQL volume,
architecture/graph documentation, provenance-based metrics, a demo runbook and
implementation-specific interview answers. It does not add another Agent,
queue, broker, database migration or provider framework.
