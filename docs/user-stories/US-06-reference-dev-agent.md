# US-06: Reference Dev Agent

**Phase:** 1 — A2A Baseline
**Reference:** [design-doc.md §4](../design-doc.md#4-participant-contract), [§9](../design-doc.md#9-assignment-strategy)

## Story
As a **platform demonstrator**, I want a reference Developer agent that votes and volunteers for work so that I can exercise the assignment decision tree in an end-to-end demo.

## Acceptance Criteria
- AC1: Agent Card declares `role: DEVELOPER` and capabilities `can_vote: true`, `can_volunteer: true`.
- AC2: Handles `session_invite`, `session_ready`, `vote`, `assign_opportunity`, `acknowledge_assignment`, `confirm`, `session_aborted`.
- AC3: `vote` returns a dot-vote ballot derived only from `session_ctx.backlog_items`.
- AC4: `assign_opportunity` responds within the 5000ms timeout with `{ volunteer: true | false }` based on a configurable acceptance rule (e.g. accept up to N items per session).
- AC5: Agent tracks its accepted assignments by reading `session_ctx.assignments` on each call — no internal counter persisted across calls.
- AC6: `confirm` returns `{ confirmed: true }` unless the agent has zero assignments.
- AC7: Agent is stateless — restarting the agent process mid-session does not corrupt session outcomes (the next task call carries full `session_ctx`).

## Out of Scope
- LLM-backed reasoning about which items to volunteer for (deterministic rule only).
- Estimation tasks.
- Code generation or downstream task execution.
- Backlog item creation or editing.
- Multi-role agents (developer-only in this reference).
