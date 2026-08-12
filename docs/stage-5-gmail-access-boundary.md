# Stage 5 Gmail Access Boundary

## Status and scope

This document records mandatory engineering constraints for the future Stage 5
real Gmail ingestion work. It is a design input, not an implementation or an
acceptance result. Inbox2Action currently has no Gmail client, OAuth runtime,
Gmail ingestion pipeline, real-mailbox integration test, or accepted Gmail
capability.

These constraints become active when Stage 5 is explicitly approved to design
or implement real Gmail ingestion. They must not be used as a reason to add
provider classes, configuration, dependencies, credentials, or tests before
that stage begins.

On 2026-08-12, the user approved preparation of offline dataset contracts and
approved a personally owned private Gmail account for a later bounded pilot.
This approval does not authorize Gmail client/OAuth implementation or a mailbox
query in the current dataset task. The checked-in candidate assets must keep
`real_mailbox_accessed=false` and `real_provider_evidence=false`.

The governing principle is:

> OAuth grants capability; application policy grants actual access.

An OAuth scope describes the maximum capability Google may grant. It is not the
Inbox2Action data-access boundary. The application must independently decide
which messages may be discovered, fetched, processed, sent to a model, logged,
or persisted.

## Stage 5 OAuth boundary

The first Gmail integration may request only:

```text
https://www.googleapis.com/auth/gmail.readonly
```

It must not request `gmail.modify`, `gmail.compose`, `gmail.send`, or
`https://mail.google.com/`. Expanding the scope requires a separately stated
business need, design review, and explicit approval. A broader scope must never
be introduced as an implementation convenience.

`gmail.readonly` can expose a large portion of a private mailbox, so possession
of a valid token does not authorize an Inbox-wide scan.

## Application-level Gmail access boundary

The first access mode is `LABEL_ALLOWLIST`. By default, only messages carrying
the user-controlled `Inbox2Action` label may enter the ingestion pipeline:

```text
Gmail API
    -> application access policy
    -> label/query-constrained message listing
    -> permitted message IDs
    -> permitted message bodies
```

The application must constrain discovery in the Gmail API query itself. It
must not fetch the Inbox or mailbox history broadly and then apply the label
filter locally.

The reviewed first-pilot query is exactly:

```text
label:Inbox2Action newer_than:30d
```

The label is a human authorization signal:

- ordinary private mail is not processed;
- adding `Inbox2Action` authorizes that message for ingestion;
- removing or omitting the label means the message is outside the application's
  allowed ingestion set.

Possible later modes are `QUERY_ALLOWLIST`, `RULE_BASED`, and `AUTO_INGEST`.
Each expansion requires its own design and acceptance gate and must preserve
deny-by-default behavior.

Class names such as `GmailAccessPolicy`, `GmailClient`, or `GmailPort` are
illustrative only. Stage 5 must choose names and boundaries that fit the actual
project architecture instead of creating abstractions solely to mirror this
document.

## Fail-closed configuration

Real Gmail ingestion is allowed only when every required access-policy field is
present and valid. Missing or invalid access mode, allowed label, query rule,
or bounded-read setting must stop ingestion before a mailbox query occurs.

There is no fallback to reading the Inbox, all mail, or mailbox history. An
empty allowlist is a denial condition, not an instruction to remove filtering.

## Bounded discovery and retrieval

Stage 5 must place explicit limits on every synchronization operation,
including:

- allowed labels and optional allowed query fragments;
- maximum messages per synchronization;
- bounded time window;
- pagination and batch limits;
- deterministic handling of cursors and duplicate message IDs.

The first real private-Gmail pilot uses a personally owned private account and
processes only synthetic test messages explicitly labelled `Inbox2Action`.
Each synchronization has a hard cap of 20 messages, a 30-day window, a page
size of 10, and at most two pages. Configuration errors, missing cursors, or
pagination edge cases must not result in an unbounded historical scan.

