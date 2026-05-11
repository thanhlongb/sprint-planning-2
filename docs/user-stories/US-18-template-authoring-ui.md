# US-18: Template Authoring UI

**Phase:** 3 — Marketplace Generalisation
**Reference:** [design-doc.md §7](../design-doc.md#7-process-template-engine)

## Story
As a **process designer**, I want a UI to build and edit Process Templates so that I don't have to hand-write YAML to customise planning flows.

## Acceptance Criteria
- AC1: A React-based UI lists existing templates and supports `Create`, `Edit`, `Clone`, `Delete`.
- AC2: A guided form lets the user add phases, configure `required_roles`, pick `turn_order` and `transition` modes, and add actions from a dropdown.
- AC3: Action parameter inputs are typed (e.g. numeric quorum slider 0–1, role-list multiselect).
- AC4: The UI validates the template against the same schema used by the YAML loader ([US-09](US-09-yaml-process-templates.md)) before saving.
- AC5: Saving a template persists it to PostgreSQL and makes it available for immediate use in `POST /sessions`.
- AC6: The UI displays a read-only YAML preview of the in-progress template for advanced users.
- AC7: A "Test" button runs the template against a built-in dry-run simulator and reports any structural issues.

## Out of Scope
- Real-time collaborative editing of templates.
- Version history / diff view between template revisions.
- Drag-and-drop graphical phase flow editor (form-based only).
- Template marketplace / sharing across organisations.
- Custom action handler authoring (action types remain platform-defined).
