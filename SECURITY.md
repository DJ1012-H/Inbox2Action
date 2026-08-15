# Security policy

Inbox2Action follows a staged safety gate. Unit tests must use fake clients and
must not call a real model. Integration probes are opt-in and must never run
from ordinary test commands or CI.

Never commit `.env`, API keys, OAuth client JSON, access tokens, refresh tokens,
authorization headers, raw model responses, complete email bodies, or complete
`reasoning_content`. Gmail OAuth client and token files belong outside the
repository, by default at
`%LOCALAPPDATA%\Inbox2Action\secrets\gmail-oauth-client.json` and
`%LOCALAPPDATA%\Inbox2Action\secrets\gmail-token.json`. The readonly transport
uses only `https://www.googleapis.com/auth/gmail.readonly`, never falls back to
a broader scope, and does not log credential contents. Token persistence fails
closed unless the temporary token file can be restricted before atomic
replacement; on Windows, inherited ACL entries are removed.

The first Gmail version is a manual, metadata-only transport smoke test. It is
not connected to the Agent and performs no send, delete, modify, mark-read, or
archive operation. Keep external writes, production mailbox workflows,
database access, and Agent ingestion disabled until a later stage is explicitly
approved.

Report suspected credential exposure or an unsafe tool path before continuing
development.
