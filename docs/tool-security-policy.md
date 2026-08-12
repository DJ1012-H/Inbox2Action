# Stage 3 Tool Security Policy

## Trust boundaries

Email subjects, bodies, HTML, attachments, model output, tool arguments, and
provider observations are untrusted. System policy, reviewed case policy,
validated schemas, durable approval records, and idempotency records are
trusted only after independent validation.

Prompt text is not an authorization mechanism. The code path must enforce the
same rules even when the model is confused, injected, unavailable, or
maliciously instructed by email content.

## Tool classes

### Direct read tools

The initial read-only set is limited to:

- get_current_time;
- get_email_thread;
- read_user_preferences;
- check_calendar_availability.

Reads must be scoped to the current workflow and bounded in size. They cannot
return credentials, broad mailbox exports, hidden application state, or
arbitrary files.

### Approval-gated writes

The initial write proposals are:

- save_reply_draft;
- create_clickup_task;
- create_calendar_event.

All writes pause at ApprovalInterrupt. A model-generated request, a previous
approval, or a provider retry cannot bypass the current approval. Sending mail,
deleting mail/tasks/events, and changing provider permissions are not Stage 3
capabilities.

### Forbidden capabilities

The registry must reject arbitrary HTTP, shell, code execution, SQL,
filesystem traversal, secret retrieval, mailbox deletion, external mail
sending, and unregistered tools. Rejection happens before any handler or
provider adapter is reached.

## Required enforcement sequence

Before every tool execution:

1. resolve the tool name from the allowlist;
2. validate strict arguments and reject extra fields;
3. verify the reviewed action plan and action identity;
4. verify required parameters are resolved and non-ambiguous;
5. verify dependency predecessors are completed;
6. verify approval is required and present for writes;
7. recompute the normalized payload and compare its hash to the approved hash;
8. check the idempotency key;
9. invoke only the narrow registered handler;
10. persist a redacted audit event and bounded observation.

Any missing, conflicting, stale, or unmeasured condition blocks the action.

## Payload and audit rules

Approval binds to action_id, action_type, normalized parameters, and a payload
hash. Editing any approved field creates a new revision and requires fresh
approval. Provider responses are stored as bounded, redacted observations, not
raw HTTP payloads.

Audit events may contain identifiers, status, timing, error class, and hashes
needed for reconciliation. They must not contain API keys, authorization
headers, complete email bodies, complete provider payloads, or hidden
reasoning.

## Injection handling

The normalizer marks suspicious instructions, hidden content, credential
requests, and requests to ignore policy as untrusted content. The router or
agent may classify a case as blocked or ask the user, but it may not use the
email to expand tools or permissions. Refusal text and risk-warning quality
are separate evaluation metrics; Stage 2 Tool Boundary Safety is not evidence
that those end-to-end metrics have passed.

## Fail-closed conditions

Block and record a redacted reason for unknown tools, invalid arguments,
missing approval, stale approval, payload-hash mismatch, duplicate identity,
dependency violations, provider ambiguity, normalization failure, checkpoint
conflict, retry exhaustion, or any unmeasured required safety metric.
