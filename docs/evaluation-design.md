# Stage 3 Evaluation Design

## Evidence labels

Every result must identify one of these modes:

- DETERMINISTIC_TEST: local unit or integration test with fake model, storage,
  and tools;
- OFFLINE_FIXTURE: replay of frozen synthetic email and provider fixtures;
- REAL_NETWORK: explicitly approved bounded provider observation.

Targets are not results. Unknown, missing, loop-exceeded, exceptional, or
unmeasured outcomes remain distinct and fail closed.

## Checkpoint 1: local workflow contract

Use deterministic fakes to test:

- MIME/HTML normalization, length limits, signature/quoted-history removal,
  tracking cleanup, and redaction;
- IGNORE, NOTIFY, and ACTION_REQUIRED routing;
- prompt-injection content staying below the instruction boundary;
- strict state serialization and absence of secrets;
- read-tool allowlisting and write-tool rejection before handlers;
- approval revision and payload-hash binding;
- dependency ordering and idempotency no-op behavior.

No test in this checkpoint may require an API key or network access.

## Checkpoint 2: interrupt and restart recovery

Use a real LangGraph interrupt with an in-memory checkpointer for deterministic
business tests, and the opt-in PostgreSQL checkpointer for process-restart
acceptance. For each write:

1. persist the waiting state under the stable `thread_id`;
2. resume with approve, edit, reject, or leave pending;
3. claim and atomically mark the idempotency key executing before the provider
   call;
4. close and reopen the PostgreSQL runtime for restart coverage;
5. verify the resumed route, execution result, and preference store.

Acceptance requires the same action identity, no duplicate provider call, and
no execution when the approved and executed hashes differ. A claim left in
`executing` or `unknown` is blocked for reconciliation instead of replayed.

## Checkpoint 3: fixture-backed proposal execution

Run only frozen synthetic fixtures through provider-neutral adapters. Verify
that read tools may execute directly, writes require approval, provider
ambiguity blocks, and retry/replay cannot create a second side effect.

The fixture suite should cover ordinary mail, notification, scheduling,
multi-action requests, ambiguous parameters, prompt injection, duplicate
delivery, approval edits, stale approvals, restart recovery, and provider
failure. A fixture result is not real-provider evidence.

## Checkpoint 4: external integration review gate

Only after Checkpoints 1-3 pass and the user approves the scope may a separate
bounded network test be considered. For the explicitly approved Gmail pilot,
the user may use a personally owned private account, but only 10-20 synthetic
test messages explicitly labelled `Inbox2Action` are in scope. Ordinary private
mail must not be discovered, fetched, model-visible, logged, or persisted. The
pilot still requires explicit credentials, an explicit request budget,
redacted evidence, and no production writes. Gmail ingestion, PostgreSQL
deployment, Calendar, and ClickUp are separate gates; passing one does not
authorize the others.

Stage 5 Gmail work has an additional design gate in
`docs/stage-5-gmail-access-boundary.md`. Before any real-mailbox test, its
deny-by-default access configuration, Gmail API-side label/query filtering,
10-20 message pilot limit, content/data boundary, log redaction, and persistence
minimization requirements must be translated into explicit acceptance cases.
Recording these requirements does not count as implementation or measured
Gmail evidence.

The offline candidate assets under `evaluation/dataset-vnext` now express these
requirements as 140 draft control cases and 30 synthetic Gmail API message
fixtures. They remain review inputs: no Gmail client, OAuth flow, runtime
scorer, network call, or real-mailbox evidence is implied.

## Acceptance metrics

The deterministic Stage 3 business tests and opt-in Stage 4 Docker case measure
the following gates.

| Metric | Target |
| --- | ---: |
| normalization safety cases | 100% |
| unknown/unauthorized tool execution | 0 |
| approval bypasses | 0 |
| payload-hash mismatches executed | 0 |
| duplicate external writes | 0 |
| deterministic interrupt/resume recovery cases | 100% |
| PostgreSQL process-restart recovery cases | 100% |
| prompt-injection tool-boundary violations | 0 |
| required-but-unmeasured safety metrics | 0 |

The local run is recorded in `evidence/stage-3/stage3-local-acceptance.md`; the
passing Docker gate is recorded in
`evidence/stage-4/stage4-local-acceptance.md`. Historical Stage 2 evidence
remains separate from Stage 3 results.

## Stop conditions

Stop the stage and report a blocker when a required state field is not
serializable, an approval can be bypassed, a retry can duplicate an action,
secrets appear in state/logs/evidence, or a test depends on an unapproved
external service. Do not weaken a gate to make a test pass.
