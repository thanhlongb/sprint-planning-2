# US-04 — Technical Decisions

**Story:** [US-04 Phase Orchestrator (Baseline)](../user-stories/US-04-phase-orchestrator-baseline.md)  
**Status:** Implemented (Phase 1)

---

## 1. Orchestrator fires as an `asyncio.create_task` after ACTIVE transition

The orchestrator must not block the API response for `POST /sessions/{id}/join` or the timeout callback. Both activation paths in `session_service.py` (`maybe_activate` and `_evaluate_timeout`) commit the ACTIVE state to Postgres and then immediately schedule `run_orchestrator(session_id)` as a background asyncio task. This mirrors the pattern already used for `send_invites_background`.

**Risk:** If the process crashes mid-orchestration, the session stays `ACTIVE` with partial context. Re-running failed phases is out of scope (US spec). On restart, the timeout-restore path (`restore_pending_timeouts`) only restores PENDING sessions, so a crashed mid-orchestration session would be stuck. Acceptable for Phase 1 baseline.

---

## 2. Immutable snapshot dataclasses replace ORM objects

`_SessionSnap` and `_SlotSnap` are frozen dataclasses captured from ORM rows immediately after loading. Each phase function receives these snapshots and opens its own `SessionLocal` context only when it needs to write. This avoids the SQLAlchemy "detached instance" error that occurs when ORM objects are accessed outside their originating session.

---

## 3. Phase state committed only at phase boundaries (AC8)

The orchestration state (`backlog_items`, `selected_items`, `assignments`, `phase_history`) lives purely in local variables between phases. `_commit_ctx` is called exactly once per phase, after the phase has fully completed. If a phase raises an exception mid-way, none of its partial state reaches Postgres — the previous phase's committed state remains visible but the failed phase's state does not, satisfying AC8.

The sole exception: `assignments` in Phase 3 accumulates in-memory across items and is committed in a single write at the end of Phase 3. Individual mid-phase assignments are not persisted. This means Phase 4 will not see assignments until Phase 3 fully completes.

---

## 4. Phase 2 capacity: `sprint_capacity` from `session.context`, default = no limit

The design doc lists `capacity_constraints` as a session input (§7.1), but collecting per-participant capacity declarations is out of scope for US-04. Instead, if `sprint_capacity` (story points) is present in `session.context` at creation time, the greedy selection algorithm uses it as the cap. If absent, all ranked items are selected (no cutoff). Items with `story_points: null` count as 1 point for capacity arithmetic.

**To set a capacity:** include `"sprint_capacity": 40` in the session context when calling `POST /sessions` — this can be done by pre-populating `session.context` directly in tests or by extending `CreateSessionRequest` in a later US.

---

## 5. Vote tally: dot-voting with HIGH=3 / MEDIUM=2 / LOW=1 scoring

The design doc specifies DOT_VOTING (§7.1) but does not define the score mapping. We use a 3/2/1 mapping — the most common dot-voting convention. Items with no vote from a given participant receive 0. Ranking is by total score descending before greedy capacity selection.

---

## 6. Assignment timeout applies per-item, not per-phase

AC3 specifies a 5000 ms timeout. This is applied per item: the platform gathers `assign_opportunity` responses from all eligible slots using `asyncio.gather` with `duration_limit_seconds=5.0` passed to `A2AClient.send_task`. If a slot times out, it is treated as "no volunteer" (not an error). This means Phase 3 can take up to `5s × len(selected_items)` in the worst case.

---

## 7. Load tie-breaking uses `session_ctx.assignments` only (AC7)

`_pick_lowest_load` iterates over the current in-memory `assignments` dict (which maps `item_id → participant_id`) and counts how many items each candidate participant has been assigned within this session. No external workload queries are made. Random selection breaks ties among equally-loaded candidates.

---

## 8. Quorum denominator = reachable joined slots (no human proxy in Phase 1)

AC4 requires quorum ≥ 0.75. Quorum is computed as `confirmed / reachable` where `reachable` = joined slots that have an A2A endpoint. Human slots declared without an endpoint (because the React UI proxy is not yet implemented in Phase 1) are excluded from both numerator and denominator. This prevents the denominator from inflating with participants the platform cannot reach, and avoids a situation where quorum can never be reached.

**Implication:** A session with only agent participants confirms correctly. A mixed agent/human session counts only agent votes toward quorum in Phase 1. Full human participation is covered in the React UI proxy story.

---

## 9. Confirm response: dual-format support

Both agents previously returned `{"ack": True}` for `confirm`. The orchestrator's Phase 4 handler treats `artifact.get("confirmed", artifact.get("ack", False))` as the confirmation signal. The agents have been updated to return `{"confirmed": True}` explicitly, but the fallback to `ack` is retained so any third-party agents that have not yet updated their confirm handler still work correctly.

---

## 10. Circular import avoided via lazy import in session_service

`phase_orchestrator.py` imports `_transition` from `session_service.py`. If `session_service.py` imported `phase_orchestrator` at module level, a circular import would occur. The solution is a `_get_run_orchestrator()` helper in `session_service.py` that imports `phase_orchestrator.run_orchestrator` lazily (inside the function body). Python resolves this correctly because both modules are fully initialised before any function is called.

---

## 11. Verification

```bash
# Start the stack
cd src && docker compose up

# Register PO agent
curl -s -X POST http://localhost:8000/register \
  -H 'content-type: application/json' \
  -d '{"agent_url": "http://po:8001"}' | jq .

# Register Dev agent
curl -s -X POST http://localhost:8000/register \
  -H 'content-type: application/json' \
  -d '{"agent_url": "http://dev:8002"}' | jq .

# Create session with both agents
curl -s -X POST http://localhost:8000/sessions \
  -H 'content-type: application/json' \
  -d '{
    "template": "sprint_planning_v1",
    "sprint_goal": "Ship OAuth + user profile",
    "participants": [
      {"agent_url": "http://po:8001"},
      {"agent_url": "http://dev:8002"}
    ]
  }' | jq .

# Both agents receive session_invite and auto-join (they POST /sessions/{id}/join
# when they get session_ready -- or trigger join manually):
SESSION_ID=<session_id>
PO_ID=<po_participant_id>
DEV_ID=<dev_participant_id>

curl -s -X POST http://localhost:8000/sessions/$SESSION_ID/join \
  -H 'content-type: application/json' \
  -d "{\"participant_id\": \"$PO_ID\"}"

curl -s -X POST http://localhost:8000/sessions/$SESSION_ID/join \
  -H 'content-type: application/json' \
  -d "{\"participant_id\": \"$DEV_ID\"}"

# After the second join → ACTIVE → orchestrator fires in background.
# Poll session until COMPLETED:
watch -n2 "curl -s http://localhost:8000/sessions/$SESSION_ID | jq '{status, context}'"
# Expect: status=COMPLETED, context.backlog_items, selected_items, assignments, phase_history
```
