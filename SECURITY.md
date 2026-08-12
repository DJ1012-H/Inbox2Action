# Security policy

Inbox2Action follows a staged safety gate. Unit tests must use fake clients and
must not call a real model. Integration probes are opt-in and must never run
from ordinary test commands or CI.

Never commit `.env`, API keys, authorization headers, raw model responses,
complete email bodies, or complete `reasoning_content`. Keep external writes,
mailbox access, database access, and production tools disabled until a later
stage is explicitly approved.

Report suspected credential exposure or an unsafe tool path before continuing
development.

Future real Gmail ingestion is governed by the application-level access and
data-boundary constraints in `docs/stage-5-gmail-access-boundary.md`. Those
requirements are planned Stage 5 controls and must not be reported as current
security capabilities before implementation and acceptance.
