# US-02 — Technical Decisions

**Story:** [US-02 Participant Registry & Agent Card Validation](../user-stories/US-02-participant-registry.md)
**Status:** Implemented (Phase 1)

---

## 1. Route layout — `/register` vs `/participants`

The US specifies `POST /register` (not `POST /participants`). The previous
stub used `/participants` as a catch-all, which conflated registration (a
one-time onboarding action) with the participant list. We split them:

- `POST /register` — onboarding; creates or returns a `participant_id`.
- `GET /participants` — operational listing used by the orchestrator and debug tooling.

This keeps the two concerns separate and matches the design doc §5 description
of "agent onboarding" as a distinct flow from session participation.

## 2. Input: `agent_url`, not `agent_card_url`

AC1 says the request body carries `agent_url`. The platform derives the
Agent Card URL by appending `/.well-known/agent.json`, following the A2A
discovery convention. This mirrors how browsers discover service workers and
how the A2A spec describes agent discovery — the caller only needs to know
the agent's base URL, not the internal path of the card.

## 3. HTTP 422 for validation failures (AC5)

The US asks for `4xx` with a machine-readable reason. We use `422 Unprocessable
Entity` for all semantic validation failures (missing field, role/capability
mismatch, unreachable URL). `400` would also be acceptable, but 422 is the
HTTP-standard code for "syntactically valid but semantically wrong", which is
exactly what these cases are. Every 422 body carries a JSON `detail` object
with a `reason` discriminator field so clients can branch on error type:

```json
{ "reason": "role_capability_mismatch", "capability": "can_provide_backlog",
  "required_value": true, "declared_value": false, "role": "PRODUCT_OWNER" }
{ "reason": "missing_field",       "field": "auth" }
{ "reason": "unreachable_url",     "url": "...", "http_status": 503 }
{ "reason": "missing_capability",  "capability": "can_vote", "role": "DEVELOPER" }
{ "reason": "invalid_role",        "role": "WIZARD", "valid_roles": [...] }
{ "reason": "unsupported_auth_scheme", "scheme": "oauth2" }
```

## 4. Role/capability contract (AC3)

We encode the contract as three lookup tables in `registry.py` rather than
embedding rules in procedural code. This makes adding a new role or capability
a one-line change without touching the validation flow.

| Constraint | Applies to | Table |
|---|---|---|
| Must declare (any boolean) | All roles → `can_vote` | `_UNIVERSAL_CAPS` |
| Must declare as `true` | `PRODUCT_OWNER` → `can_provide_backlog` | `_ROLE_REQUIRED_TRUE` |
| Must declare (any boolean) | `DEVELOPER`, `ARCHITECT` → `can_volunteer` | `_ROLE_REQUIRED_DECLARED` |

`SCRUM_MASTER` only needs `can_vote`. No `can_volunteer` or `can_provide_backlog`
requirement is stated in the design doc §4.1 for that role.

`can_volunteer` for `DEVELOPER` and `ARCHITECT` need only be declared — they
may declare it `false` (meaning "I won't volunteer this sprint"). The constraint
is about contract compliance (declaring intent), not forcing volunteering.

## 5. What is stored vs. what is discarded (AC6)

Per the design doc §5: "The agent's participant_id, endpoint URL, role, and
validated capabilities are stored. The Agent Card is not stored."

Storing the full card would create a stale-data problem (the card is the
agent's source of truth; the platform's copy would diverge after any card
update). Storing only the extracted, validated subset keeps the registry lean
and forces re-validation on card changes (covered by US-16).

`auth` is deliberately **not** persisted either — the platform re-reads auth
requirements from the card at task-send time (US-01 client). Persisting it
would couple the platform to a snapshot that could go stale.

## 6. Idempotent re-registration (AC7)

AC7 states that a registered `participant_id` can be reused indefinitely.
This implies the ID must be stable — re-registering the same agent should not
produce a new ID.

We enforce stability via a `UNIQUE` constraint on `endpoint` and an
"upsert-lite" read-before-write: if a row with the same endpoint already
exists, we return the existing `participant_id` with `200`. New registrations
return `201`.

This satisfies the story's intent ("register once") without implementing full
upsert semantics. Deregistration and rotation remain out of scope (US-16+).

## 7. Auth scheme allowlist

Only `none` and `bearer` are accepted at registration. This mirrors the
schemes the A2A client (US-01) knows how to handle. An agent declaring an
unknown scheme would be accepted at registration but would fail silently at
task-send time, which is worse. Failing fast at registration with a clear
`unsupported_auth_scheme` error is better.

## 8. Verification

```bash
# Register PO agent (happy path → 201)
curl -X POST http://localhost:8000/register \
  -H 'content-type: application/json' \
  -d '{"agent_url": "http://po-agent:8001"}'
# → {"participant_id": "<uuid>", "status": "REGISTERED"}

# Re-register same agent (idempotent → 200, same ID)
curl -X POST http://localhost:8000/register \
  -H 'content-type: application/json' \
  -d '{"agent_url": "http://po-agent:8001"}'

# Missing required field → 422
curl -X POST http://localhost:8000/register \
  -H 'content-type: application/json' \
  -d '{"agent_url": "http://bad-agent:9999"}'
# → {"detail": {"reason": "unreachable_url", ...}}

# List all participants
curl http://localhost:8000/participants
```
