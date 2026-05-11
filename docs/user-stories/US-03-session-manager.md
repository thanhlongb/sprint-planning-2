# US-03: Session Manager

**Phase:** 1 — A2A Baseline
**Reference:** [design-doc.md §6](../design-doc.md#6-session-lifecycle)

## Story
As a **session creator**, I want to create a planning session with a declared participant list and have the platform manage join, timeout, and state transitions, so that the session begins deterministically once everyone is present.

## Acceptance Criteria
- [x] AC1: `POST /sessions` accepts `template`, `sprint_goal`, and a unified `participants` array containing both agents (by `agent_url` or `participant_id`) and humans (by `type: HUMAN`, `name`, `role`).
- [x] AC2: Response contains `session_id`, `join_url`, `timeout_at` (15 minutes from creation), and `status: PENDING`.
- [x] AC3: For each agent participant, a `session_invite` task is sent to the agent's endpoint.
- [x] AC4: `POST /session/{session_id}/join` accepts both `{ participant_id }` (agents) and `{ name, role }` (humans), assigning a fresh `participant_id` to humans.
- [x] AC5: When all declared participants have joined, the session transitions `PENDING → ACTIVE` and a `session_ready` task is broadcast.
- [x] AC6: At `timeout_at`, the platform checks missing participants' roles against the **first phase**'s `required_roles`:
  - If covered → `ACTIVE` with a note listing absentees.
  - If a required role is missing → `ABORTED` and `session_aborted` is broadcast with reason.
- [x] AC7: Sessions cannot transition backward (e.g. `ACTIVE → PENDING`).
- [x] AC8: Session state is persisted in PostgreSQL and survives a platform restart.

## Out of Scope
- Joining a session that has already transitioned to `ACTIVE` (late join not supported in Phase 1).
- Replacing a participant mid-session.
- Configurable join-timeout duration (fixed at 15 minutes).
- Authentication of the session creator (assume trusted caller for baseline).
- Sending the `join_url` to humans via email/Slack — distribution is out-of-band.
