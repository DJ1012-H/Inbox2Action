# Stage 3 Reference Analysis

## Purpose and boundary

This document is the first Stage 3 design checkpoint. It records the
architecture concepts that the implementation must preserve before any
durable state or external integration is introduced.

The committed baseline is `main` at `47c63dc`, the accepted Stage 2 candidate.
The current worktree layers the Stage 3 and Stage 4 implementation over that
baseline; those changes are not yet committed or pushed.

The reference implementation, if inspected later, is reference material only.
Its classes or files must not be copied mechanically. Inbox2Action owns its
contracts, safety policy, and persistence behavior.

## Concepts to retain

| Concept | Inbox2Action meaning | Required invariant |
| --- | --- | --- |
| State | The bounded, serializable workflow state for one email thread | No API secret, OAuth token, raw authorization header, or hidden model reasoning |
| Node | A small workflow transition with explicit input/output fields | A node cannot silently perform a write or bypass the policy boundary |
| Edge | A typed route chosen from validated state | Unknown, malformed, or incomplete routing fails closed |
| Tool | A named capability with a strict argument schema | Only registered tools can be selected; authorization is checked again before execution |
| Interrupt | A durable human-approval boundary | Every external write pauses before execution and binds approval to the exact payload |
| Store | Durable checkpoint and separately scoped user preferences | Checkpoint recovery is deterministic and preference updates cannot alter policy |

## Ownership model

The workflow owns orchestration and recovery. The agent owns multi-turn
reasoning over the sanitized email and observations. The policy layer owns
authorization, parameter completeness, dependency order, and approval
requirements. Tool adapters own only their narrowly scoped provider call.

No component may infer authorization from model text. The only source of
write authorization is a valid reviewed action plan plus a matching,
unconsumed human approval.

## Reference patterns deliberately not adopted

- A one-shot JSON classifier is not the product agent.
- A second autonomous agent is not introduced for triage; TriageRouter is a
  workflow node.
- A terminal y/n prompt is not durable human-in-the-loop approval.
- An in-memory checkpoint is not sufficient for restart recovery.
- A generic HTTP, shell, SQL, filesystem, or code-execution tool is never
  added as a convenience escape hatch.

## Stage 3 decision and current result

The implemented local workflow accepts only normalized input, consumes the
validated Stage 2 planning contracts, persists one LangGraph workflow state,
uses real approval interrupts, and executes approved fixture writes in
dependency order behind one authorization boundary. Stage 4 adds PostgreSQL
checkpoint and side-effect claim persistence. Real Gmail, Calendar, ClickUp,
and other provider credentials or writes remain out of scope.
