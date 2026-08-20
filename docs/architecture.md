# Inbox2Action architecture

This diagram reflects the Stage 10 implementation and the Stage 11 Compose
packaging. The API is the existing standard-library approval server, despite
the service name `api`; no second FastAPI application is introduced.

```mermaid
flowchart TD
    Gmail[Gmail readonly OAuth] --> Worker[GmailWorkflowWorker\nrun_stage8_worker.py]
    Worker --> Ingest[Email ingestion\nmetadata/body adapter]
    Ingest --> Normalize[normalize_email\nPII sanitization]
    Normalize --> Planner[GmailStage2Planner or\nCalendarStage8Planner]
    Planner --> Loop[DeepSeek-compatible client\nbounded Tool Loop]
    Loop --> Graph[LangGraph EmailActionGraph]
    Graph --> Proposal[ActionProposal / Tool observation]
    Proposal --> Interrupt[approval_interrupt\ninterrupt()]
    Interrupt --> UI[approval API + HTML UI\nrun_stage8_approval_ui.py]
    UI --> Resume[ApprovalService.decide\nCommand(resume=...)]
    Resume --> Graph
    Graph --> Permit[ExecutionPermit\ntrusted policy + approved hash]
    Permit --> Ledger[PostgresExecutionLedger\nclaim / execute / reconcile]
    Ledger --> ClickUp[ClickUp executor]
    Ledger --> Calendar[Google Calendar executor]

    subgraph PG[PostgreSQL named volume]
        Schema[Alembic business schema\nhead 0005_execution_diagnostics]
        Checkpoint[AsyncPostgresSaver\nshort-term checkpoint]
        Store[AsyncPostgresStore\nlong-term memory]
        Index[PostgresWorkflowIndex\naccount/message dedup + pending index]
        Exec[inbox2action_execution_ledger]
    end

    Worker -. same DATABASE_URL .-> PG
    UI -. same DATABASE_URL .-> PG
    Schema --> Checkpoint
    Schema --> Store
    Schema --> Index
    Schema --> Exec
```

## Process boundaries

Compose starts `postgres` first, then the one-shot `migrate` service. `api` and
`worker` depend on migration completion and connect to the same PostgreSQL
database from separate processes/containers. The Worker polls Gmail and the API
only serves pending workflow state and approval decisions.

`migrate` is the only service that invokes `scripts/setup_stage4_postgres.py`.
The API and Worker pass `--skip-migrations`, so startup does not race on schema
changes. LangGraph's PostgreSQL checkpointer/store setup remains the existing
runtime initialization in `open_langgraph_postgres`; the Alembic revision is
still verified independently as `0005_execution_diagnostics`.

## Trust boundaries

Gmail content is untrusted. The planner can propose only allowlisted local
tools, and a proposal is not an external write. The execution graph validates
the approved payload and dependencies, claims the idempotency key in
`PostgresExecutionLedger`, and calls a provider executor only after the claim.
Unknown provider outcomes enter readonly reconciliation and fail closed if
identity cannot be proven.
