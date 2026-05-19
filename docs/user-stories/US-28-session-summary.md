# US-28: Session Summary Storage & Review UI

**Phase:** 4 — Experience Polish
**Reference:** [design-doc.md §6](../design-doc.md#6-session-lifecycle), [US-03](./US-03-session-manager.md), [US-08](./US-08-sprint-backlog-output.md), [US-14](./US-14-session-audit-log.md), [US-20](./US-20-metrics-collection.md)

## Story
As a **session participant or researcher**, I want a structured summary automatically generated and stored when a session concludes, and viewable via a dedicated summary screen, so that I can review what was decided, how agents performed, and share outcomes without replaying the full audit log.

## Acceptance Criteria

### Backend — Summary Generation & Storage
- AC1: When a session transitions to `COMPLETED` (US-03 AC5/AC6), the platform generates a `SessionSummary` record and persists it in PostgreSQL, linked by `session_id`.
- AC2: The summary record includes:
  - `session_id`, `sprint_goal`, `template_used`, `started_at`, `ended_at`, `duration_seconds`
  - `participants` array: each entry carries `participant_id`, `name`, `role`, `type` (`HUMAN | AGENT`), and `message_count`
  - `backlog_output`: the final sprint backlog (US-08) as a JSON array of story objects (`title`, `story_points`, `assigned_to`, `priority`)
  - `phase_breakdown`: list of phases with `phase_name`, `duration_seconds`, `outcome` (`COMPLETED | TIMED_OUT | SKIPPED`)
  - `key_decisions`: up to 10 notable events extracted from the audit log (US-14) — e.g., votes, estimation consensus moments, human interventions
  - `metrics_snapshot`: a copy of the session-level metrics from US-20 (velocity points, consensus rate, participation ratio) snapshotted at conclusion time
- AC3: `GET /sessions/{session_id}/summary` returns the stored summary as JSON; returns `404` if the session has not yet concluded or summary generation failed.
- AC4: If summary generation fails (e.g., missing audit data), the platform retries up to 3 times with exponential backoff; on final failure it stores a partial summary with a `generation_status: PARTIAL` flag and logs the error.
- AC5: Summary records are immutable after creation — subsequent reads always return the same snapshot even if audit data is later amended.

### Frontend — Session Summary Screen
- AC6: Upon session completion, all connected participants are automatically navigated to (or shown a banner linking to) a `/sessions/{session_id}/summary` route.
- AC7: The Summary screen is divided into three sections:
  1. **Overview card** — sprint goal, date/time, total duration, participant count (humans vs. agents), and overall `generation_status` badge.
  2. **Sprint Backlog panel** — tabular list of backlog items with columns: Title, Story Points, Assigned Agent, Priority. A "Copy as Markdown" button exports the table to the clipboard.
  3. **Session Insights panel** — phase-by-phase timeline bar showing duration and outcome per phase; key decisions listed chronologically; metrics (velocity, consensus rate, participation ratio) displayed as stat cards.
- AC8: The Summary screen is accessible post-session at any time via `GET /sessions/{session_id}/summary`; it does not require the participant to have been in the original session (read-only, no auth in Phase 4).
- AC9: A "Download JSON" button on the Summary screen triggers a browser download of the raw summary payload.
- AC10: If `generation_status` is `PARTIAL`, the UI shows an inline warning banner: "Summary is incomplete — some data could not be retrieved."
- AC11: The Summary screen is responsive and readable on both desktop and tablet viewports (minimum 768 px width).

## Out of Scope
- LLM-generated narrative prose summaries (the summary is structured data, not a written paragraph).
- Email or Slack delivery of the summary (distribution is out-of-band).
- Editing or annotating the summary post-session.
- Cross-session comparison view (deferred to Phase 5+).
- Authentication or access control for the summary endpoint in Phase 4.
- Exporting to Jira, Linear, or other project management tools.
