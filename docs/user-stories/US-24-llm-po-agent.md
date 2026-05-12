# US-24: LLM-Backed PO Agent (Dynamic)

**Phase:** 3 — Marketplace Generalisation
**Reference:** [design-doc.md §4](../design-doc.md#4-participant-contract)

## Story
As a **platform demonstrator or researcher**, I want an LLM-backed Product Owner agent that dynamically generates a backlog and provides reasoning for its decisions, so that I can validate complex, non-deterministic planning flows and observe reasoning transparency.

## Acceptance Criteria
- AC1: The agent uses an LLM (e.g., GPT-4, Claude, Gemini) to generate a realistic set of backlog items dynamically based on a provided high-level `sprint_goal`.
- AC2: The agent streams its reasoning as "thoughts" back to the platform during long-running tasks (e.g., `present_backlog`, `vote`) to support the UI transparency requirements in US-23.
- AC3: The agent evaluates the `session_ctx` to cast votes intelligently, prioritising tasks that best align with the sprint goal rather than using a hardcoded deterministic distribution.
- AC4: The agent remains stateless between tasks, relying on injecting the full `session_ctx` into the LLM prompt context for each decision to maintain A2A contract compliance.
- AC5: The agent correctly formats its A2A responses, parsing the LLM's output to strictly adhere to the required JSON schemas for backlog items and ballots.

## Out of Scope
- Direct integration with real Jira/GitHub instances (this remains a generic LLM agent for platform validation).
- Complex multi-agent negotiation via private channels outside the established A2A protocol.
