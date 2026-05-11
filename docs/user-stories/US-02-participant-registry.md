# US-02: Participant Registry & Agent Card Validation

**Phase:** 1 — A2A Baseline
**Reference:** [design-doc.md §5](../design-doc.md#5-agent-onboarding)

## Story
As an **agent developer**, I want to register my A2A Remote Agent with the platform once and receive a stable `participant_id`, so that I can join any future session without re-onboarding.

## Acceptance Criteria
- AC1: `POST /register` accepts an `agent_url` and fetches `{agent_url}/.well-known/agent.json`.
- AC2: Platform validates the Agent Card contains required fields: `name`, `role`, `capabilities`, `endpoint`, `auth`.
- AC3: Platform validates declared `capabilities` against the contract for the declared `role` (e.g. `PRODUCT_OWNER` must declare `can_provide_backlog: true`).
- AC4: On success, the platform returns `201 { participant_id, status: "REGISTERED" }`.
- AC5: On validation failure, the platform returns `4xx` with a machine-readable error reason (missing field, role/capability mismatch, unreachable URL).
- AC6: The registry persists `participant_id`, `endpoint`, `role`, and validated capabilities. The full Agent Card body is **not** stored.
- AC7: A registered `participant_id` can be reused indefinitely across sessions.

## Out of Scope
- Centralised public registry of agents (each company hosts its own card).
- Agent Card revalidation on session join (covered in [US-16](US-16-agent-card-revalidation.md)).
- Platform-issued API keys (auth scheme is dictated by the agent's card).
- Capability negotiation or role inference — the agent must declare both explicitly.
- Deregistration / agent rotation flows.
