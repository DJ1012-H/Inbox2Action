# Stage 10 Security & Evaluation

Stage 10 is an evaluation boundary around the existing Stage 3--9 workflow.
It does not create a second workflow, approval system, execution ledger,
checkpoint, provider executor, or memory store.

## Runner

The offline runner reads the canonical vNext corpus, computes a content-based
SHA-256 dataset identity, writes an ignored JSON report and a Markdown summary,
and returns a non-zero status unless the result is complete:

```powershell
python scripts/run_stage10_evaluation.py --full
python scripts/run_stage10_evaluation.py --dataset-audit
python scripts/run_stage10_evaluation.py --security
python scripts/run_stage10_evaluation.py --memory

# After the opt-in live PostgreSQL evidence runner has completed:
python scripts/run_stage10_evaluation.py --full --postgres-evidence evaluation/results/stage10-postgres.json --run-full-pytest
```

The runner uses only synthetic fixtures and the production allowlist, memory,
checkpoint, and execution-ledger boundaries. It never calls DeepSeek or writes
to ClickUp/Google Calendar. `--live-llm` records an explicit unmeasured gate;
it is not an authorization mechanism and makes no request.

## Authorized DeepSeek observed benchmark

The full observed benchmark is a separate explicit live command. It requires
the existing `RUN_DEEPSEEK_INTEGRATION_TESTS=true` gate and both authorization
flags; credentials remain in the external runtime configuration:

```powershell
$env:RUN_DEEPSEEK_INTEGRATION_TESTS = "true"
python scripts/run_stage10_observed_benchmark.py `
  --live-model --confirm-api-cost --failure-mode continue `
  --json-output evaluation/results/stage10-observed.json `
  --markdown-output evaluation/results/stage10-observed.md
```

This command requires the fixed approved dataset version and all 120 case IDs.
It sends normalized synthetic email content to the configured DeepSeek model,
then exposes only the existing local proposal/read tools. Dataset provider
capabilities such as `create_clickup_task` and `create_calendar_event` are
mapped to local-only proposal tools for observation and scoring. No ClickUp
POST or Google Calendar `Events.insert` path is constructed.

The observed evidence is incorporated into the final machine report only with
the explicit evidence path:

```powershell
python scripts/run_stage10_evaluation.py --full `
  --observed-evidence evaluation/results/stage10-observed.json `
  --postgres-evidence evaluation/results/stage10-postgres.json `
  --run-full-pytest `
  --json-output evaluation/results/stage10-final.json `
  --markdown-output evaluation/results/stage10-final.md
```

## Dataset boundary

`evaluation/dataset-vnext` remains the source of truth. Its case content and
ground truth are not rewritten by the audit. Human review records are the
approval authority; batch receipts do not silently promote draft labels. The
audit reports duplicates, malformed records, missing ground truth, old schema,
coverage distributions, approved/unapproved counts, and a deterministic
content version.

The current corpus contains 120 valid cases and its per-case
`reviews/review-records.jsonl` queue remains 120 `draft` records.  The audit
also loads the separate historical human-review receipts under
`reviews/human-review/approvals/`: six `email` batches cover all 120 case IDs,
share candidate commit `f0d015013178f0c7a74294d1d68a182cf2bdd3fe`, and bind to
the current case blobs.  Their `formal_holdout_authorized=false` field is
preserved.  The current audit therefore reports 120 approved cases with
`approval_provenance.status=verified`; this makes the canonical corpus ready,
but does not by itself measure a model or authorize a formal holdout.

If the receipts are absent, incomplete, duplicated, or cannot be bound to the
candidate case content, the audit fails closed and reports the affected case
IDs as unapproved.  Batch receipts never silently rewrite the draft review
records or promote the seven non-email control batches into this benchmark.

## System acceptance evidence

`scripts/run_stage10_postgres_restart_validation.py --mode both` runs the
existing Stage 4--9 PostgreSQL integration tests, then performs a real
Process-A/Process-B checkpoint resume and invokes the existing Stage 9
cross-process memory validator.  It uses `FixtureWriteExecutor`; the report
must retain `real_provider_writes=0`.  It is opt-in because it writes only the
configured local PostgreSQL test state.

`--run-full-pytest` makes the Stage 10 report execute the complete offline
collection itself.  The two DeepSeek integration tests remain expected skips
unless their separate explicit environment gate is enabled.  A DeepSeek
observed benchmark is not inferred from prior pilot evidence and is not
started by the offline runner.

## Evaluation boundaries

The module exposes deterministic evaluators for:

- triage accuracy, per-class precision/recall/F1, macro F1, and confusion;
- exact tool-set selection and forbidden-tool invocations;
- structured critical arguments and bounded natural-language fields;
- observed trajectory ordering, observation use, replanning, HITL, and replay;
- frozen-clock temporal and trusted-timezone precedence;
- security hard invariants and memory poisoning;
- checkpoint recovery, execution-ledger idempotency, reconciliation, memory
  +/- behavior, and account isolation.

Expected labels are never used as observed model output. Missing observations
remain `UNMEASURED` and cannot satisfy a hard gate.
