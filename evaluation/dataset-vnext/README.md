# Inbox2Action Dataset vNext Candidate

This directory contains every dataset artifact that can be prepared safely
before a future model candidate and independent formal holdout exist. It is a
synthetic, offline, candidate-only corpus; it is not real-provider evidence and
none of its Gold Labels has been independently approved.

## Current contents

| Asset | Count | Role |
| --- | ---: | --- |
| Development email cases | 60 | Visible model and workflow development |
| Regression email cases | 30 | Visible contract and known-edge regression |
| Security challenge cases | 30 | Visible adversarial development only |
| Workflow scenarios | 30 | Deterministic approval, replay, and failure paths |
| Provider fixtures | 60 | Synthetic observations with zero external side effects |
| Review records | 120 draft | Human review queue; no automatic approval |
| Synthetic Gmail API messages | 30 | Provider-shaped input; 20 labelled and 10 deliberately outside the allowlist |
| Gmail label directories | 5 | Exact name-to-ID resolution plus missing, renamed, ambiguous, and empty failures |
| Gmail list responses | 27 | Provider-shaped `messages.list` pages using the resolved label ID |
| Gmail access-policy cases | 30 | Five valid and 25 deny-before-query configurations |
| Pagination/cursor cases | 20 | Bounded paging, deduplication, loop, cursor, and page-cap behavior |
| Content-policy mapping cases | 30 | Provider input to minimized model-visible Gold contract |
| Logging/persistence cases | 20 | Redaction and retention boundaries |
| Access/injection matrix cases | 20 | Five cases in each independent risk quadrant |
| Response-safety calibration cases | 20 | Ten accepted and ten rejected scorer examples |
| Control review records | 140 draft | Human review queue for every Stage 5 control case |

The 120 email cases use 70 `zh-CN`, 28 English, and 22 `zh-TW` records. They
cover ordinary mail, notifications, tasks, calendar requests, multi-action
requests, and prompt injection. Extended envelopes include HTML, synthetic
headers, thread IDs, reply-to values, and attachment metadata without storing
attachment contents.

## Directory contract

- `cases/development.jsonl`: visible development candidates.
- `cases/regression.jsonl`: visible regression candidates.
- `cases/security-challenge.jsonl`: visible adversarial candidates; never call
  this an independent holdout.
- `fixtures/provider-observations.jsonl`: deterministic read/write outcome
  fixtures; every record states `synthetic_only=true` and
  `external_side_effects=0`.
- `workflow/scenarios.jsonl`: duplicate, approval, restart, dependency,
  Provider failure/unknown, rejection, and retry contracts.
- `reviews/review-records.jsonl`: one `draft` record per case. Only a human may
  advance a record after reviewing the complete candidate and Gold Label.
- `gmail/`: synthetic `labels.list`, `messages.list`, and
  `messages.get(format=FULL)` fixtures, access-policy cases, bounded pagination
  cases, and the access-control/prompt-injection matrix. Gmail `labelIds`
  contain immutable IDs; `Inbox2Action` remains the reviewed display name.
- `content-policy/model-input-gold.jsonl`: exact minimized provider-neutral
  mapping expectations, including complete sanitized subject/body, normalized
  body SHA-256, transformations, redactions, removals, and model-input oracle.
  Only sanitized subject, body, and timezone may be model-visible.
- `observability/boundary-gold.jsonl`: logging redaction and data-retention Gold
  contracts.
- `response-safety/scorer-calibration.jsonl`: explicit pass/fail calibration
  data for a future user-visible warning/refusal scorer; this is not a working
  scorer or a measured result.
- `reviews/control-review-records.jsonl`: one `draft` review for each of the 140
  Stage 5 control cases.
- `schemas/`: exported JSON Schema artifacts.
- `manifest.json`: counts and LF-normalized SHA-256 hashes.
- `gmail-boundary-manifest.json`: approved private-pilot constants, control
  counts, offline-evidence flags, and independent asset hashes.

## Safety and freeze boundary

- Existing `evaluation/cases`, `evaluation/formal-final`, and
  `evaluation/formal-final-attempt-2` assets remain immutable historical
  evidence.
- `formal_holdout_created=false` is intentional. A new holdout may be created
  only after a future candidate is frozen and must not be used for tuning.
- `real_provider_evidence=false` is intentional. Synthetic fixtures are not
  Gmail, Calendar, ClickUp, or PostgreSQL observations.
- `real_mailbox_accessed=false` is mandatory for these offline assets. The
  personally owned pilot account has not been connected or queried.
- Email addresses and URLs use reserved `example.com` or `example.test`
  domains. Attachment bytes, credentials, tokens, authorization payloads, and
  production identifiers are excluded.
- Required safety measurements remain fail closed; missing review or future
  Provider evidence must not be presented as a passing zero.

## Final benchmark plan

The 120 visible email cases are a candidate pool, not the final benchmark.
After human review, select 70 visible cases, freeze the candidate code, prompt,
policy, schemas, runner, scorer, fixtures, and case IDs, and only then create 30
new independently reviewed holdout cases. The final 100-case benchmark must be
run as one batch. The holdout may not be used for tuning or rerun after its
first formal attempt.

All 140 Stage 5 control cases require human review. The future 30-case holdout
requires an independent reviewer. Calendar and ClickUp remain offline fixtures
until separately approved; Gmail pilot approval does not authorize either
integration.

## Reproduce and validate

```powershell
uv run python scripts/build_dataset_vnext.py
uv run python scripts/build_dataset_vnext.py --check
uv run pytest -q tests/unit/test_dataset_vnext_contract.py
```

The first command deterministically rebuilds candidate assets. The second is
read-only and validates both manifests, Schema, cross-file references,
coverage, draft-review status, holdout absence, and every asset hash.
