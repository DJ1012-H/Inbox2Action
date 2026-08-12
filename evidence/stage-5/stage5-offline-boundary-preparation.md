# Stage 5 Offline Boundary Preparation

Date: 2026-08-12

## Evidence mode

`OFFLINE_FIXTURE` and `DETERMINISTIC_TEST` only.

This record covers candidate dataset generation and contract validation. It is
implementation-ready preparation, not Stage 5 real Gmail integration
acceptance.

## Scope and non-evidence

- No real Gmail mailbox was accessed.
- No Gmail API call was made.
- No OAuth login, authorization, token, or Google credential was used.
- No real Provider evidence was collected.
- No production Gmail client, policy, adapter, worker, or ingestion pipeline
  was added.
- No formal holdout was created.
- All Stage 5 reviews remain `draft`.
- All fixtures and control records are `synthetic_only=true`.
- The readonly scope and pilot constants are offline contract values only; they
  are not an OAuth configuration or a claim that access was requested or
  verified.

## Candidate assets

The deterministic rebuild retains the existing vNext corpus: 120 email cases
(60 development, 30 regression, 30 security challenge), 60 provider fixtures,
30 workflow scenarios, and 120 draft reviews.

The additional Stage 5 candidate assets contain:

- 30 Gmail access-policy cases;
- 20 bounded pagination cases;
- 30 synthetic Gmail API message fixtures;
- 5 synthetic Gmail label-directory fixtures;
- 27 provider-shaped Gmail `messages.list` response fixtures;
- 30 content/data-boundary cases;
- 20 logging/persistence cases;
- 20 access-control by prompt-injection quadrant cases;
- 20 response-safety calibration cases;
- 140 draft control reviews;
- 7 Gmail boundary JSON Schemas and LF-normalized SHA-256 manifest entries.

The Gmail boundary manifest records `real_mailbox_accessed=false` and
`real_provider_evidence=false`.

The provider-shaped fixtures use synthetic immutable label IDs rather than
placing display names in `Message.labelIds`. FULL message payloads include
nested MIME structures and attachment references without attachment bytes.
Content-policy records contain exact sanitized text and hashes; this remains an
offline oracle and is not evidence that a production normalizer implements it.

## Verification run

The following local checks were executed with the project `.venv` and without
network or external-service configuration:

- deterministic rebuild: passed;
- read-only dataset check: passed;
- Stage 5 and vNext contract tests: passed (`10 passed` for
  `tests/unit/test_dataset_vnext_contract.py`);
- full repository regression: passed (`273 passed, 3 skipped`); the skipped
  cases remain explicit opt-in DeepSeek and PostgreSQL integrations and are not
  counted as Stage 5 evidence;
- Ruff on the changed Python files: passed;
- Mypy on the related source files: passed;
- Bandit on the Stage 5 source file: passed;
- `git diff --check`: passed.

Skipped, unmeasured, and not-executed external integration evidence is not
counted as a pass.

## Remaining gate

Stage 5 real Gmail work remains blocked until the user separately completes
Google Cloud project/API enablement, OAuth consent/client configuration,
credential storage review, and explicit approval for a bounded real-mailbox
pilot. Those prerequisites are outside this offline preparation change.
