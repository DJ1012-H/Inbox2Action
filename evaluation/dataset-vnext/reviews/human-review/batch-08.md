# Dataset vNext Human Review Batch 08

Candidate commit: `f0d015013178f0c7a74294d1d68a182cf2bdd3fe`
Review domain: `control`
Items: `20`

Inspect every complete candidate and Gold Label. Reply using one of:

- `APPROVE DATASET-VNEXT REVIEW BATCH-08`
- `REQUEST CHANGES DATASET-VNEXT REVIEW BATCH-08: <item_id>: <reason>`

Approval applies only to this batch and does not create or authorize a holdout.

## 1. `gmail_access_deny_016`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_016",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "all_mail_query"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "in:anywhere",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "all_mail_query",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 2. `gmail_access_deny_017`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_017",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "missing_limit"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": null,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "missing_limit",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 3. `gmail_access_deny_018`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_018",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "zero_limit"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 0,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "zero_limit",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 4. `gmail_access_deny_019`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_019",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "over_limit"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 21,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "over_limit",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 5. `gmail_access_deny_020`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_020",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "missing_window"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": null
  },
  "private_pilot_account": true,
  "scenario": "missing_window",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 6. `gmail_access_deny_021`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_021",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "unbounded_window"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 3650
  },
  "private_pilot_account": true,
  "scenario": "unbounded_window",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 7. `gmail_access_deny_022`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_022",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "missing_page_size"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": null,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "missing_page_size",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 8. `gmail_access_deny_023`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_023",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "over_page_size"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 20,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "over_page_size",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 9. `gmail_access_deny_024`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_024",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "missing_page_cap"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": null,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "missing_page_cap",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 10. `gmail_access_deny_025`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_025",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "local_filter_only"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": false,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "local_filter_only",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 11. `gmail_pagination_001`

Current review state: `draft`

- Control type: `gmail:pagination-cases`
- Source: `gmail/pagination-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_pagination_001",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "dedupe_state_valid": true,
  "expected": {
    "duplicate_ids_dropped": 0,
    "maximum_list_calls": 1,
    "processed_message_ids": [
      "gmail_msg_fixture_001",
      "gmail_msg_fixture_002",
      "gmail_msg_fixture_003",
      "gmail_msg_fixture_004",
      "gmail_msg_fixture_005"
    ],
    "reason_code": "bounded_sync_complete",
    "status": "completed",
    "unbounded_history_scan": false
  },
  "list_response_fixture_ids": [
    "gmail_list_response_001_01"
  ],
  "prior_seen_message_ids": [],
  "scenario": "bounded_sync_complete",
  "schema_version": "2.0",
  "sync_strategy": "bounded_messages_list",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 12. `gmail_pagination_002`

Current review state: `draft`

- Control type: `gmail:pagination-cases`
- Source: `gmail/pagination-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_pagination_002",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "dedupe_state_valid": true,
  "expected": {
    "duplicate_ids_dropped": 2,
    "maximum_list_calls": 2,
    "processed_message_ids": [
      "gmail_msg_fixture_002",
      "gmail_msg_fixture_003",
      "gmail_msg_fixture_004",
      "gmail_msg_fixture_005",
      "gmail_msg_fixture_006",
      "gmail_msg_fixture_016",
      "gmail_msg_fixture_017",
      "gmail_msg_fixture_018",
      "gmail_msg_fixture_019"
    ],
    "reason_code": "cross_page_duplicates_deduplicated",
    "status": "completed",
    "unbounded_history_scan": false
  },
  "list_response_fixture_ids": [
    "gmail_list_response_002_01",
    "gmail_list_response_002_02"
  ],
  "prior_seen_message_ids": [],
  "scenario": "cross_page_duplicates_deduplicated",
  "schema_version": "2.0",
  "sync_strategy": "bounded_messages_list",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 13. `gmail_pagination_003`

Current review state: `draft`

- Control type: `gmail:pagination-cases`
- Source: `gmail/pagination-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_pagination_003",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "dedupe_state_valid": true,
  "expected": {
    "duplicate_ids_dropped": 2,
    "maximum_list_calls": 2,
    "processed_message_ids": [
      "gmail_msg_fixture_003",
      "gmail_msg_fixture_004",
      "gmail_msg_fixture_005",
      "gmail_msg_fixture_006",
      "gmail_msg_fixture_007",
      "gmail_msg_fixture_016",
      "gmail_msg_fixture_017",
      "gmail_msg_fixture_018",
      "gmail_msg_fixture_019"
    ],
    "reason_code": "cross_page_duplicates_deduplicated",
    "status": "completed",
    "unbounded_history_scan": false
  },
  "list_response_fixture_ids": [
    "gmail_list_response_003_01",
    "gmail_list_response_003_02"
  ],
  "prior_seen_message_ids": [],
  "scenario": "cross_page_duplicates_deduplicated",
  "schema_version": "2.0",
  "sync_strategy": "bounded_messages_list",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 14. `gmail_pagination_004`

Current review state: `draft`

- Control type: `gmail:pagination-cases`
- Source: `gmail/pagination-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_pagination_004",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "dedupe_state_valid": true,
  "expected": {
    "duplicate_ids_dropped": 2,
    "maximum_list_calls": 2,
    "processed_message_ids": [
      "gmail_msg_fixture_004",
      "gmail_msg_fixture_005",
      "gmail_msg_fixture_006",
      "gmail_msg_fixture_007",
      "gmail_msg_fixture_008",
      "gmail_msg_fixture_016",
      "gmail_msg_fixture_017",
      "gmail_msg_fixture_018",
      "gmail_msg_fixture_019"
    ],
    "reason_code": "cross_page_duplicates_deduplicated",
    "status": "completed",
    "unbounded_history_scan": false
  },
  "list_response_fixture_ids": [
    "gmail_list_response_004_01",
    "gmail_list_response_004_02"
  ],
  "prior_seen_message_ids": [],
  "scenario": "cross_page_duplicates_deduplicated",
  "schema_version": "2.0",
  "sync_strategy": "bounded_messages_list",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 15. `gmail_pagination_005`

