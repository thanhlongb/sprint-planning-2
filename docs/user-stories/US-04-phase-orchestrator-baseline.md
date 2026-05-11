# US-04: Phase Orchestrator (Hard-coded sprint_planning_v1)

**Phase:** 1 — A2A Baseline
**Reference:** [design-doc.md §8](../design-doc.md#8-phase-orchestration), [§9](../design-doc.md#9-assignment-strategy)

## Story
As the **platform**, I want to execute the four phases of `sprint_planning_v1` end-to-end so that an active session reliably produces a sprint backlog.

## Acceptance Criteria
- [x] AC1: Phase 1 — Backlog Presentation: `present_backlog` task is sent to the PRODUCT_OWNER; returned items are validated against the standardised Backlog Item schema and stored in `session_ctx.backlog_items`.
- [x] AC2: Phase 2 — Prioritisation: `vote` task is sent in parallel to all required roles; votes are tallied (dot voting); items are selected greedily by capacity and stored in `session_ctx.selected_items`.
- [x] AC3: Phase 3 — Assignment: For each selected item, the orchestrator runs the `VOLUNTEER_FIRST → AUTO_BALANCE` decision tree with a 5000ms timeout; the resolved `assignee_id` is broadcast via `acknowledge_assignment` with a `reason` of `VOLUNTEERED | CONFLICT_RESOLVED | AUTO_BALANCE`.
- [x] AC4: Phase 4 — Confirmation: `confirm` task is sent to all; session transitions to `COMPLETED` when quorum ≥ 0.75 is reached.
- [x] AC5: Every outbound task call includes the full `session_ctx` payload per [§11](../design-doc.md#11-session-context-schema); late-populated fields are nullable.
- [x] AC6: `phase_history` is appended with `phase_id`, `completed_at`, and a platform-generated `outcome` string at each transition.
- [x] AC7: Load for tie-breaking is computed from `session_ctx.assignments` only — never from external systems.
- [x] AC8: Phase transitions are atomic — partial state from a failed phase is not visible to the next.

## Out of Scope
- YAML-driven template execution (covered in [US-10](US-10-dynamic-phase-orchestrator.md)).
- Templates other than `sprint_planning_v1`.
- Estimation phase (story points pre-populated by PO).
- Re-running a failed phase.
- Configurable assignment timeout per session.
- Simultaneous-reveal vote buffering (Phase 2 deliverable — [US-12](US-12-simultaneous-reveal.md)).
