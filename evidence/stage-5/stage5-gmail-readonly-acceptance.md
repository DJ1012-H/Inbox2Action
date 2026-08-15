# Stage 5 Gmail Readonly Acceptance

Acceptance date: 2026-08-15

## Implemented boundary

- Desktop App OAuth with the fixed scope
  `https://www.googleapis.com/auth/gmail.readonly`;
- browser authorization with a localhost callback;
- external atomic token persistence and refresh;
- fail-closed token permission hardening, including Windows ACL inheritance
  removal;
- Gmail profile plus a fixed `newer_than:30d` query;
- at most 20 messages over at most two pages;
- message ID, thread ID, From, Subject, and Date only, using Gmail metadata
  format;
- no body, attachment, Agent ingestion, or Gmail write operation.

## Real provider evidence

The External/Testing OAuth application was authorized by a configured test
user. The token was persisted outside the repository and subsequently reused
and refreshed without another browser login.

The final Gmail smoke completed with exit code 0:

- profile response present: yes;
- message count: 10;
- complete message/thread ID and From/Subject/Date record groups: 10;
- raw mailbox values recorded in the repository: no;
- real provider evidence: true.

## Local validation

- full no-service regression: `282 passed, 3 skipped`;
- Gmail OAuth/transport unit slice: `19 passed`;
- Ruff: passed;
- Mypy: passed;
- repository OAuth client/token file scan: clean;
- Windows ACL verification: current user, SYSTEM, and Administrators only.

The skipped tests require separate explicit DeepSeek or PostgreSQL integration
configuration and are not part of the Gmail readonly transport gate.
