# US-25: LLM-Backed Dev Agent (Reasoning)

**Phase:** 3 — Marketplace Generalisation
**Reference:** [design-doc.md §4](../design-doc.md#4-participant-contract), [§9](../design-doc.md#9-assignment-strategy)

## Story
As a **platform demonstrator or researcher**, I want an LLM-backed Developer agent that reasons about its workload and capabilities before volunteering for tasks, so that I can observe realistic, dynamic assignment behaviours during planning.

## Acceptance Criteria
- AC1: The agent uses an LLM to evaluate the `backlog_items` in the `session_ctx` against a configurable "persona" (e.g., frontend specialist, backend specialist) to inform its voting ballot.
- AC2: When receiving an `assign_opportunity` task, the agent uses the LLM to evaluate its current assignments (tracked via `session_ctx.assignments`) and inferred task complexity to decide whether to volunteer.
- AC3: The agent streams its internal reasoning ("thoughts") during the `vote` and `assign_opportunity` tasks to support UI transparency (US-23).
- AC4: The agent correctly formats its A2A response to match the contract, ensuring the LLM's unstructured output is parsed into the required JSON schema (e.g., `{ volunteer: true | false }`).
- AC5: The agent handles platform timeouts gracefully, ensuring a default fallback response is returned if the LLM generation exceeds the permitted 5000ms window for assignments.

## Out of Scope
- Code generation or actual execution of the assigned tasks.
- Maintaining persistent memory/state across sessions or task calls (relies purely on `session_ctx`).
