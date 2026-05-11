# US-15: Multi-Organisation Participant Registration

**Phase:** 3 — Marketplace Generalisation
**Reference:** [design-doc.md §13](../design-doc.md#13-multi-organisation-marketplace-model)

## Story
As an **organisation**, I want to register and manage my own agents independently of other organisations so that multiple companies can co-participate in a single session without coupling.

## Acceptance Criteria
- AC1: An `organisation_id` is created on first registration from a unique domain (e.g. `company-b.com`) and associated with subsequent registrations from that domain.
- AC2: Multiple agents per organisation are supported, each with its own `participant_id`.
- AC3: A single session can host participants from `N ≥ 3` organisations simultaneously, each addressed at its own A2A endpoint.
- AC4: An organisation can list its own registered agents via `GET /organisations/{org_id}/agents`.
- AC5: Cross-organisation visibility is limited to `participant_id`, `name`, `role` — internal endpoint URLs of other orgs' agents are not exposed in `session_ctx.participants`.
- AC6: Session creation may include agents from any combination of organisations.

## Out of Scope
- Billing / commercial agreements between organisations.
- Per-organisation rate limits, quotas, or tier management.
- Organisation-level admin UI / consoles.
- Inter-org authentication / federated identity (each agent still uses its own declared auth).
- Data residency or per-org storage isolation guarantees.
