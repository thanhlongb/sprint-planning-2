# US-03 — Technical Decisions

**Story:** [US-03 Session Manager](../user-stories/US-03-session-manager.md)
**Status:** Implemented (Phase 1)

---

## 1. Route: `/sessions/{id}/join`, not `/session/{id}/join`

The US spec uses the singular `/session/{id}/join`. We keep the plural `/sessions` prefix established by `main.py` (already includes the router at `/sessions`). Consistent pluralisation avoids an irregular URL that would confuse clients. The join endpoint therefore lives at `POST /sessions/{session_id}/join`.

## 2. Timeout scheduling: per-session `asyncio.Task`, not a poller

A background poller that queries Postgres every N seconds would add load and introduce up-to-N-second drift. Instead, one `asyncio.create_task` is spawned per PENDING session and sleeps precisely until `timeout_at`. This is exact, has zero polling cost, and stays inside the existing async process model.

**Drawback:** Tasks are in-process and lost on restart.

**Mitigation (AC8):** `restore_pending_timeouts()` is called at startup. It reads all PENDING sessions from Postgres and re-schedules their timeout tasks. If the platform restarted *after* a `timeout_at` has already passed, the sleep is negative → the task fires immediately on the next event-loop tick.

## 3. Agent resolution in `participants` list

The US allows agents to be declared by either `agent_url` or `participant_id`. Both cases resolve to a registered `Participant` row at session-creation time:

- **`participant_id`**: direct lookup by primary key.
- **`agent_url`**: we look for a registered participant whose `endpoint` column starts with the given base URL. This mirrors how registration works (the platform derives the endpoint from the Agent Card the first time).

An unregistered agent yields a `404 agent_not_registered` error at `POST /sessions` creation time rather than silently failing at invite time. Fail fast is better than a session that can never reach ACTIVE.

## 4. `session_invite` is fire-and-forget

After `POST /sessions` commits, invites are sent in `asyncio.create_task(send_invites_background(...))`. The HTTP response is returned immediately. This matches the design doc's sequence diagram (the platform returns `join_url` before the invite flow completes).

If an invite fails (network error, agent down), the agent simply never joins and the timeout logic handles the absentee. No retry is attempted — it is out of scope for Phase 1.

## 5. Human join matched by (name, role) pair

A human join (`POST /sessions/{id}/join` with `{ name, role }`) must match a declared slot exactly. The slot is identified by `slot_type=HUMAN AND name=body.name AND role=body.role AND status=declared`. If more than one slot has the same name+role, the first undeclared one is consumed.

**Why not match by role alone?** Sessions can have multiple humans in the same role (two DEVELOPERs). Matching by role only would be ambiguous. Matching by name+role is the least-surprise option while staying within Phase 1 scope (no auth required).

A fresh UUID is assigned as `participant_id` for humans at join time (AC4). This ID is scoped to the session — it is not backed by a `Participant` row in the registry.

## 6. Hardcoded first-phase `required_roles` per template

AC6 requires the timeout checker to compare absentee roles against the **first phase's** `required_roles`. The `sprint_planning_v1` template first phase is `backlog_presentation`, which requires `PRODUCT_OWNER` (design doc §7.1).

This is encoded as a static dict in `session_service.py`:

```python
_FIRST_PHASE_REQUIRED_ROLES: dict[str, set[str]] = {
    "sprint_planning_v1": {"PRODUCT_OWNER"},
}
```

Adding a new template means adding one entry here. Full template-driven lookup (US-09) replaces this in Phase 2.

## 7. State-machine guard (AC7)

All status mutations go through `_transition()`, which validates against an explicit allow-list:

```
PENDING  → ACTIVE | ABORTED
ACTIVE   → COMPLETED
COMPLETED → (none)
ABORTED  → (none)
```

Any call that would cross this boundary raises `ValueError` at the service layer, producing a 500 rather than silently corrupting state. No backward transition is possible.

## 8. `timeout_at` stored with UTC offset, restored with explicit tzinfo

SQLAlchemy stores `datetime` in Postgres as `TIMESTAMP WITHOUT TIME ZONE`. On retrieval the value is timezone-naive. `restore_pending_timeouts()` attaches `timezone.utc` before passing it to `asyncio.sleep`, so the comparison is always in UTC even if the server's local timezone differs.

## 9. Status casing: uppercase `PENDING`, `ACTIVE`, `ABORTED`

The US spec and design doc both use uppercase state names (`PENDING`, `ACTIVE`, `ABORTED`, `COMPLETED`). The old stub used lowercase `pending`. We switch to uppercase throughout for consistency with the spec. Client code that relied on the old stub must be updated.

## 10. Verification

```bash
# Create a session with a pre-registered agent + one human
curl -X POST http://localhost:8000/sessions \
  -H 'content-type: application/json' \
  -d '{
    "template": "sprint_planning_v1",
    "sprint_goal": "Ship OAuth + profile",
    "participants": [
      {"participant_id": "<po-agent-id>"},
      {"type": "HUMAN", "name": "Alice", "role": "DEVELOPER"}
    ]
  }'
# → {"session_id":"...","join_url":"http://localhost:8000/sessions/.../join",
#    "timeout_at":"...","status":"PENDING",...}

# Agent joins (uses its participant_id)
curl -X POST http://localhost:8000/sessions/<id>/join \
  -H 'content-type: application/json' \
  -d '{"participant_id": "<po-agent-id>"}'

# Human joins
curl -X POST http://localhost:8000/sessions/<id>/join \
  -H 'content-type: application/json' \
  -d '{"name": "Alice", "role": "DEVELOPER"}'
# When all joined → status: ACTIVE, session_ready sent to agents

# Inspect session
curl http://localhost:8000/sessions/<id>
```
