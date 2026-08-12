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
- `schemas/`: exported JSON Schema artifacts.
- `manifest.json`: counts and LF-normalized SHA-256 hashes.

## Safety and freeze boundary

- Existing `evaluation/cases`, `evaluation/formal-final`, and
  `evaluation/formal-final-attempt-2` assets remain immutable historical
  evidence.
- `formal_holdout_created=false` is intentional. A new holdout may be created
  only after a future candidate is frozen and must not be used for tuning.
- `real_provider_evidence=false` is intentional. Synthetic fixtures are not
  Gmail, Calendar, ClickUp, or PostgreSQL observations.
- Email addresses and URLs use reserved `example.com` or `example.test`
  domains. Attachment bytes, credentials, tokens, authorization payloads, and
  production identifiers are excluded.
- Required safety measurements remain fail closed; missing review or future
  Provider evidence must not be presented as a passing zero.

## Reproduce and validate

```powershell
uv run python scripts/build_dataset_vnext.py
uv run python scripts/build_dataset_vnext.py --check
uv run pytest -q tests/unit/test_dataset_vnext_contract.py
```

The first command deterministically rebuilds candidate assets. The second is
read-only and validates Schema, cross-file references, coverage, draft-review
status, holdout absence, and every manifest hash.
