# US-29: New Workflow Template (sprint_planning_v2)

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md), [May 25 meeting notes](../../../wiki/projects/sprint-planning-2.md#may-25-2026--ai-human-sprint-planning-and-capacity-optimization)

## Story
As a **platform operator**, I want a `sprint_planning_v2` YAML template defining the new 3-phase discussion-driven workflow so that sessions reflect the May 25 design decisions.

## Acceptance Criteria
- [ ] AC1: Template defines 3 phases: `recommendation`, `assignment`, `confirmation`.
- [ ] AC2: **Recommendation phase** has two actions: `GENERATE_RECOMMENDATION` (platform algorithmic) followed by `OPEN_DISCUSSION` (participants add/remove/modify). `turn_order: FACILITATOR_LED`, `transition: MANUAL`.
- [ ] AC3: Recommendation discussion allows actions: `add_item`, `remove_item`, `modify_item`. Timeout: 60s.
- [ ] AC4: **Assignment phase** has two actions: `GENERATE_ASSIGNMENT` (expertise-based) followed by `OPEN_DISCUSSION` (volunteer/object/reassign). `transition: MANUAL`.
- [ ] AC5: Assignment discussion allows actions: `volunteer`, `object`, `reassign`. Strategy: `VOLUNTEER_FIRST`, fallback: `AUTO_BALANCE`. Timeout: 60s.
- [ ] AC6: **Confirmation phase** has single `CONFIRM` action with `acceptor: PRODUCT_OWNER`. `turn_order: ROLE_FIRST`, `transition: AUTO`. No quorum requirement — PO sign-off only.
- [ ] AC7: Required roles: PRODUCT_OWNER (recommendation, confirmation), DEVELOPER (recommendation, assignment).
- [ ] AC8: Inputs declared: `product_backlog`, `sprint_goal`, `capacity_constraints`. Outputs: `sprint_backlog`, `sprint_goal`, `convergence_metrics`.
- [ ] AC9: Template loads successfully via the existing `template_loader.py` and validates against `template_schema.py`.
- [ ] AC10: `sprint_planning_v1.yaml` remains unchanged and functional alongside v2.

## Out of Scope
- Iterative refinement loop beyond timeout-based round management (Phase 3).
- Natural language discussion parsing (structured messages only).
- Human capacity model (hours + seniority) and AI compute budget.
