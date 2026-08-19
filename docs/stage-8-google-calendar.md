# Stage 8 Google Calendar

Stage 8 extends the existing Stage 6/7 path without adding a Calendar-specific
approval or execution ledger:

`Gmail -> Calendar Agent tool loop -> local Calendar proposal -> existing HITL -> ExecutionPermit -> ExecutionLedger -> GoogleCalendarWriteExecutor -> ExternalResourceRef`

`check_calendar_availability` is read-only. The production adapter sends an
explicit `Asia/Shanghai` FreeBusy request to the trusted `GOOGLE_CALENDAR_ID`.
`save_calendar_proposal` only records a local proposal. No attendee, recurrence,
conference data, or dynamic Calendar routing is supported by this MVP.

## Trusted runtime configuration

Keep the OAuth Desktop client JSON and token outside the repository. Configure
these values in the existing external `runtime.env` or IntelliJ environment:

```text
INBOX2ACTION_BUSINESS_TIMEZONE=Asia/Shanghai
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CALENDAR_ID=<dedicated Inbox2Action Test calendar id>
```

## Reauthorization

The old Stage 5 token may contain Gmail-only access. Reauthorize it through the
project-native command; do not delete the token manually:

```powershell
.\.venv\Scripts\python.exe scripts\run_stage8_reauthorize.py
```

The command requests only the existing `gmail.readonly` scope plus
`calendar.freebusy` and `calendar.events.owned`, then atomically replaces the
external token using the existing secure persistence and Windows ACL path.

## Real smoke fixture

After offline and PostgreSQL gates pass and OAuth reauthorization succeeds:

```powershell
.\.venv\Scripts\python.exe scripts\run_stage8_worker.py --max-messages 10
```

Use the existing approval UI for the pending proposal:

```powershell
.\.venv\Scripts\python.exe scripts\run_stage8_approval_ui.py
```

The 2026-08-21 15:00–16:00 Asia/Shanghai fixture should produce BUSY and the
16:00–17:00 interval should produce FREE. This repository change does not claim
that live OAuth, live FreeBusy, or a real Calendar event has passed.
