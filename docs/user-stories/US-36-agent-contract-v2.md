# US-36: Agent Contract Changes for v2

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md)

## Story
As a **platform**, I want agents to support the new v2 task types so that the discussion-driven workflow can communicate with all participants.

## Acceptance Criteria
- [ ] AC1: **PO agent** handles `accept_plan` task — receives final sprint backlog, responds `{accepted: true}` if backlog non-empty. Deterministic (same logic as current `confirm`).
- [ ] AC2: **Dev agent** handles `recommendation_update` task — acknowledges receipt. No decision required (informational only).
- [ ] AC3: **Dev agent** handles `assignment_proposal` task — receives algorithmic assignment map. Responds with structured decisions: `{volunteers: [...], objects: [...], reassignments: [...]}`.
- [ ] AC4: **Dev agent** Agent Card updated to declare `capacity` under `capabilities` (per US-34 AC2).
- [ ] AC5: All existing v1 task handlers (`vote`, `confirm`, `session_invite`, `session_ready`, `session_aborted`, `acknowledge_assignment`, `sprint_backlog`) remain functional.
- [ ] AC6: Unknown task types return HTTP 400 with descriptive error — no silent failures.

## Out of Scope
- LLM-driven volunteer/object decisions (deterministic reference agents only).
- Natural language negotiation responses.
- Agent-initiated phase transitions.
