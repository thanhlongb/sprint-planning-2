# US-05: Reference PO Agent

**Phase:** 1 — A2A Baseline
**Reference:** [design-doc.md §4](../design-doc.md#4-participant-contract)

## Story
As a **platform demonstrator**, I want a reference Product Owner agent backed by a static backlog so that I can validate the end-to-end planning flow without integrating a real Jira instance.

## Acceptance Criteria
- [x] AC1: The agent hosts a compliant A2A HTTP server with `/.well-known/agent.json` published.
- [x] AC2: Agent Card declares `role: PRODUCT_OWNER` and `capabilities.can_provide_backlog: true`, `can_vote: true`.
- [x] AC3: Handles `session_invite`, `session_ready`, `present_backlog`, `vote`, `confirm`, `acknowledge_assignment`, `session_aborted`.
- [x] AC4: `present_backlog` returns a static set of ≥ 5 backlog items conforming to the standardised Backlog Item schema (no `metadata` field leaked).
- [x] AC5: `vote` casts dot votes deterministically (e.g. distributing across items) using only fields in `session_ctx`.
- [x] AC6: `confirm` returns `{ confirmed: true }` when `session_ctx.selected_items` is non-empty.
- [x] AC7: Agent rejects task calls whose declared auth scheme does not match its Agent Card.
- [x] AC8: Agent does not persist session state between task calls — it relies solely on `session_ctx`.

## Out of Scope
- Real Jira / GitHub / TestRail integration.
- LLM-driven backlog generation (static fixture only).
- Multi-session concurrency stress testing.
- Volunteering for items (PO is not a developer role).
- Backlog refinement / item editing during the session.
