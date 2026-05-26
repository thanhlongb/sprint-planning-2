# US-35: Convergence Metrics Tracking

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md), May 25 meeting (evaluation pivot to convergence)

## Story
As a **researcher**, I want the platform to track convergence metrics during v2 sessions so that I can measure recommendation quality and planning efficiency without external instrumentation.

## Acceptance Criteria
- [ ] AC1: `initial_recommendation` captured as a snapshot of the platform's starting item list at the beginning of the recommendation discussion.
- [ ] AC2: `recommendation_rounds` incremented each time the recommendation discussion state changes (add/remove/modify applied + broadcast).
- [ ] AC3: `assignment_rounds` incremented each time the assignment discussion state changes (volunteer/object/reassign applied + broadcast).
- [ ] AC4: `retention_pct` calculated at confirmation as `len(final_items ∩ initial_recommendation) / len(initial_recommendation)`, stored as a float (0.0–1.0).
- [ ] AC5: All four fields persisted to `session.context` JSON column via `_commit_ctx()`.
- [ ] AC6: Fields are present in the final sprint backlog output alongside item and assignment data.
- [ ] AC7: Fields are nullable in the schema — v1 sessions do not populate them.

## Out of Scope
- Statistical analysis or visualization of convergence data.
- Real-time convergence dashboard.
- Per-participant round attribution (who drove the most changes).
