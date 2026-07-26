# Inbox2Action

Inbox2Action is being developed through staged, safety-gated validation.

## Current status

Stage 2 has not started implementation. The current baseline contains only
the stage-one learning evidence and project scaffolding. No real API key,
mailbox data, external service integration, or business agent is included.

## Scope boundary

The next approved implementation stage is limited to validating
`deepseek-v4-flash` through the native OpenAI SDK, with deterministic fakes for
unit tests. LangGraph, Gmail, Calendar, ClickUp, PostgreSQL, external writes,
and production agent workflows are out of scope.

## Local setup

Copy `.env.example` to `.env` only when a human explicitly enables an
integration probe. The default configuration keeps the model disabled.
