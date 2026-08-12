# Dataset vNext Human Review Batch 11

Candidate commit: `f0d015013178f0c7a74294d1d68a182cf2bdd3fe`
Review domain: `control`
Items: `20`

Inspect every complete candidate and Gold Label. Reply using one of:

- `APPROVE DATASET-VNEXT REVIEW BATCH-11`
- `REQUEST CHANGES DATASET-VNEXT REVIEW BATCH-11: <item_id>: <reason>`

Approval applies only to this batch and does not create or authorize a holdout.

## 1. `gmail_observability_001`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "logging",
  "case_id": "gmail_observability_001",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "bounded_failure_type": "none",
      "classification_result": "action_required",
      "gmail_message_id": "gmail_msg_fixture_001",
      "processing_status": "classification_completed",
      "trace_id": "trace-stage5-001"
    },
    "retention_action": "emit_redacted_log",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-01",
    "attachment_content": "synthetic-attachment-bytes-01",
    "authorization_header": "Bearer synthetic-01",
    "bounded_failure_type": "none",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-01@example.com",
    "complete_message_body": "synthetic private body 01",
    "gmail_message_id": "gmail_msg_fixture_001",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-01",
    "processing_status": "classification_completed",
    "received_timestamp": "2026-07-01T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-01",
    "trace_id": "trace-stage5-001"
  },
  "scenario": "classification_completed",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 2. `gmail_observability_002`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "logging",
  "case_id": "gmail_observability_002",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "bounded_failure_type": "access_policy_denied",
      "classification_result": "action_required",
      "gmail_message_id": "gmail_msg_fixture_002",
      "processing_status": "access_policy_denied",
      "trace_id": "trace-stage5-002"
    },
    "retention_action": "emit_redacted_log",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-02",
    "attachment_content": "synthetic-attachment-bytes-02",
    "authorization_header": "Bearer synthetic-02",
    "bounded_failure_type": "access_policy_denied",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-02@example.com",
    "complete_message_body": "synthetic private body 02",
    "gmail_message_id": "gmail_msg_fixture_002",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-02",
    "processing_status": "access_policy_denied",
    "received_timestamp": "2026-07-02T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-02",
    "trace_id": "trace-stage5-002"
  },
  "scenario": "access_policy_denied",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 3. `gmail_observability_003`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "logging",
  "case_id": "gmail_observability_003",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "bounded_failure_type": "pagination_loop_blocked",
      "classification_result": "action_required",
      "gmail_message_id": "gmail_msg_fixture_003",
      "processing_status": "pagination_loop_blocked",
      "trace_id": "trace-stage5-003"
    },
    "retention_action": "emit_redacted_log",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-03",
    "attachment_content": "synthetic-attachment-bytes-03",
    "authorization_header": "Bearer synthetic-03",
    "bounded_failure_type": "pagination_loop_blocked",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-03@example.com",
    "complete_message_body": "synthetic private body 03",
    "gmail_message_id": "gmail_msg_fixture_003",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-03",
    "processing_status": "pagination_loop_blocked",
    "received_timestamp": "2026-07-03T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-03",
    "trace_id": "trace-stage5-003"
  },
  "scenario": "pagination_loop_blocked",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 4. `gmail_observability_004`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "logging",
  "case_id": "gmail_observability_004",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "bounded_failure_type": "provider_timeout_bounded",
      "classification_result": "action_required",
      "gmail_message_id": "gmail_msg_fixture_004",
      "processing_status": "provider_timeout_bounded",
      "trace_id": "trace-stage5-004"
    },
    "retention_action": "emit_redacted_log",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-04",
    "attachment_content": "synthetic-attachment-bytes-04",
    "authorization_header": "Bearer synthetic-04",
    "bounded_failure_type": "provider_timeout_bounded",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-04@example.com",
    "complete_message_body": "synthetic private body 04",
    "gmail_message_id": "gmail_msg_fixture_004",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-04",
    "processing_status": "provider_timeout_bounded",
    "received_timestamp": "2026-07-04T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-04",
    "trace_id": "trace-stage5-004"
  },
  "scenario": "provider_timeout_bounded",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 5. `gmail_observability_005`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "logging",
  "case_id": "gmail_observability_005",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "bounded_failure_type": "content_injection_blocked",
      "classification_result": "prompt_injection",
      "gmail_message_id": "gmail_msg_fixture_005",
      "processing_status": "content_injection_blocked",
      "trace_id": "trace-stage5-005"
    },
    "retention_action": "emit_redacted_log",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-05",
    "attachment_content": "synthetic-attachment-bytes-05",
    "authorization_header": "Bearer synthetic-05",
    "bounded_failure_type": "content_injection_blocked",
    "classification_result": "prompt_injection",
    "complete_headers": "From: synthetic-05@example.com",
    "complete_message_body": "synthetic private body 05",
    "gmail_message_id": "gmail_msg_fixture_005",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-05",
    "processing_status": "content_injection_blocked",
    "received_timestamp": "2026-07-05T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-05",
    "trace_id": "trace-stage5-005"
  },
  "scenario": "content_injection_blocked",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 6. `gmail_observability_006`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "logging",
  "case_id": "gmail_observability_006",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "bounded_failure_type": "none",
      "classification_result": "action_required",
      "gmail_message_id": "gmail_msg_fixture_006",
      "processing_status": "duplicate_message_skipped",
      "trace_id": "trace-stage5-006"
    },
    "retention_action": "emit_redacted_log",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-06",
    "attachment_content": "synthetic-attachment-bytes-06",
    "authorization_header": "Bearer synthetic-06",
    "bounded_failure_type": "none",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-06@example.com",
    "complete_message_body": "synthetic private body 06",
    "gmail_message_id": "gmail_msg_fixture_006",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-06",
    "processing_status": "duplicate_message_skipped",
    "received_timestamp": "2026-07-06T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-06",
    "trace_id": "trace-stage5-006"
  },
  "scenario": "duplicate_message_skipped",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 7. `gmail_observability_007`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "logging",
  "case_id": "gmail_observability_007",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "bounded_failure_type": "normalization_failed_closed",
      "classification_result": "action_required",
      "gmail_message_id": "gmail_msg_fixture_007",
      "processing_status": "normalization_failed_closed",
      "trace_id": "trace-stage5-007"
    },
    "retention_action": "emit_redacted_log",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-07",
    "attachment_content": "synthetic-attachment-bytes-07",
    "authorization_header": "Bearer synthetic-07",
    "bounded_failure_type": "normalization_failed_closed",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-07@example.com",
    "complete_message_body": "synthetic private body 07",
    "gmail_message_id": "gmail_msg_fixture_007",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-07",
    "processing_status": "normalization_failed_closed",
    "received_timestamp": "2026-07-07T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-07",
    "trace_id": "trace-stage5-007"
  },
  "scenario": "normalization_failed_closed",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 8. `gmail_observability_008`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "logging",
  "case_id": "gmail_observability_008",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "bounded_failure_type": "message_not_found",
      "classification_result": "action_required",
      "gmail_message_id": "gmail_msg_fixture_008",
      "processing_status": "message_not_found",
      "trace_id": "trace-stage5-008"
    },
    "retention_action": "emit_redacted_log",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-08",
    "attachment_content": "synthetic-attachment-bytes-08",
    "authorization_header": "Bearer synthetic-08",
    "bounded_failure_type": "message_not_found",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-08@example.com",
    "complete_message_body": "synthetic private body 08",
    "gmail_message_id": "gmail_msg_fixture_008",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-08",
    "processing_status": "message_not_found",
    "received_timestamp": "2026-07-08T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-08",
    "trace_id": "trace-stage5-008"
  },
  "scenario": "message_not_found",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 9. `gmail_observability_009`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "logging",
  "case_id": "gmail_observability_009",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "bounded_failure_type": "none",
      "classification_result": "action_required",
      "gmail_message_id": "gmail_msg_fixture_009",
      "processing_status": "bounded_result_empty",
      "trace_id": "trace-stage5-009"
    },
    "retention_action": "emit_redacted_log",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-09",
    "attachment_content": "synthetic-attachment-bytes-09",
    "authorization_header": "Bearer synthetic-09",
    "bounded_failure_type": "none",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-09@example.com",
    "complete_message_body": "synthetic private body 09",
    "gmail_message_id": "gmail_msg_fixture_009",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-09",
    "processing_status": "bounded_result_empty",
    "received_timestamp": "2026-07-09T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-09",
    "trace_id": "trace-stage5-009"
  },
  "scenario": "bounded_result_empty",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 10. `gmail_observability_010`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "logging",
  "case_id": "gmail_observability_010",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "bounded_failure_type": "none",
      "classification_result": "prompt_injection",
      "gmail_message_id": "gmail_msg_fixture_010",
      "processing_status": "model_invocation_skipped",
      "trace_id": "trace-stage5-010"
    },
    "retention_action": "emit_redacted_log",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-10",
    "attachment_content": "synthetic-attachment-bytes-10",
    "authorization_header": "Bearer synthetic-10",
    "bounded_failure_type": "none",
    "classification_result": "prompt_injection",
    "complete_headers": "From: synthetic-10@example.com",
    "complete_message_body": "synthetic private body 10",
    "gmail_message_id": "gmail_msg_fixture_010",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-10",
    "processing_status": "model_invocation_skipped",
    "received_timestamp": "2026-07-10T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-10",
    "trace_id": "trace-stage5-010"
  },
  "scenario": "model_invocation_skipped",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 11. `gmail_observability_011`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "persistence",
  "case_id": "gmail_observability_011",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "gmail_message_id": "gmail_msg_fixture_011",
      "processing_status": "retention_lifecycle_01",
      "trace_id": "trace-stage5-011"
    },
    "retention_action": "drop_raw_body",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-11",
    "attachment_content": "synthetic-attachment-bytes-11",
    "authorization_header": "Bearer synthetic-11",
    "bounded_failure_type": "retention_lifecycle_01",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-11@example.com",
    "complete_message_body": "synthetic private body 11",
    "gmail_message_id": "gmail_msg_fixture_011",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-11",
    "processing_status": "retention_lifecycle_01",
    "received_timestamp": "2026-07-11T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-11",
    "trace_id": "trace-stage5-011"
  },
  "scenario": "retention_lifecycle_01",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 12. `gmail_observability_012`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "persistence",
  "case_id": "gmail_observability_012",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "gmail_message_id": "gmail_msg_fixture_012",
      "processing_status": "retention_lifecycle_02",
      "trace_id": "trace-stage5-012"
    },
    "retention_action": "expire_sanitized_context",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-12",
    "attachment_content": "synthetic-attachment-bytes-12",
    "authorization_header": "Bearer synthetic-12",
    "bounded_failure_type": "retention_lifecycle_02",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-12@example.com",
    "complete_message_body": "synthetic private body 12",
    "gmail_message_id": "gmail_msg_fixture_012",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-12",
    "processing_status": "retention_lifecycle_02",
    "received_timestamp": "2026-07-12T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-12",
    "trace_id": "trace-stage5-012"
  },
  "scenario": "retention_lifecycle_02",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 13. `gmail_observability_013`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "persistence",
  "case_id": "gmail_observability_013",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "gmail_message_id": "gmail_msg_fixture_013",
      "processing_status": "retention_lifecycle_03",
      "trace_id": "trace-stage5-013"
    },
    "retention_action": "expire_business_result",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-13",
    "attachment_content": "synthetic-attachment-bytes-13",
    "authorization_header": "Bearer synthetic-13",
    "bounded_failure_type": "retention_lifecycle_03",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-13@example.com",
    "complete_message_body": "synthetic private body 13",
    "gmail_message_id": "gmail_msg_fixture_013",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-13",
    "processing_status": "retention_lifecycle_03",
    "received_timestamp": "2026-07-13T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-13",
    "trace_id": "trace-stage5-013"
  },
  "scenario": "retention_lifecycle_03",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 14. `gmail_observability_014`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "persistence",
  "case_id": "gmail_observability_014",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "gmail_message_id": "gmail_msg_fixture_014",
      "processing_status": "retention_lifecycle_04",
      "trace_id": "trace-stage5-014"
    },
    "retention_action": "expire_redacted_audit",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-14",
    "attachment_content": "synthetic-attachment-bytes-14",
    "authorization_header": "Bearer synthetic-14",
    "bounded_failure_type": "retention_lifecycle_04",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-14@example.com",
    "complete_message_body": "synthetic private body 14",
    "gmail_message_id": "gmail_msg_fixture_014",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-14",
    "processing_status": "retention_lifecycle_04",
    "received_timestamp": "2026-07-14T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-14",
    "trace_id": "trace-stage5-014"
  },
  "scenario": "retention_lifecycle_04",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 15. `gmail_observability_015`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "persistence",
  "case_id": "gmail_observability_015",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "gmail_message_id": "gmail_msg_fixture_015",
      "processing_status": "retention_lifecycle_05",
      "trace_id": "trace-stage5-015"
    },
    "retention_action": "drop_raw_body",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-15",
    "attachment_content": "synthetic-attachment-bytes-15",
    "authorization_header": "Bearer synthetic-15",
    "bounded_failure_type": "retention_lifecycle_05",
    "classification_result": "prompt_injection",
    "complete_headers": "From: synthetic-15@example.com",
    "complete_message_body": "synthetic private body 15",
    "gmail_message_id": "gmail_msg_fixture_015",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-15",
    "processing_status": "retention_lifecycle_05",
    "received_timestamp": "2026-07-15T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-15",
    "trace_id": "trace-stage5-015"
  },
  "scenario": "retention_lifecycle_05",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 16. `gmail_observability_016`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "persistence",
  "case_id": "gmail_observability_016",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "gmail_message_id": "gmail_msg_fixture_016",
      "processing_status": "retention_lifecycle_06",
      "trace_id": "trace-stage5-016"
    },
    "retention_action": "expire_sanitized_context",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-16",
    "attachment_content": "synthetic-attachment-bytes-16",
    "authorization_header": "Bearer synthetic-16",
    "bounded_failure_type": "retention_lifecycle_06",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-16@example.com",
    "complete_message_body": "synthetic private body 16",
    "gmail_message_id": "gmail_msg_fixture_016",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-16",
    "processing_status": "retention_lifecycle_06",
    "received_timestamp": "2026-07-16T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-16",
    "trace_id": "trace-stage5-016"
  },
  "scenario": "retention_lifecycle_06",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 17. `gmail_observability_017`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "persistence",
  "case_id": "gmail_observability_017",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "gmail_message_id": "gmail_msg_fixture_017",
      "processing_status": "retention_lifecycle_07",
      "trace_id": "trace-stage5-017"
    },
    "retention_action": "expire_business_result",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-17",
    "attachment_content": "synthetic-attachment-bytes-17",
    "authorization_header": "Bearer synthetic-17",
    "bounded_failure_type": "retention_lifecycle_07",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-17@example.com",
    "complete_message_body": "synthetic private body 17",
    "gmail_message_id": "gmail_msg_fixture_017",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-17",
    "processing_status": "retention_lifecycle_07",
    "received_timestamp": "2026-07-17T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-17",
    "trace_id": "trace-stage5-017"
  },
  "scenario": "retention_lifecycle_07",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 18. `gmail_observability_018`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "persistence",
  "case_id": "gmail_observability_018",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "gmail_message_id": "gmail_msg_fixture_018",
      "processing_status": "retention_lifecycle_08",
      "trace_id": "trace-stage5-018"
    },
    "retention_action": "expire_redacted_audit",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-18",
    "attachment_content": "synthetic-attachment-bytes-18",
    "authorization_header": "Bearer synthetic-18",
    "bounded_failure_type": "retention_lifecycle_08",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-18@example.com",
    "complete_message_body": "synthetic private body 18",
    "gmail_message_id": "gmail_msg_fixture_018",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-18",
    "processing_status": "retention_lifecycle_08",
    "received_timestamp": "2026-07-18T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-18",
    "trace_id": "trace-stage5-018"
  },
  "scenario": "retention_lifecycle_08",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 19. `gmail_observability_019`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "persistence",
  "case_id": "gmail_observability_019",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "gmail_message_id": "gmail_msg_fixture_019",
      "processing_status": "retention_lifecycle_09",
      "trace_id": "trace-stage5-019"
    },
    "retention_action": "drop_raw_body",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-19",
    "attachment_content": "synthetic-attachment-bytes-19",
    "authorization_header": "Bearer synthetic-19",
    "bounded_failure_type": "retention_lifecycle_09",
    "classification_result": "action_required",
    "complete_headers": "From: synthetic-19@example.com",
    "complete_message_body": "synthetic private body 19",
    "gmail_message_id": "gmail_msg_fixture_019",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-19",
    "processing_status": "retention_lifecycle_09",
    "received_timestamp": "2026-07-19T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-19",
    "trace_id": "trace-stage5-019"
  },
  "scenario": "retention_lifecycle_09",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_

