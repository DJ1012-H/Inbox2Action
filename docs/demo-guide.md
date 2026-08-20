# Final demo guide

This is a runbook for a configured test Gmail account, one dedicated ClickUp
List, one dedicated Google Calendar and a local PostgreSQL database. Use the
same `account_id`, message identifiers and `thread_id` in the evidence log.
Do not use a personal mailbox or a production list/calendar.

## Preflight

```powershell
Copy-Item .env.example .env
# Set OAuth host paths, runtime container paths, LLM/provider flags and the
# dedicated provider IDs. Keep all token files outside Git.
docker compose --env-file .env config
docker compose --env-file .env up --build -d
docker compose --env-file .env ps
```

Open `http://localhost:8080/`. Capture only redacted subject/thread/status,
approval revision, idempotency key suffix and provider resource ID. Never show
email bodies, OAuth tokens, API keys or authorization headers.

## Demo 1 — reply proposal and internal draft

1. Send a fixture email to the test Gmail account asking for a reply.
2. Wait for the Worker to list and normalize the message.
3. In the approval UI, show `save_reply_draft` in `WAITING_FOR_APPROVAL`.
4. Edit the proposal, approve it, and show the internal draft/result in the
   workflow state. There is no Gmail send operation.
5. Show the account-scoped memory update or its explicit no-op evidence.

Expected evidence: one message identity, one pending `thread_id`, changed
approval revision after edit, approved payload hash, no Gmail write.

## Demo 2 — ClickUp task

1. Send a task email with a deterministic due date and priority.
2. Show the task proposal and edit it before approval.
3. Approve once and show the ClickUp task ID/resource reference.
4. Refresh/replay the workflow and show the durable ledger result is
   `ALREADY_SUCCEEDED`; do not click approve twice to force a second write.

Expected evidence: one ClickUp POST, one task ID, one idempotency key, and no
second POST on replay. This is a manually authorized live-provider gate.

## Demo 3 — Calendar conflict and replanning

1. Send a meeting email whose first slot conflicts with a pre-created calendar
   event.
2. Show the readonly FreeBusy observation and the Agent's replanning turn.
3. Show the new proposal, approve it, and show the Calendar event ID/resource.

Expected evidence: FreeBusy before insert, conflict observation, replan, HITL
approval before `Events.insert`, and one deterministic event identity.

## Demo 4 — cross-process restart recovery

1. Create a proposal and leave it at `WAITING_FOR_APPROVAL`.
2. Record the `thread_id`, action ID and approval revision.
3. Stop both `api` and `worker` containers without removing the PostgreSQL
   volume:

   ```powershell
   docker compose --env-file .env stop api worker
   docker compose --env-file .env start api worker
   ```

4. Refresh the UI and show the same pending `thread_id`, action and revision.
5. Approve once and show completion.

Expected evidence: the process IDs/containers changed, PostgreSQL volume was
retained, the same checkpoint was loaded, and no duplicate provider write was
made.

## Demo 5 — prompt injection

1. Send a fixture email containing an instruction to ignore policy, reveal a
   token or bypass approval.
2. Show the normalized untrusted input and enforced safe triage.
3. Show that no unauthorized tool is exposed, no approval is bypassed and no
   ClickUp/Calendar write occurs.

Expected evidence: policy reason code, zero provider writes, and a redacted
security audit event. Do not put a real secret in the email fixture.

## Cleanup

```powershell
docker compose --env-file .env stop
# Keep the volume for restart evidence; remove it only as an explicitly
# authorized local cleanup action.
```
