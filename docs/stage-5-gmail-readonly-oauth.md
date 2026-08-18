# Stage 5: Gmail readonly OAuth transport

This stage implements the smallest local Gmail boundary needed to verify OAuth
and API transport. It is not an email classifier, task extractor, Agent input,
or production workflow.

## Fixed boundary

- OAuth scope is exactly `https://www.googleapis.com/auth/gmail.readonly`.
- The smoke transport uses the fixed query `newer_than:30d`; it does not depend
  on a custom Gmail label or expand the query dynamically.
- At most 20 message IDs are read, over at most two pages of 10.
- Each message is fetched with `format=metadata` and only `From`, `Subject`,
  and `Date` headers. Bodies and attachments are not requested or persisted.
- No Gmail write method is present: there is no send, compose, delete, modify,
  mark-read, archive, or label mutation path.
- `eval/dataset-vnext` remains an evaluation-only fixture boundary and is not
  imported by this production transport.

## Files and call chain

The implementation is in `src/inbox2action/gmail/`:

1. `GmailOAuthCredentialProvider` checks the external token file.
2. A valid token is reused. An expired token is refreshed with its refresh
   token and saved atomically.
3. If no token exists, the external Desktop OAuth client JSON is validated,
   `InstalledAppFlow` starts a browser authorization with a localhost callback,
   and the resulting token is saved externally.
4. `GmailReadonlyTransport` obtains credentials before constructing a Gmail API
   service, then reads profile, recent message IDs, and bounded metadata.
5. `scripts/run_gmail_smoke.py` prints only profile email and the required
   message metadata fields.

Failure classes are kept distinct: missing client JSON, invalid client config,
authorization denial, callback failure, invalid token, refresh failure, API
network failure, and API authentication/authorization failure. Errors exposed
by the CLI are safe codes only; secret values and raw provider exceptions are
not printed.

## External files

The CLI reads the configured external paths from
`%LOCALAPPDATA%\Inbox2Action\secrets\runtime.env`:

```text
%LOCALAPPDATA%\Inbox2Action\secrets\gmail-oauth-client.json
%LOCALAPPDATA%\Inbox2Action\secrets\gmail-token.json
```

Custom paths are accepted only when they are also outside the repository.
Neither file should be copied into Git. The token is written atomically. Its
temporary file must pass permission hardening before replacement: POSIX uses
mode `0600`; Windows removes inherited ACL entries and grants full control only
to the current user, SYSTEM, and Administrators. A hardening failure preserves
the previous token and fails with `token_persistence_failed`.

## First authorization

From the repository root, after the external client JSON exists:

```powershell
uv run --frozen python scripts/run_gmail_smoke.py
```

The first run opens the system browser. Sign in with a Gmail account listed in
the OAuth app's Test users and approve the readonly permission. The localhost
callback completes the flow and creates the external token file.

To use explicit external paths:

```powershell
uv run --frozen python scripts/run_gmail_smoke.py `
  --client-secrets 'C:\path\outside\gmail-oauth-client.json' `
  --token-path 'C:\path\outside\gmail-token.json'
```

## Repeatable smoke test

After the first authorization, rerun the same command. The token is reused or
refreshed without a new browser login when its refresh token remains valid.
Use `--max-messages 1` through `--max-messages 20` to bound output. This smoke
test is intentionally manual and is not run by ordinary unit-test commands.

The real Desktop OAuth and Gmail API smoke passed on 2026-08-15 with ten
metadata records. Provider values remain redacted from repository evidence;
see `evidence/stage-5/stage5-gmail-readonly-acceptance.md`.
