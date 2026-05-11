# US-09: YAML-Based Process Templates

**Phase:** 2 — Template Engine
**Reference:** [design-doc.md §7](../design-doc.md#7-process-template-engine)

## Story
As a **process designer**, I want to define a planning process as a YAML Process Template so that the planning flow becomes configuration, not code.

## Acceptance Criteria
- AC1: A YAML schema is defined matching [§7.1](../design-doc.md#71-template-schema): `template_id`, `name`, `description`, `phases[]`, `inputs[]`, `outputs[]`.
- AC2: Each `phase` declares `phase_id`, `required_roles`, `actions[]`, `turn_order`, `duration_limit`, and `transition`.
- AC3: Templates are loaded from YAML files into PostgreSQL on platform start.
- AC4: Template validation rejects unknown `action.type`, unknown `turn_order` modes, and undeclared roles.
- AC5: The pre-existing `sprint_planning_v1` baseline behaviour is fully expressible as a YAML template with no orchestrator code changes.
- AC6: A loaded template can be referenced by `template` in `POST /sessions`.
- AC7: Schema and validation errors are reported with the YAML file path and line number where possible.

## Out of Scope
- Visual template authoring UI (covered in [US-18](US-18-template-authoring-ui.md)).
- Per-session template overrides (templates are immutable per session).
- Versioning / migration of stored templates.
- Cross-template inheritance or composition.
- Runtime template hot-reload.