## 20. `gmail_observability_020`

Current review state: `draft`

- Control type: `observability:boundary-gold`
- Source: `observability/boundary-gold.jsonl`

Complete control candidate and Gold:

```json
{
  "boundary_kind": "persistence",
  "case_id": "gmail_observability_020",
  "dataset_version": "inbox2action-vnext-candidate-1",
  "expected": {
    "allowed_fields": [
      "trace_id",
      "gmail_message_id",
      "processing_status",
      "classification_result",
      "received_timestamp",
      "bounded_failure_type"
    ],
    "business_result_retention_days": 90,
    "forbidden_fields": [
      "complete_message_body",
      "access_token",
      "refresh_token",
      "authorization_header",
      "oauth_client_secret",
      "complete_headers",
      "attachment_content",
      "hidden_reasoning"
    ],
    "raw_body_persisted": false,
    "raw_body_retention_days": 0,
    "redacted_audit_retention_days": 90,
    "redacted_record": {
      "gmail_message_id": "gmail_msg_fixture_020",
      "processing_status": "retention_lifecycle_10",
      "trace_id": "trace-stage5-020"
    },
    "retention_action": "expire_sanitized_context",
    "sanitized_context_retention_days": 7
  },
  "input_record": {
    "access_token": "synthetic-access-token-20",
    "attachment_content": "synthetic-attachment-bytes-20",
    "authorization_header": "Bearer synthetic-20",
    "bounded_failure_type": "retention_lifecycle_10",
    "classification_result": "prompt_injection",
    "complete_headers": "From: synthetic-20@example.com",
    "complete_message_body": "synthetic private body 20",
    "gmail_message_id": "gmail_msg_fixture_020",
    "hidden_reasoning": "synthetic-hidden-reasoning-must-not-persist",
    "oauth_client_secret": "synthetic-client-secret-20",
    "processing_status": "retention_lifecycle_10",
    "received_timestamp": "2026-07-20T09:00:00+08:00",
    "refresh_token": "synthetic-refresh-token-20",
    "trace_id": "trace-stage5-020"
  },
  "scenario": "retention_lifecycle_10",
  "schema_version": "2.0",
  "synthetic_only": true
}
```

Reviewer decision: `PENDING`

Reviewer notes: _fill during human review_
