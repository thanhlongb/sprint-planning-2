# US-33: Phase Orchestrator Wiring for v2

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md), existing `phase_orchestrator.py`

## Story
As the **platform**, I want the phase orchestrator to dispatch the new v2 actions so that sessions using `sprint_planning_v2` execute the discussion-driven workflow end-to-end.

## Acceptance Criteria
- [ ] AC1: `_handle_recommend()` added — calls `recommender.recommend()`, stores initial list, snapshots `initial_recommendation`, then enters discussion via `_handle_discussion()`.
- [ ] AC2: `_handle_generate_assignment()` added — calls the expertise-based assignment algorithm, broadcasts the proposal, then enters discussion.
- [ ] AC3: `_handle_discussion()` added — shared handler per US-32.
- [ ] AC4: Action dispatch in `_orchestrate()` wired for `GENERATE_RECOMMENDATION`, `GENERATE_ASSIGNMENT`, and `OPEN_DISCUSSION`.
- [ ] AC5: `_handle_confirm()` simplified when template is v2: polls only the PRODUCT_OWNER slot, accepts if PO confirms (no quorum).
- [ ] AC6: `_handle_vote()` and `_handle_select()` NOT called for v2 templates (retained for v1 compatibility).
- [ ] AC7: `run_orchestrator()` detects template version and routes to the correct action set.
- [ ] AC8: Session transitions PENDING → ACTIVE → COMPLETED correctly with v2.
- [ ] AC9: Existing v1 sessions continue to work unchanged.

## Out of Scope
- Hot-reloading template changes mid-session.
- Version negotiation between platform and agents.
- Multi-template session (one session = one template).
