# US-38: End-to-End Test for v2 Workflow

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md)

## Story
As a **developer**, I want an automated end-to-end test of the v2 workflow so that I can verify the new template, recommender, assignment algorithm, discussion handler, and convergence tracking work together correctly.

## Acceptance Criteria
- [ ] AC1: Register po-agent and dev-agent via `/register`.
- [ ] AC2: Create session via `POST /sessions` with `template: sprint_planning_v2` and `sprint_goal: "Ship OAuth + user profile"`.
- [ ] AC3: Verify recommendation phase: platform generates scored item list, `recommendation` comm message broadcast.
- [ ] AC4: Simulate a discussion round: send `add_item` and `remove_item` structured messages, verify platform broadcasts `recommendation_update`.
- [ ] AC5: Verify `recommendation_rounds` incremented after discussion activity.
- [ ] AC6: Advance to assignment: verify `GENERATE_ASSIGNMENT` produces an assignment map, `assignment_proposal` broadcast.
- [ ] AC7: Simulate assignment discussion: send `volunteer` message, verify `assignment_update` broadcast.
- [ ] AC8: Advance to confirmation: PO agent receives `accept_plan`, responds `{accepted: true}`.
- [ ] AC9: Session status transitions to COMPLETED.
- [ ] AC10: Final sprint backlog output includes `convergence_metrics`: `initial_recommendation`, `recommendation_rounds`, `assignment_rounds`, `retention_pct`.
- [ ] AC11: Test is repeatable and deterministic.

## Out of Scope
- Multi-round convergence with timeout-based exit (single round per phase in test).
- Human participant simulation.
- Performance / load testing.
