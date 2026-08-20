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
side effects.

## Stage 5 offline boundary coverage

| Contract | Cases | Coverage |
| --- | ---: | --- |
| Gmail access policy | 30 | 5 exact-policy allow; 25 deny before query |
| Pagination and cursor | 20 | hard cap, page cap, duplicates, invalid cursor, token loop |
| Provider-message mapping | 30 | 20 labelled; 10 outside the allowlist |
| Logging and persistence | 20 | forbidden fields and 0/7/90-day retention boundaries |
| Access/injection quadrants | 20 | 5 per quadrant |
| Response-safety scorer calibration | 20 | 10 expected pass; 10 expected fail |

The four access/injection quadrants separately cover allowed-benign,
allowed-malicious, disallowed-benign, and disallowed-malicious messages.
Disallowed messages are neither discovered nor fetched. Allowed malicious
messages are fetched only within the bounded access contract and must be
stopped by the content-security gate with zero external side effects.

Response-safety calibration now makes the missing warning/refusal metric
explicit, but no runtime scorer or model result exists yet. It must remain
reported as unmeasured until a reviewed scorer evaluates a frozen candidate.

## Gmail provider-shape coverage

The offline provider corpus separates the reviewed `Inbox2Action` display name
from synthetic immutable label ID `Label_Inbox2Action_001`. Five label-directory
fixtures cover exact resolution, missing label, renamed label, duplicate exact
names, and an empty directory. Twenty-seven `messages.list` responses contain
only message/thread references, use the resolved label ID plus the bounded
query, and form the page chains used by the 20 pagination cases.

The 30 `messages.get(format=FULL)` fixtures cover top-level plain text, HTML,
`multipart/alternative`, `multipart/mixed`, nested multipart, attachment
references without bytes, inline images, RFC 2047 subjects, missing subjects,
tracking parameters, verification codes, and hidden HTML. Exact content Gold
records make normalization and model-input comparison deterministic.
