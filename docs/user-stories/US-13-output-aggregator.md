# US-13: Output Aggregator & Webhook Delivery

**Phase:** 2 — Template Engine
**Reference:** [design-doc.md §12.1 Output Aggregator](../design-doc.md#121-component-breakdown)

## Story
As an **operator**, I want session outputs delivered to external systems via webhook so that downstream tools (Jira, GitHub, dashboards) can react to a completed planning session.

## Acceptance Criteria
- AC1: A session can declare one or more `output_webhooks` at creation time.
- AC2: On `COMPLETED`, the Output Aggregator compiles the sprint backlog, sprint goal summary, and capacity plan per [§7.1 outputs](../design-doc.md#71-template-schema).
- AC3: Each declared webhook receives a `POST` with the compiled output and an `X-Session-Id` header.
- AC4: Webhook delivery is retried up to 3 times with exponential backoff (1s, 5s, 30s).
- AC5: Delivery results (success / failed after retries) are logged in the audit log ([US-14](US-14-session-audit-log.md)).
- AC6: Webhook failures do not change the session's `COMPLETED` status — A2A delivery to participants ([US-08](US-08-sprint-backlog-output.md)) is the authoritative path.
- AC7: Webhook payloads include a signature header for the recipient to verify authenticity (HMAC over body with a shared secret).

## Out of Scope
- OAuth or per-recipient credential management — shared-secret HMAC only.
- Direct first-party integrations with Jira / GitHub APIs.
- Async result streaming during the session (only end-of-session delivery).
- A pull-based `GET /sessions/{id}/output` endpoint (may be added later).
