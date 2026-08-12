# Dataset vNext Coverage Matrix

## Email distribution

| Dimension | Measured coverage |
| --- | --- |
| Splits | development 60; regression 30; security challenge 30 |
| Categories | ordinary 15; notification 15; task 15; calendar 15; multi-action 15; prompt injection 45 |
| Languages | zh-CN 70; English 28; zh-TW 22 |
| Triage | IGNORE 15; NOTIFY 60; ACTION_REQUIRED 45 |
| Distinct case IDs | 120/120 |
| Review state | draft 120; approved 0 |

## Source and normalization coverage

| Capability | Cases |
| --- | ---: |
| HTML input | 27 |
| Attachment metadata | 21 |
| Thread context | 27 |
| Long-body truncation | 12 |
| Synthetic PII redaction | 30 |
| Tracking-parameter cleanup | 30 |
| User clarification | 13 |
| Approval-required action | 34 |

Attachment contents and raw Provider payloads are intentionally absent. The
metadata cases establish a future ingestion contract without claiming that the
current normalizer parses attachment bytes.

## Workflow coverage

Each required workflow scenario has three independent synthetic variants:

| Scenario | Variants | Required invariant |
| --- | ---: | --- |
| duplicate delivery | 3 | zero duplicate writes |
| approval edit | 3 | execute only the approved revision |
| stale approval | 3 | block before Provider execution |
| restart recovery | 3 | preserve action identity |
| Provider failure | 3 | fail closed without a false success |
| Provider unknown | 3 | block for reconciliation |
| payload-hash mismatch | 3 | block before execution |
| dependency order | 3 | execute only dependency-ready actions |
| rejection | 3 | terminal route with zero writes |
| retry after failure | 3 | reuse identity without duplicate write |

## Security challenge coverage

Ten attack families each have `zh-CN`, English, and `zh-TW` variants: direct
override, fake system message, credential exfiltration, approval bypass, Tool
impersonation, fake Observation, encoded instruction, attachment instruction,
quoted instruction, and hidden HTML instruction.

These are visible development challenges, not an independent formal holdout.
They measure expected Triage, normalization, Tool/approval boundaries, and zero
side effects. User-visible refusal and risk-warning quality still need a future
explicit scorer before they can be reported as measured.
