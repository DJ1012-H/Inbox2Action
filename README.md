# Inbox2Action

Inbox2Action is a **Stateful Ambient Action Agent**: it turns bounded Gmail
input into reviewed, durable and recoverable actions. The engineering problem
is not only whether an LLM can read an email; it is whether a proposed action
can execute safely under human approval, durable state, idempotency and
provider failure.

## What is implemented

The current Stage 1–10 baseline provides:

- Gmail readonly OAuth ingestion, MIME normalization, PII sanitization and deduplication.
- DeepSeek-compatible structured triage and a bounded multi-turn Tool Loop.
- LangGraph HITL interrupts with approval, edit, reject, clarify and stale-revision checks.
- PostgreSQL-backed checkpoints, `PostgresStore` long-term memory and a durable execution ledger.
- ClickUp and Google Calendar provider boundaries with deterministic identities and readonly reconciliation.
- Cross-process restart recovery, account isolation, idempotency and prompt-injection policy enforcement.
- A canonical 120-case Stage 10 evaluation and security regression suite.

The Docker `api` service exposes the existing local approval page/API from
`scripts/run_stage8_approval_ui.py`; it is a small standard-library HTTP
server, not a second web application. The `worker` service reuses
`scripts/run_stage8_worker.py` and repeats the existing bounded poll.

## Architecture

```text
Gmail readonly OAuth
        |
        v
GmailWorkflowWorker -> normalize/deduplicate -> Gmail/Calendar planner
        |                                      |
        +------------------------------> LangGraph Tool Loop
                                               |
                                      HITL interrupt / proposal
                                               |
                                      approval API and UI
                                               |
                               ExecutionPermit -> ExecutionLedger
                                               |
                               ClickUp / Google Calendar executor
```

PostgreSQL is shared by the API and Worker. It stores LangGraph checkpoints,
the long-term `PostgresStore`, the workflow identity index and the durable
execution ledger. See [the architecture document](docs/architecture.md) and
[the graph lifecycle](docs/graph.md).

## Quick start with Docker Compose

The canonical startup is one Compose project with `postgres`, a one-shot
`migrate` service, `api`, and `worker`:

```powershell
Copy-Item .env.example .env
# Edit .env: set a local PostgreSQL password, the two external Gmail file paths,
# and any explicitly authorized LLM/provider settings.
docker compose --env-file .env config
docker compose --env-file .env up --build
```

Open the approval page at [http://localhost:8080/](http://localhost:8080/).
The `worker` polls Gmail every 60 seconds, deduplicates by account/message
identity, and pauses action workflows at HITL. `migrate` is the only Compose
service that runs Alembic; API and Worker use `--skip-migrations`.

To stop while retaining PostgreSQL state:

```powershell
docker compose --env-file .env down
```

Do not use `down -v` for normal shutdown. The named volume is the durable demo
state. OAuth client JSON and token files are bind-mounted from the host and are
never copied into the image.

For a host-only bounded poll, use the existing entrypoint after configuring the
external runtime file described in `.env.example` (use `localhost`, not the
Compose service name `postgres`, in its database URL):

```powershell
uv run --frozen python scripts/setup_stage4_postgres.py
uv run --frozen python scripts/run_stage8_worker.py --max-messages 1
uv run --frozen python scripts/run_stage8_approval_ui.py --port 8081
```

## Security model

Email is untrusted data. It cannot change trusted configuration, grant a tool,
read credentials, bypass HITL, override an `ExecutionPermit`, or turn a
provider observation into a trusted fact. The effective precedence is:

```text
trusted configuration and security policy
  > tool allowlist and execution contract
  > human approval / approved payload
  > normalized email content
  > provider observations and memory, subject to their contracts
```

Provider writes occur only after approval, permit validation, a durable ledger
claim and executor checks. An ambiguous provider result is reconciled through a
readonly identity check; it is not retried blindly. See [SECURITY.md](SECURITY.md)
and [the tool security policy](docs/tool-security-policy.md).

## Evaluation

The observed Stage 10 report is generated from the redacted machine result at
`evaluation/results/stage10-final.json`; it is not a target or a marketing
number. The report records 120 approved cases, verified approval provenance,
triage 1.0 accuracy/macro-F1, 1.0 tool-selection F1, 93/93 critical arguments,
120/120 trajectories, 36/36 applicable date/time cases, and 120/120 security
cases with zero violations. It also records zero ClickUp POSTs and zero
Calendar inserts during the benchmark.

Regenerate the tracked report from an available Stage 10 result:

```powershell
uv run --frozen python scripts/generate_final_metrics_report.py
```

Run safe Stage 11 checks (no provider writes and no live-model calls):

```powershell
uv run --frozen python scripts/run_stage11_acceptance.py --run-tests
```

The Stage 10 source result is intentionally a local redacted run artifact and
is ignored by Git. If it is absent, the acceptance result says so rather than
reconstructing numbers from prose.

## Demo and interview preparation

- [Demo guide](docs/demo-guide.md) — five end-to-end scenarios and evidence.
- [Demo video script](docs/demo-video-script.md) — deterministic recording order.
- [Interview guide](docs/interview-guide.md) — 20 implementation-specific questions.
- [Project overview](docs/project-overview.md) — the final engineering narrative.
- [Evaluation report](docs/evaluation-report.md) — generated observed metrics.

## Limitations

- The demo uses a test Gmail account and dedicated ClickUp List/Calendar.
- Gmail access is readonly; there is no automatic email send.
- Proposal tools are bounded; there is no arbitrary code execution, arbitrary
  HTTP, or arbitrary SQL.
- Provider acceptance requires explicit OAuth/runtime configuration and is not
  performed by the offline Stage 11 acceptance script.
- Docker runtime smoke and the final screen recording are environment/manual
  gates; this repository does not claim a video artifact that is not present.

## Project status

Stage 10 is the frozen functional/security baseline. Stage 11 packages and
documents that baseline. `Engineering: COMPLETE` requires packaging,
documentation, metrics provenance and regression checks. `STAGE 11 COMPLETE`
also requires a real Compose runtime smoke, final demo validation and an actual
recorded video artifact; otherwise the final verdict remains `INCOMPLETE` with
the remaining manual gate listed explicitly.
