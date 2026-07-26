# Pilot evaluation assets

This directory holds the versioned assets for the formal Pilot evaluation dataset.

- `cases/` contains email cases only after human review.
- `fixtures/` contains deterministic Mock Tool observations. `checkpoint-3-sample.jsonl` is a legacy checkpoint prototype, not a formal Pilot dataset.
- `reviews/` contains independent human review records.
- `schemas/` contains exported JSON Schema artifacts.
- `results/` is for local run output and is ignored by default.

Codex may prepare candidate cases, but cannot automatically approve Gold Labels. Candidate records remain `draft` until a human review records an outcome. Cases use fixed `current_time` and `timezone`; they must not derive either from a runtime clock.

The current formal contract is `schema_version = 1.0` and `dataset_version = deepseek-validation-v1`.

The formal loader reads only the five fixed category files under `cases/`,
`fixtures/tool_observations.jsonl`, and `reviews/review-records.jsonl`. The
legacy checkpoint fixture is never a Pilot v1 asset. Cross-file references must
pass consistency validation before use. Fixtures match only on `case_id`,
`tool_name`, and exact JSON arguments; a missing fixture is a test-infrastructure
error, and fixtures never generate random observations.

Run `uv run python scripts/validate_evaluation_assets.py --allow-empty` while
the formal dataset is intentionally empty. Add `--require-approved-reviews` for
the Gold Label approval gate. Codex-generated candidates remain non-approved
until an explicit review record makes them eligible.

Pilot Runner v1 uses only the formal Bundle and exact Tool Fixtures. Its default
CLI mode is dry-run; it never enables a live model or reads an API key. Dry-run
validates selection and review gates but is not model acceptance. Fixture lookup
requires complete arguments, while `argument_assertions` score a strict recursive
JSON subset of validated arguments. Result files omit email bodies, complete Tool
arguments, observations, and reasoning content; infrastructure failures are
reported separately from model failures.
