# US-01: A2A Task Sending & SSE Subscription

**Phase:** 1 — A2A Baseline
**Reference:** [design-doc.md §3](../design-doc.md#3-a2a-protocol)

## Story
As the **platform**, I want to send A2A tasks to any registered Remote Agent endpoint and subscribe to its SSE stream, so that I can drive a planning session with heterogeneous agents over a standard open protocol.

## Acceptance Criteria
- [x] AC1: Platform can `POST /tasks` to an agent's declared endpoint with a JSON payload containing `task_type`, `task_id`, and `session_ctx`.
- [x] AC2: Platform handles the synchronous `completed` response path (short decisions like `vote`, `confirm`).
- [x] AC3: Platform handles the asynchronous path: agent returns `202 { task_id, status: "working" }`, and platform opens an SSE subscription to `GET /tasks/{id}`.
- [x] AC4: SSE stream parses `working` progress events and a terminal `completed` or `failed` event.
- [x] AC5: Platform applies the agent's declared auth scheme (e.g. Bearer token) from its Agent Card on every task call.
- [x] AC6: Task timeouts are enforced — if an agent does not reach `completed` within the phase's `duration_limit`, the task is marked `failed` and the orchestrator proceeds per template rules.
- [x] AC7: All task requests, responses, and SSE events are logged with `session_id` and `task_id`.

> Technical decisions taken while implementing this story are recorded in
> [../decisions/US-01-a2a-client.md](../decisions/US-01-a2a-client.md).

## Out of Scope
- Persistent outbound WebSocket connections from agents to platform.
- Polling-based fallback when SSE is unsupported.
- Agent-initiated push to the platform (agents only respond, never originate).
- Retry / exponential backoff strategies (basic single-attempt only in Phase 1).
- Multi-tenant rate limiting.
