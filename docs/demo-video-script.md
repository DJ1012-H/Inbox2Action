# Final demo video script

Recording status: **MANUAL GATE**. This repository contains the runbook and
evidence plan, not a fabricated `demo.mp4`.

## Recording setup

1. Use a clean desktop with the terminal, approval UI and provider test tabs.
2. Configure `.env` from `.env.example`; hide all secret values and personal
   mailbox content.
3. Start with `docker compose --env-file .env up --build -d` and show `docker
   compose ps` with `postgres`, `migrate`, `api` and `worker` healthy/completed.
4. Keep a redacted evidence sheet open with `thread_id`, action ID, approval
   revision, idempotency key suffix, provider resource ID and container restart
   timestamps.

## Shot order

| Shot | Action | Screen/evidence | Talking point |
|---:|---|---|---|
| 1 | Show architecture/Compose status | terminal + architecture diagram | API and Worker are separate processes sharing PostgreSQL |
| 2 | Send reply email | test Gmail, then pending UI item | email is untrusted input and only a proposal is created |
| 3 | Edit and approve reply | approval revision and internal result | HITL binds the edited payload |
| 4 | Send task email | task proposal | ClickUp write is still behind permit and ledger |
| 5 | Approve task | ClickUp task ID and ledger result | exactly one external write |
| 6 | Trigger calendar conflict | FreeBusy observation and replan | observation precedes new proposal |
| 7 | Approve calendar event | event ID and deterministic identity | Calendar insert happens once |
| 8 | Stop/start containers | terminal container IDs and same UI thread | checkpoint recovery is cross-process |
| 9 | Show injection email | policy reason and zero writes | email cannot grant authority |
| 10 | Show metrics report | `docs/evaluation-report.md` | observed measurements are sourced from Stage 10 JSON |

## Narration checklist

- Say “proposal” before “execution” for every provider action.
- Name `ExecutionPermit`, `PostgresExecutionLedger` and readonly reconciliation.
- Distinguish `AsyncPostgresSaver` checkpoint from `AsyncPostgresStore` memory.
- Say that the benchmark performed zero ClickUp POSTs and zero Calendar inserts.
- State limitations: test account, dedicated providers, no Gmail send, no
  arbitrary code/HTTP/SQL.

## Completion evidence

The recording is complete only when a real video file exists, can be opened,
contains the five scenarios above, and has been checked for secrets/private
content. Until then the final Stage 11 verdict must remain `INCOMPLETE` with
`Actual demo video: MANUAL GATE`.
