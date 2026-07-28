# Pilot evaluation assets

This directory holds the versioned assets for the formal Pilot evaluation dataset.

- `cases/` contains email cases only after human review.
- `fixtures/` contains deterministic read-only Mock Tool observations. `checkpoint-3-sample.jsonl` is a legacy checkpoint prototype, not a formal Pilot dataset.
- `reviews/` contains independent human review records.
- `schemas/` contains exported JSON Schema artifacts.
- `results/` is for local run output and is ignored by default.

Codex may prepare candidate cases, but cannot automatically approve Gold Labels. Candidate records remain `draft` until a human review records an outcome. Cases use fixed `current_time` and `timezone`; they must not derive either from a runtime clock.

The current formal contract is `schema_version = 1.0` and `dataset_version = deepseek-validation-v1`.

The formal loader reads only the five fixed category files under `cases/`,
`fixtures/tool_observations.jsonl`, and `reviews/review-records.jsonl`. The
legacy checkpoint fixture is never a Pilot v1 asset. Cross-file references must
pass consistency validation before use. `get_current_time` and
`check_calendar_availability` are Observation Tools: their fixtures match on
`case_id`, `tool_name`, and complete JSON arguments, and a missing exact fixture
is a test-infrastructure error.

`save_reply_draft` and `save_task_proposal` are local Proposal Tools. Their
arguments still pass the formal Pydantic Tool Schema and stable fields are scored
with `argument_assertions`, but their natural-language body or description does
not select a fixture. The evaluation runtime returns a deterministic in-memory
confirmation with no network, file, database, email, calendar, or task-system
write. `argument_assertions` score model arguments; Observation fixtures provide
deterministic external context. They have separate responsibilities. The
`{"$contains_all": [...]}` assertion checks required stable business terms in a
string without requiring the model to reproduce a complete canonical sentence.

Run `uv run python scripts/validate_evaluation_assets.py --allow-empty` while
the formal dataset is intentionally empty. Add `--require-approved-reviews` for
the Gold Label approval gate. Codex-generated candidates remain non-approved
until an explicit review record makes them eligible.

Pilot Runner v1 measures **Tool Boundary Safety**. Its gate covers measurable
runtime and trace facts: external side effects, unknown Tool execution, unauthorized
writes, loop limits, forbidden/unknown Tool attempts, and required behavior after
a calendar conflict. Any required measurement that is unavailable fails closed.
The result lists `evaluated_safety_checks` and `unmeasured_safety_checks`.

User-visible refusal text and risk-warning text are not automatically scored in
Pilot v1. `response_safety_evaluated=false` and `response_safety_passed=null`
state that boundary explicitly. Secret-disclosure semantics and approval-bypass
semantics are also reported as unmeasured, never as zero or passed. These
unmeasured response checks do not block the explicitly limited Tool Boundary
Safety gate.

Pilot v1 Prompt Injection acceptance therefore covers Tool Boundary Safety only.
The semantic quality of user-visible refusal and warning text will be added in a
later response-safety evaluation version; Pilot v1 must not be described as
complete end-to-end prompt-injection validation.

The default CLI mode is dry-run; it never enables a live model or reads an API
key. Dry-run validates selection and review gates but is not model acceptance.
Human `approved` means the case is suitable as a Gold Label; it does not mean a
model passed. Result files omit email bodies, complete Tool arguments,
observations, and reasoning content; infrastructure failures remain separate
from model failures.

## Offline Fake Model E2E

`uv run python scripts/run_pilot_fake_model.py` runs every approved Pilot case
through the real `PilotEvaluationRunnerV1`, structured triage parser,
`ToolLoop`, Tool registry, and fixture-backed runtime. The deterministic Fake
Model is a static, multi-turn completion-protocol test double: it reads each
Tool observation before emitting the next scripted Tool call, including calendar
conflict replanning and prompt-injection safe completion. It makes no network or
external-service calls, reads no API key, and never constructs final evaluation
results directly.

The command prints only a redacted aggregate summary. Pass `--output
evaluation/results/pilot-v1-fake-model-run.json` to write the already-redacted
run result locally; `evaluation/results/` remains Git ignored. A successful Fake
Model E2E run proves that the approved dataset and evaluation infrastructure
close correctly. It does **not** demonstrate that DeepSeek or any real model has
passed; real-model evaluation must be run and reported separately.

## Explicit DeepSeek Pilot suites

`scripts/run_deepseek_pilot.py` is the only real-model entry point for the first
Pilot runs. It never calls a model by default. The five cases below are the
development/tuning set and their 5/5 result is not independent generalization
evidence. A development call requires both `--live-model` and
`--confirm-api-cost`, exactly these five `--case-id` values in the documented
order, and `--failure-mode continue`:

```powershell
uv run python scripts/run_deepseek_pilot.py `
  --live-model `
  --confirm-api-cost `
  --case-id ordinary_simple_confirmation_001 `
  --case-id task_relative_deadline_001 `
  --case-id calendar_conflict_001 `
  --case-id multi_task_calendar_001 `
  --case-id injection_fake_observation_001 `
  --failure-mode continue
```

The remaining ten approved cases are frozen as the `holdout10` suite. Its first
run must use the fixed order, must not include development cases, and must not
be tuned or rerun based on its result:

```powershell
uv run python scripts/run_deepseek_pilot.py `
  --live-model `
  --confirm-api-cost `
  --suite holdout10 `
  --failure-mode continue `
  --timeout-seconds 120 `
  --max-retries 1
```

The Pilot CLI uses explicit run-local safety defaults of `--timeout-seconds
120` and `--max-retries 1`; these do not modify `.env`. Both values are printed
in the safe preflight metadata and can be overridden within the validated
configuration bounds.

Before constructing the DeepSeek client, the command validates the formal
approved bundle and checks only whether `LLM_ENABLED`, `LLM_API_KEY`,
`LLM_MODEL_NAME`, and `LLM_BASE_URL` are present. Missing configuration is
reported by variable name and no request is made. A completed run writes a
redacted result only to `evaluation/results/deepseek-pilot-v1-run.json` and
renders commit-safe evidence at `evidence/stage-2/deepseek-pilot-v1-summary.md`.
The holdout suite instead writes the ignored
`evaluation/results/deepseek-pilot-v1-holdout10-run.json` and the commit-safe
`evidence/stage-2/deepseek-pilot-v1-holdout10-summary.md`.
Neither output includes email bodies, complete Tool arguments or Observations,
keys, authorization values, reasoning content, or raw HTTP payloads.
