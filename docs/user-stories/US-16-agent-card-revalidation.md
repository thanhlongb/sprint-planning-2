# US-16: Agent Card Discovery & Revalidation

**Phase:** 3 — Marketplace Generalisation
**Reference:** [design-doc.md §3.2](../design-doc.md#32-agent-card), [§5](../design-doc.md#5-agent-onboarding)

## Story
As the **platform**, I want to revalidate an agent's Agent Card on each session join so that stale capability declarations do not break a session.

## Acceptance Criteria
- AC1: When a registered agent receives a `session_invite`, the platform re-fetches `{agent_url}/.well-known/agent.json`.
- AC2: If the role or required capabilities have changed since registration, the platform compares the new card against the session's requirements.
- AC3: If the agent still satisfies the contract for its declared role in the session, it is allowed to join; the registry record's capabilities are updated.
- AC4: If the agent no longer satisfies the contract, the session treats the agent as a join failure and falls into the standard timeout / abort logic per [US-03](US-03-session-manager.md).
- AC5: Agent Card fetch failures (HTTP 5xx, timeout, malformed JSON) are retried up to 3 times before treating the agent as unavailable.
- AC6: Revalidation results are logged in the audit log.

## Out of Scope
- Periodic background revalidation outside of session joins.
- Notifying organisations of capability drift.
- Migrating an in-flight session if an agent's card changes mid-session.
- Card schema versioning / negotiation.
