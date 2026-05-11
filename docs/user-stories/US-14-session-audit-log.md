# US-14: Session Audit Log

**Phase:** 2 — Template Engine
**Reference:** [design-doc.md §12.1 Message Bus / Event Router](../design-doc.md#121-component-breakdown)

## Story
As a **researcher / operator**, I want a complete audit log of every session so that I can reconstruct what happened for debugging, evaluation, and academic study.

## Acceptance Criteria
- AC1: Every inbound and outbound A2A task is logged with: `session_id`, `task_id`, `participant_id`, `task_type`, timestamp, payload, response status.
- AC2: Every phase transition is logged with `from_phase`, `to_phase`, trigger (`AUTO | TIMED | MANUAL`), and outcome.
- AC3: Every session state change (`PENDING → ACTIVE → COMPLETED | ABORTED`) is logged with reason.
- AC4: Vote-buffer release events are logged (release trigger, vote count).
- AC5: Logs are append-only and persisted in PostgreSQL.
- AC6: `GET /sessions/{session_id}/audit` returns the ordered log for that session (operator endpoint).
- AC7: Logs retain redaction markers for `backlog_items` description text if a session declares `redact_content: true` — supporting the zero-knowledge principle when sessions involve sensitive content.

## Out of Scope
- Real-time streaming of the audit log to external observability tools (logs are queryable only).
- Cross-session analytics dashboards.
- Long-term cold storage / log archival policy.
- User-facing audit visualisation.
- GDPR-style export / deletion endpoints.
