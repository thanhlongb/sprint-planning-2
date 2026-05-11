# US-08: Sprint Backlog Output

**Phase:** 1 — A2A Baseline
**Reference:** [design-doc.md §1](../design-doc.md#1-system-overview), [§7.1 outputs](../design-doc.md#71-template-schema)

## Story
As a **participant**, I want to receive the final sprint backlog when the session completes so that I can sync the results into my own system of record.

## Acceptance Criteria
- [x] AC1: On `COMPLETED`, the platform constructs a `sprint_backlog` object containing: `session_id`, `sprint_goal`, the list of selected items with their `assignee_id`, and a `capacity_plan` summary.
- [x] AC2: The `sprint_backlog` task is sent to every participant via their A2A endpoint (or the React UI proxy for humans).
- [x] AC3: Items in the output use the standardised Backlog Item schema — no internal source-system metadata is included.
- [x] AC4: Assignments include both `assignee_id` and the human-readable `assignee_name` so participants can render without an extra lookup.
- [x] AC5: A single canonical version of the sprint backlog is delivered — all participants receive byte-identical content.
- [x] AC6: Delivery failures (agent unreachable at completion) are logged but do not prevent the session from completing.

## Out of Scope
- Round-trip sync into Jira/GitHub/TestRail (each agent handles its own sync).
- Webhook delivery to external systems (covered in [US-13](US-13-output-aggregator.md)).
- Versioned / iterative sprint backlog revisions after completion.
- Export formats other than the A2A task payload (CSV, PDF, etc.).