## LLM data boundary

Mailbox access authorization and model data authorization are separate gates.
Passing the Gmail access boundary only allows a message to enter Inbox2Action;
it does not authorize sending the complete message to an LLM.

The future pipeline must apply a separately designed content/data policy,
prompt-injection defense, and data minimization before model invocation:

```text
Application Gmail access boundary
    -> approved email
    -> content/data policy
    -> prompt-injection defense
    -> data minimization
    -> LLM
```

For the first pilot:

- OAuth access tokens, refresh tokens, credentials, and Authorization headers
  never enter prompts or model-visible observations;
- Gmail internal metadata and headers are retained only when required for the
  task;
- attachment metadata may be mapped, but bytes and OCR output are never sent to
  a model;
- model-visible fields are limited to sanitized subject, sanitized body, and
  timezone;
- email addresses and phone numbers are replaced with role tokens; any action
  recipient is bound from trusted application context rather than model output;
- verification codes, credentials, tokens, raw headers, and Gmail internal
  metadata are excluded from model input.

The offline Gold contracts specify this policy, but no runtime content-policy
implementation exists today.

## Access control and prompt injection are independent

Two risks must remain conceptually and operationally separate:

1. Reading private mail that Inbox2Action was not authorized to ingest is an
   application access-policy failure.
2. An authorized message containing malicious instructions is an email content
   and prompt-injection failure.

Label filtering cannot replace prompt-injection defenses, and prompt-injection
detection cannot authorize access to an otherwise disallowed message. Both
gates must pass before an authorized message reaches agent reasoning.

## Logging boundary

Real Gmail code must not log complete provider message objects or rely on their
string representation. Logs may include bounded operational metadata such as:

- trace ID and Gmail message ID;
- processing status and classification result;
- received timestamp;
- bounded failure type.

Logs must not include complete message bodies, access or refresh tokens,
Authorization headers, OAuth client credentials, or complete attachments.

## Persistence boundary

Stage 5 must separately model raw provider content, bounded agent context,
extracted actions/tasks, and audit metadata. A Gmail message must not be stored
permanently in full merely because persistence is convenient.

The preferred default is to persist the minimum business result and source
identity, for example an extracted task description, deadline, and source
message ID. Any retention of raw bodies, full headers, or attachments requires
an explicit purpose, retention period, deletion behavior, and acceptance
review.

For the first pilot, raw message bodies have no database retention. Sanitized
agent context may be retained for at most seven days. Minimum business results
and redacted audit metadata may be retained for at most 90 days. Attachment
bytes, full headers, tokens, and credentials are not persisted.

## Expected future pipeline boundary

The intended responsibility flow is:

```text
Gmail API
    -> narrow provider client/port
    -> application Gmail access boundary
    -> provider-message mapping
    -> email security pipeline
       -> data minimization
       -> prompt-injection defense
    -> EmailActionAgent
    -> structured output validation
    -> business validation
    -> action proposal
```

This is a responsibility map, not a required class diagram. Stage 5 should add
only the abstractions needed by the existing Port/Adapter and LangGraph design.

## Entry conditions for implementation

Implementation may begin only when all of the following are true:

1. Stage 5 real Gmail ingestion is explicitly approved.
2. The initial access mode, label name, Gmail query, per-sync limit, time
   window, pagination behavior, and pilot account are reviewed.
3. The OAuth scope remains `gmail.readonly`, or any expansion has received a
   separate approved design.
4. Credential and token storage locations are defined outside Git and outside
   LangGraph state.
5. The content/data-minimization boundary is specified separately from the
   access policy.
6. Acceptance cases cover deny-by-default configuration, API-side filtering,
   bounded pagination, logging redaction, persistence minimization, and the
   independence of access control and prompt-injection handling.

Until these conditions are met, Gmail remains an unimplemented external
integration and no current-stage evidence may describe these constraints as
working security controls.