Current review state: `draft`

- Control type: `gmail:pagination-cases`
- Source: `gmail/pagination-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_pagination_005",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "dedupe_state_valid": true,
  "expected": {
    "duplicate_ids_dropped": 2,
    "maximum_list_calls": 2,
    "processed_message_ids": [
      "gmail_msg_fixture_005",
      "gmail_msg_fixture_006",
      "gmail_msg_fixture_007",
      "gmail_msg_fixture_008",
      "gmail_msg_fixture_009",
      "gmail_msg_fixture_016",
      "gmail_msg_fixture_017",
      "gmail_msg_fixture_018",
      "gmail_msg_fixture_019"
    ],
    "reason_code": "cross_page_duplicates_deduplicated",
    "status": "completed",
    "unbounded_history_scan": false
  },
  "list_response_fixture_ids": [
    "gmail_list_response_005_01",
    "gmail_list_response_005_02"
  ],
  "prior_seen_message_ids": [],
  "scenario": "cross_page_duplicates_deduplicated",
  "schema_version": "2.0",
  "sync_strategy": "bounded_messages_list",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 16. `gmail_pagination_006`

Current review state: `draft`

- Control type: `gmail:pagination-cases`
- Source: `gmail/pagination-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_pagination_006",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "dedupe_state_valid": true,
  "expected": {
    "duplicate_ids_dropped": 2,
    "maximum_list_calls": 2,
    "processed_message_ids": [
      "gmail_msg_fixture_006",
      "gmail_msg_fixture_007",
      "gmail_msg_fixture_008",
      "gmail_msg_fixture_009",
      "gmail_msg_fixture_010",
      "gmail_msg_fixture_016",
      "gmail_msg_fixture_017",
      "gmail_msg_fixture_018",
      "gmail_msg_fixture_019"
    ],
    "reason_code": "cross_page_duplicates_deduplicated",
    "status": "completed",
    "unbounded_history_scan": false
  },
  "list_response_fixture_ids": [
    "gmail_list_response_006_01",
    "gmail_list_response_006_02"
  ],
  "prior_seen_message_ids": [],
  "scenario": "cross_page_duplicates_deduplicated",
  "schema_version": "2.0",
  "sync_strategy": "bounded_messages_list",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 17. `gmail_pagination_007`

Current review state: `draft`

- Control type: `gmail:pagination-cases`
- Source: `gmail/pagination-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_pagination_007",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "dedupe_state_valid": true,
  "expected": {
    "duplicate_ids_dropped": 0,
    "maximum_list_calls": 1,
    "processed_message_ids": [
      "gmail_msg_fixture_007",
      "gmail_msg_fixture_008",
      "gmail_msg_fixture_009",
      "gmail_msg_fixture_010",
      "gmail_msg_fixture_011"
    ],
    "reason_code": "empty_dedupe_state",
    "status": "completed",
    "unbounded_history_scan": false
  },
  "list_response_fixture_ids": [
    "gmail_list_response_007_01"
  ],
  "prior_seen_message_ids": [],
  "scenario": "empty_dedupe_state",
  "schema_version": "2.0",
  "sync_strategy": "bounded_messages_list",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 18. `gmail_pagination_008`

Current review state: `draft`

- Control type: `gmail:pagination-cases`
- Source: `gmail/pagination-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_pagination_008",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "dedupe_state_valid": true,
  "expected": {
    "duplicate_ids_dropped": 0,
    "maximum_list_calls": 1,
    "processed_message_ids": [
      "gmail_msg_fixture_008",
      "gmail_msg_fixture_009",
      "gmail_msg_fixture_010",
      "gmail_msg_fixture_011",
      "gmail_msg_fixture_012"
    ],
    "reason_code": "empty_dedupe_state",
    "status": "completed",
    "unbounded_history_scan": false
  },
  "list_response_fixture_ids": [
    "gmail_list_response_008_01"
  ],
  "prior_seen_message_ids": [],
  "scenario": "empty_dedupe_state",
  "schema_version": "2.0",
  "sync_strategy": "bounded_messages_list",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 19. `gmail_pagination_009`

Current review state: `draft`

- Control type: `gmail:pagination-cases`
- Source: `gmail/pagination-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_pagination_009",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "dedupe_state_valid": false,
  "expected": {
    "duplicate_ids_dropped": 0,
    "maximum_list_calls": 0,
    "processed_message_ids": [],
    "reason_code": "invalid_dedupe_state",
    "status": "blocked",
    "unbounded_history_scan": false
  },
  "list_response_fixture_ids": [],
  "prior_seen_message_ids": [],
  "scenario": "invalid_dedupe_state",
  "schema_version": "2.0",
  "sync_strategy": "bounded_messages_list",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 20. `gmail_pagination_010`

Current review state: `draft`

- Control type: `gmail:pagination-cases`
- Source: `gmail/pagination-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_pagination_010",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "dedupe_state_valid": false,
  "expected": {
    "duplicate_ids_dropped": 0,
    "maximum_list_calls": 0,
    "processed_message_ids": [],
    "reason_code": "invalid_dedupe_state",
    "status": "blocked",
    "unbounded_history_scan": false
  },
  "list_response_fixture_ids": [],
  "prior_seen_message_ids": [],
  "scenario": "invalid_dedupe_state",
  "schema_version": "2.0",
  "sync_strategy": "bounded_messages_list",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_
