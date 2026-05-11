# US-05 — Technical Decisions

**Story:** [US-05 Reference PO Agent](../user-stories/US-05-reference-po-agent.md)  
**Status:** Implemented (Phase 1)

---

## 1. Auth validation checks the HTTP Authorization header, not the task envelope

AC7 requires the agent to reject calls whose auth scheme does not match its Agent Card. The task envelope (`TaskEnvelope`) carries no auth field — auth is conveyed at the HTTP transport layer as an `Authorization` header (injected by `A2AClient._auth_headers`). The `_check_auth` guard reads `request.headers["authorization"]` and compares against the agent's declared scheme:

- `scheme: none` → reject any request that carries a `Bearer …` header (HTTP 401).
- `scheme: bearer` → reject any request that lacks an `Authorization` header (HTTP 401).

This mirrors exactly what the platform's `A2AClient` sends, so valid platform calls always pass; replayed or misconfigured calls with the wrong scheme are rejected.

---

## 2. Deterministic voting uses item priority from session_ctx.backlog_items

AC5 requires dot votes to be cast deterministically using only fields in `session_ctx`. The implementation reads `session_ctx.backlog_items`, builds a `{item_id: priority}` map, and returns each item's own declared priority as the vote. This is:

- **Deterministic:** same backlog → same votes, no randomness.
- **Contextual:** uses only `session_ctx` fields; no external lookups, no internal agent state.
- **Semantically correct:** the PO agent votes highest priority for items it itself marked as HIGH when presenting the backlog.

Items absent from `backlog_items` default to `"MEDIUM"`.

---

## 3. confirm returns false when selected_items is absent or empty

AC6 specifies `{ confirmed: true }` only when `session_ctx.selected_items` is non-empty. This guards against a mistaken early confirm call during backlog presentation (when `selected_items` is still `null`). An empty list is treated as "no items selected" and also produces `confirmed: false`.

---

## 4. Static backlog has 6 items with realistic story-point estimates

AC4 requires ≥5 items. Six items were chosen to provide enough spread for Phase 2 (prioritisation + capacity selection) to be observable in end-to-end tests. All items conform to the `BacklogItem` schema validated by `phase_orchestrator.BacklogItem` — `item_id`, `title`, `description`, `priority`, `story_points`, `labels`, `dependencies` — with no `metadata` field.

Story points are populated (not null) on all items so capacity-limited sessions (`sprint_capacity` in session context) exercise the greedy selection algorithm.

---

## 5. present_backlog remains an async SSE task

The short `asyncio.sleep(0.3)` before completing the SSE stream is retained so the A2A client exercises its async/SSE code path in every end-to-end run. Removing it would mean `present_backlog` could be collapsed into a synchronous handler, which would eliminate test coverage of the SSE path in Phase 1.

---

## 6. Verification

```bash
# Start stack
cd src && docker compose up

# Check Agent Card
curl -s http://localhost:8001/.well-known/agent.json | jq .

# AC7: auth mismatch (agent expects 'none' — bearer token should be rejected)
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST http://localhost:8001/a2a/tasks \
  -H "Authorization: Bearer fake-token" \
  -H "content-type: application/json" \
  -d '{"task_id":"t1","task_type":"session_ready","session_ctx":{},"payload":{}}'

# AC3: session_aborted
curl -s -X POST http://localhost:8001/a2a/tasks \
  -H "content-type: application/json" \
  -d '{"task_id":"t2","task_type":"session_aborted","session_ctx":{},"payload":{}}' | jq .

# AC5/AC6: vote + confirm round-trip
curl -s -X POST http://localhost:8001/a2a/tasks \
  -H "content-type: application/json" \
  -d '{
    "task_id":"t3","task_type":"vote",
    "session_ctx":{"backlog_items":[{"item_id":"PO-1","priority":"HIGH"},{"item_id":"PO-3","priority":"MEDIUM"}]},
    "payload":{"items":["PO-1","PO-3"]}
  }' | jq .
# Expect: {"votes":{"PO-1":"HIGH","PO-3":"MEDIUM"}}

curl -s -X POST http://localhost:8001/a2a/tasks \
  -H "content-type: application/json" \
  -d '{"task_id":"t4","task_type":"confirm","session_ctx":{"selected_items":["PO-1"]},"payload":{}}' | jq .
# Expect: {"confirmed":true}

curl -s -X POST http://localhost:8001/a2a/tasks \
  -H "content-type: application/json" \
  -d '{"task_id":"t5","task_type":"confirm","session_ctx":{"selected_items":[]},"payload":{}}' | jq .
# Expect: {"confirmed":false}
```
