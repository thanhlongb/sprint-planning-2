# US-37: Template Schema Updates for v2 Actions

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md), existing `template_schema.py`

## Story
As a **platform**, I want the template schema to accept the new v2 action types and discussion configuration so that `sprint_planning_v2.yaml` passes validation.

## Acceptance Criteria
- [ ] AC1: `GENERATE_RECOMMENDATION` added to allowed action types in `template_schema.py`.
- [ ] AC2: `GENERATE_ASSIGNMENT` added to allowed action types.
- [ ] AC3: `OPEN_DISCUSSION` added to allowed action types.
- [ ] AC4: `OPEN_DISCUSSION` action schema extended with `context` field (enum: `recommendation | assignment`) and `allowed_actions` field (list of strings).
- [ ] AC5: `CONFIRM` action schema extended with optional `acceptor` field (role string, e.g. `PRODUCT_OWNER`). When absent, defaults to all-roles quorum (v1 behavior).
- [ ] AC6: `sprint_planning_v2.yaml` validates without errors against the updated schema.
- [ ] AC7: `sprint_planning_v1.yaml` continues to validate without changes.

## Out of Scope
- Custom action type plugins (all types are built-in).
- Runtime schema hot-reload.
- Per-action custom validation beyond the schema.
