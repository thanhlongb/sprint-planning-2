# US-11: Multiple Pre-Built Templates

**Phase:** 2 — Template Engine
**Reference:** [design-doc.md §7.2](../design-doc.md#72-pre-built-templates)

## Story
As a **session creator**, I want to choose from 2–3 pre-built templates so that I can run different styles of planning sessions on the same platform.

## Acceptance Criteria
- AC1: At least three templates are shipped and loadable: `sprint_planning_v1`, `delegation_only`, and one of (`continuous_planning`, `negotiation_protocol`).
- AC2: `delegation_only` skips voting — PO presents, platform auto-assigns to agents.
- AC3: Each template completes end-to-end with the reference PO and Dev agents (plus a human if required by the template).
- AC4: `GET /templates` lists all loaded templates with `template_id`, `name`, `description`.
- AC5: Selecting an unknown `template` in `POST /sessions` returns a `4xx` listing valid template IDs.
- AC6: Each template's required roles are validated at session-creation time — the declared participant list must cover the union of required roles across all phases (or first-phase only if abort-on-timeout is acceptable).

## Out of Scope
- User-authored templates (covered in [US-18](US-18-template-authoring-ui.md)).
- A/B comparison runs of the same session across templates.
- Per-organisation default template.
- Localisation of template names/descriptions.
