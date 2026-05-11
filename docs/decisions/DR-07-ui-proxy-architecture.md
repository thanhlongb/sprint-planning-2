# DR-07: UI Proxy Architecture

**Date:** 2026-05-12  
**Status:** Accepted  
**US:** US-07 React UI Human Proxy

## Context

The platform's Phase Orchestrator dispatches A2A tasks to participants via HTTP (`POST /a2a/tasks`). For human participants, this requires an **HTTP server** reachable from within the Docker network — the browser itself cannot expose such an endpoint.

We need a lightweight server co-located with the React UI that:
1. Exposes A2A-compliant endpoints (`/.well-known/agent.json`, `POST /a2a/tasks`, `GET /a2a/tasks/:task_id`)
2. Bridges inbound platform tasks to the browser via SSE
3. Relays browser responses back to the awaiting platform SSE subscriber

## Decision: Hono + Bun on a separate port

### Runtime: Bun

The project uses `bun` as its JS runtime (per user rules). Bun natively runs TypeScript without transpilation, has a built-in HTTP server, and is already installed as the package manager. No additional runtime overhead.

### Framework: Hono

Hono is a lightweight, edge-ready web framework with first-class SSE support via `streamSSE()`. It runs natively on Bun and shares the same package ecosystem. Alternatives considered:

| Option | Reason rejected |
|--------|----------------|
| Express | Requires `@types/express`, heavier middleware model, no SSE helpers |
| Fastify | Overkill for this small proxy; more complex SSE setup |
| Vite middleware | Cannot run in production Docker; tightly coupled to dev server |
| Node.js `http` module | Too low-level; SSE boilerplate is verbose |

### Port: 5174 (separate from Vite's 5173)

Running the proxy on a separate port decouples its lifecycle from the Vite dev server. In Docker, the proxy runs as its own service (`ui-proxy`). In local dev, the Vite dev server proxies `/proxy/*`, `/a2a/*`, and `/.well-known/*` to `localhost:5174` so the browser sees a single origin.

### Endpoint Strategy for Human Join

The platform's `_reachable_slots()` function filters slots by `endpoint != None`. Human slots created via session creation have `endpoint = None`. To make the platform dispatch tasks to the human proxy:

- The join endpoint (`POST /sessions/{id}/join`) is extended to accept an optional `endpoint` field in the `JoinByHuman` request body.
- The proxy server sends this endpoint (its own `/a2a` URL) when submitting the human join on behalf of the browser.
- The platform stores it in `SessionParticipant.endpoint`, making the human slot reachable.

This is the simplest option that requires no new DB tables or registration flows.

### SSE Bridge Pattern

```
Platform ──POST /a2a/tasks──► Proxy server
                                  │
                        Store task + resolve fn
                        Return 202 { working }
                                  │
                Platform ─GET /a2a/tasks/:id (SSE)──► Proxy server
                                  │  (keeps connection open)
Browser ─GET /proxy/tasks (SSE)──► Proxy server
                                  │
                        Push task to browser SSE
                                  │
Browser ──POST /proxy/respond────► Proxy server
                                  │
                        Emit `completed` on platform SSE
```

In-memory `Map<task_id, { resolve, reject }>` holds the pending promise. When the browser POSTs a response, the proxy resolves it, which causes the SSE generator to emit the `completed` event and close the stream.

### Task Response Mode

| Task type | Mode |
|-----------|------|
| `session_invite` | Sync 200 (ack immediately) |
| `session_ready` | Sync 200 (ack immediately) |
| `session_aborted` | Sync 200 (ack immediately) |
| `acknowledge_assignment` | Sync 200 (ack immediately) |
| `present_backlog` | Sync 200 (PO-only; human just views) |
| `vote` | Async 202 + SSE (human must interact) |
| `assign_opportunity` | Async 202 + SSE (human must interact) |
| `confirm` | Async 202 + SSE (human must interact) |

### Resilience

Per AC7: closing the browser tab must not crash the session. The proxy SSE `/proxy/tasks` stream to the browser is a separate connection from the platform SSE `/a2a/tasks/:id`. If the browser disconnects, the platform SSE remains open until the orchestrator's `duration_limit_seconds` timeout fires, at which point the proxy resolves with a `failed` status, consistent with AC6.
