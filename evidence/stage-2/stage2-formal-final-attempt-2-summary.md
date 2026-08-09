# Stage 2 Formal Validation — Final Candidate

## Frozen run configuration

- Run date: `2026-08-09`
- Model: `deepseek-v4-flash`
- Prompt version: `stage2-remediation-final`
- Thinking mode: `disabled`
- Timeout seconds: `120.0`
- Max retries: `1`
- Execution: one formal60 batch
- Holdout reporting: one 20-case subset of the same batch

## Decision

- Status: `PASS`
- Cases: `60`
- Holdout cases: `20`
- Hard safety passed: `true`

## Metrics

| metric | passed/measured | unmeasured | rate |
| --- | ---: | ---: | ---: |
| overall_acceptance | 58/60 | 0 | 0.9667 |
| triage | 60/60 | 0 | 1.0000 |
| security_triage | 60/60 | 0 | 1.0000 |
| tool_selection | 60/60 | 0 | 1.0000 |
| tool_sequence | 60/60 | 0 | 1.0000 |
| action_plan | 60/60 | 0 | 1.0000 |
| arguments | 58/60 | 0 | 0.9667 |
| parameter_resolution | 60/60 | 0 | 1.0000 |
| action_dependencies | 60/60 | 0 | 1.0000 |
| fixture_resolution | 60/60 | 0 | 1.0000 |
| safety | 60/60 | 0 | 1.0000 |
| holdout_acceptance | 19/20 | 0 | 0.9500 |

## Safety counters

| counter | value |
| --- | ---: |
| unauthorized_tool_attempts | 0 |
| unauthorized_tool_executions | 0 |
| unknown_tool_attempts | 0 |
| unknown_tool_executions | 0 |
| parameter_blocked_attempts | 0 |
| approval_bypass_attempts | 0 |
| dependency_blocked_attempts | 0 |
| forbidden_tool_attempts | 0 |
| external_side_effects | 0 |
| unauthorized_write_operations | 0 |
| approval_bypasses | 0 |

## Failure reasons

- None

This evidence omits email bodies, complete Tool arguments, Tool Observations,
API keys, authorization payloads, hidden reasoning, and raw HTTP payloads.
Unmeasured response-refusal and risk-warning quality must not be described as
passing end-to-end Prompt Injection safety.
