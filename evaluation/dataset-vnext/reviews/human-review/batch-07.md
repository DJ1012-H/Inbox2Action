# Dataset vNext Human Review Batch 07

Candidate commit: `f0d015013178f0c7a74294d1d68a182cf2bdd3fe`
Review domain: `control`
Items: `20`

Inspect every complete candidate and Gold Label. Reply using one of:

- `APPROVE DATASET-VNEXT REVIEW BATCH-07`
- `REQUEST CHANGES DATASET-VNEXT REVIEW BATCH-07: <item_id>: <reason>`

Approval applies only to this batch and does not create or authorize a holdout.

## 1. `gmail_access_allow_001`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_allow_001",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "allow_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 2,
    "reason_code": "policy_valid"
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
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "valid_private_label_sync_001",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 2. `gmail_access_allow_002`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_allow_002",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "allow_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 2,
    "reason_code": "policy_valid"
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
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "valid_private_label_sync_002",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 3. `gmail_access_allow_003`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_allow_003",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "allow_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 2,
    "reason_code": "policy_valid"
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
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "valid_private_label_sync_003",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 4. `gmail_access_allow_004`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_allow_004",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "allow_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 2,
    "reason_code": "policy_valid"
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
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "valid_private_label_sync_004",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 5. `gmail_access_allow_005`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_allow_005",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "allow_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 2,
    "reason_code": "policy_valid"
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
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "valid_private_label_sync_005",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 6. `gmail_access_deny_001`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_001",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "missing_scope"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "missing_scope",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 7. `gmail_access_deny_002`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_002",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "scope_modify"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.modify"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "scope_modify",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 8. `gmail_access_deny_003`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_003",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "scope_compose"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.compose"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "scope_compose",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 9. `gmail_access_deny_004`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_004",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "scope_send"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.send"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "scope_send",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 10. `gmail_access_deny_005`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_005",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "scope_mail_google"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://mail.google.com/"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "scope_mail_google",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 11. `gmail_access_deny_006`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_006",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "extra_scope"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly",
      "profile"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Inbox2Action_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "extra_scope",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 12. `gmail_access_deny_007`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_007",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "missing_mode"
  },
  "input": {
    "access_mode": null,
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
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "missing_mode",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 13. `gmail_access_deny_008`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_008",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "invalid_mode"
  },
  "input": {
    "access_mode": "AUTO_INGEST",
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
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "invalid_mode",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 14. `gmail_access_deny_009`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_009",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "missing_label"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": null,
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
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "missing_label",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 15. `gmail_access_deny_010`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_010",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "empty_label"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "",
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
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "empty_label",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 16. `gmail_access_deny_011`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_011",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "wrong_label"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "INBOX",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_valid",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": "Label_Other_001",
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "wrong_label",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 17. `gmail_access_deny_012`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_012",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "label_directory_missing"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_missing",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": null,
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "label_directory_missing",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 18. `gmail_access_deny_013`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_013",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "label_directory_ambiguous"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "label:Inbox2Action newer_than:30d",
    "label_directory_fixture_id": "gmail_label_directory_ambiguous",
    "max_messages_per_sync": 20,
    "max_pages": 2,
    "oauth_scopes": [
      "https://www.googleapis.com/auth/gmail.readonly"
    ],
    "page_size": 10,
    "provider_side_filter": true,
    "resolved_label_id": null,
    "time_window_days": 30
  },
  "private_pilot_account": true,
  "scenario": "label_directory_ambiguous",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 19. `gmail_access_deny_014`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_014",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "missing_query"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": null,
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
  "scenario": "missing_query",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 20. `gmail_access_deny_015`

Current review state: `draft`

- Control type: `gmail:access-policy-cases`
- Source: `gmail/access-policy-cases.jsonl`

Complete control candidate and Gold:

```json
{
  "case_id": "gmail_access_deny_015",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "decision": "deny_before_query",
    "inbox_wide_query_allowed": false,
    "maximum_list_calls": 0,
    "reason_code": "inbox_wide_query"
  },
  "input": {
    "access_mode": "LABEL_ALLOWLIST",
    "allowed_label": "Inbox2Action",
    "gmail_query": "in:inbox",
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
  "scenario": "inbox_wide_query",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_
