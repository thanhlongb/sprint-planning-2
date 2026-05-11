# US-06 — Technical Decisions

**Story:** [US-06 Reference Dev Agent](../user-stories/US-06-reference-dev-agent.md)  
**Status:** Implemented (Phase 1)

---

## 1. Agent identity resolved from session_ctx.participants, not a hard-coded ID

AC5 requires the agent to count its own accepted assignments by reading `session_ctx.assignments` with no internal counter. To map assignment `participant_id` values back to this agent, the implementation looks up `AGENT_NAME` in `session_ctx.participants`:

```python
def _own_participant_id(session_ctx):
    for p in (session_ctx.get("participants") or []):
        if p.get("name") == AGENT_NAME:
            return p.get("participant_id")
    return None
```

`AGENT_NAME` is set via the `AGENT_NAME` environment variable (defaulting to `"dev-agent"`). This matches the value injected by docker-compose and what the platform writes into the participants list when building `session_ctx`. No participant ID is hard-coded or stored between calls — the lookup is re-derived on every task call (AC7: stateless).

---

## 2. Configurable acceptance ceiling via MAX_ASSIGNMENTS env var (AC4)

The acceptance rule `volunteer = current_count < MAX_ASSIGNMENTS` is exposed as an environment variable (`MAX_ASSIGNMENTS`, default `2`). This allows the demo operator to:

- Run two dev-agent instances with different `MAX_ASSIGNMENTS` values to show the CONFLICT_RESOLVED path in the assignment decision tree.
- Set `MAX_ASSIGNMENTS=0` to force a fully AUTO_BALANCE session.
- Set `MAX_ASSIGNMENTS=99` to simulate an eager volunteer that accepts everything.

The current count is read from `session_ctx.assignments` on each call, so no counter is persisted across restarts (AC5, AC7).

---

## 3. Deterministic voting mirrors item priority from session_ctx.backlog_items (AC3)

Same strategy as the PO agent (see US-05 decision 2): `vote` reads `session_ctx.backlog_items`, builds a `{item_id: priority}` map, and returns each item's declared priority as the vote. This is:

- **Deterministic:** same backlog → same votes, no randomness.
- **Derived only from session_ctx:** no external lookups, no internal state.

Items absent from the backlog default to `"MEDIUM"`.

---

## 4. confirm returns false when agent has zero assignments (AC6)

`_handle_confirm` calls `_count_own_assignments` and returns `confirmed = count > 0`. This satisfies AC6 ("unless the agent has zero assignments") and ensures the PO-only confirmation path (where DEVELOPER agents have no assignments) does not produce a false positive quorum.

---

## 5. Auth validation matches PO agent pattern

The same `_check_auth` guard from US-05 is applied: check the HTTP `Authorization` header against `_AUTH_SCHEME`. Currently `_AUTH_SCHEME = "none"`, so any request carrying a `Bearer` token is rejected with HTTP 401. This mirrors what `A2AClient._auth_headers` sends and is consistent with the dev-agent's Agent Card declaration.

---

## 6. Verification

```bash
# Start stack
cd src && docker compose up

# Check Agent Card (AC1)
curl -s http://localhost:8002/.well-known/agent.json | jq .
# Expect: role=DEVELOPER, can_vote=true, can_volunteer=true

# AC2: session_aborted
curl -s -X POST http://localhost:8002/a2a/tasks \
  -H "content-type: application/json" \
  -d '{"task_id":"t1","task_type":"session_aborted","session_ctx":{},"payload":{}}' | jq .

# AC3: vote — mirrors priority from session_ctx.backlog_items
curl -s -X POST http://localhost:8002/a2a/tasks \
  -H "content-type: application/json" \
  -d '{
    "task_id":"t2","task_type":"vote",
    "session_ctx":{"backlog_items":[{"item_id":"PO-1","priority":"HIGH"},{"item_id":"PO-3","priority":"LOW"}]},
    "payload":{"items":["PO-1","PO-3"]}
  }' | jq .
# Expect: {"votes":{"PO-1":"HIGH","PO-3":"LOW"}}

# AC4/AC5: volunteer when below MAX_ASSIGNMENTS (current=0, MAX=2)
curl -s -X POST http://localhost:8002/a2a/tasks \
  -H "content-type: application/json" \
  -d '{
    "task_id":"t3","task_type":"assign_opportunity",
    "session_ctx":{
      "participants":[{"name":"dev-agent","participant_id":"p1"}],
      "assignments":{}
    },
    "payload":{"item_id":"PO-1","title":"Add OAuth login"}
  }' | jq .
# Expect: {"volunteer":true}

# AC4/AC5: decline when at MAX_ASSIGNMENTS (current=2, MAX=2)
curl -s -X POST http://localhost:8002/a2a/tasks \
  -H "content-type: application/json" \
  -d '{
    "task_id":"t4","task_type":"assign_opportunity",
    "session_ctx":{
      "participants":[{"name":"dev-agent","participant_id":"p1"}],
      "assignments":{"PO-1":"p1","PO-2":"p1"}
    },
    "payload":{"item_id":"PO-3","title":"Dark mode"}
  }' | jq .
# Expect: {"volunteer":false}

# AC6: confirm=true when agent has assignment
curl -s -X POST http://localhost:8002/a2a/tasks \
  -H "content-type: application/json" \
  -d '{
    "task_id":"t5","task_type":"confirm",
    "session_ctx":{
      "participants":[{"name":"dev-agent","participant_id":"p1"}],
      "assignments":{"PO-1":"p1"}
    },
    "payload":{}
  }' | jq .
# Expect: {"confirmed":true}

# AC6: confirm=false when agent has no assignment
curl -s -X POST http://localhost:8002/a2a/tasks \
  -H "content-type: application/json" \
  -d '{
    "task_id":"t6","task_type":"confirm",
    "session_ctx":{
      "participants":[{"name":"dev-agent","participant_id":"p1"}],
      "assignments":{}
    },
    "payload":{}
  }' | jq .
# Expect: {"confirmed":false}
```
