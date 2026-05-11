# US-01 — Technical Decisions

**Story:** [US-01 A2A Task Sending & SSE Subscription](../user-stories/US-01-a2a-task-sending.md)
**Status:** Implemented (Phase 1)

This note records non-obvious choices made while building the platform-side A2A
client and updating the reference agents. Anything that can be derived from
the code (file paths, function names, etc.) is left out.

---

## 1. Task envelope shape

The design doc only specifies that the request "contains `task_type`,
`task_id`, and `session_ctx`". We additionally include an optional `payload`
field for task-specific arguments (e.g. ballot items for `vote`, the candidate
`item_id` for `assign_opportunity`). Keeping `payload` separate from
`session_ctx` preserves the design-doc invariant that `session_ctx` is a
shared, append-only view of the session — it should not be polluted with
per-task arguments.

Final wire format (request body to `POST {endpoint}/tasks`):

```json
{
  "task_id":    "uuid",
  "task_type":  "vote",
  "session_ctx": { /* §11 SessionContext */ },
  "payload":    { "items": ["PO-1", "PO-2"] }
}
```

## 2. Sync vs. async dispatch — agent decides

The platform does not declare up-front whether a task is sync or async. The
agent chooses by responding with `200` (sync, body is the terminal event) or
`202 {task_id, status: "working"}` (async, platform must subscribe). This
keeps the protocol symmetric with the design doc §3.3 sequence diagram and
means the platform never needs a per-task-type policy table.

For the reference agents, only `present_backlog` is async — it's the one task
expected to take noticeable wall-clock time in real PO implementations
(fetching a backlog from Jira/GitHub). All other reference tasks are sync.

## 3. SSE framing

We use the minimal SSE subset: `data: {json}\n\n`, one JSON object per frame,
no `event:` or `id:` fields. The platform parses lines starting with `data:`
and ignores everything else (comments, keepalives). Rationale: the protocol
already carries a `status` discriminator inside the JSON, so a separate SSE
`event:` name would be redundant.

A stream is considered well-formed iff it terminates with a frame whose
`status` is `completed` or `failed`. If the connection closes before that,
the platform raises `A2AError` — the orchestrator (US-04) will translate
this to a `failed` task and continue per template rules (AC6 fallback).

## 4. Auth scheme handling (AC5)

The Agent Card declares an `auth.scheme`. The platform implements:

| Scheme   | Behaviour                                           |
|----------|-----------------------------------------------------|
| `none` / unset | No `Authorization` header sent                |
| `bearer` | `Authorization: Bearer <token>` on every call       |
| anything else | `A2AError` raised — agent registration should have failed earlier |

**Token provisioning is deliberately out of scope for Phase 1.** A single
platform-wide token (`A2A_BEARER_TOKEN` env var) is applied to every
bearer-scheme agent. The design doc explicitly says "No API key is issued by
the platform" (§5), so the token is expected to be provisioned out-of-band by
the agent operator and shared with the platform deployer. Per-agent token
storage and rotation will land alongside multi-org registration (US-15).

## 5. Timeouts (AC6)

A single `duration_limit_seconds` bounds the **entire** task — the POST, the
SSE handshake, and all streamed events combined. We do not apply separate
budgets for connect / read / stream-idle, because the meaningful guarantee the
orchestrator needs is "we have an answer (or a failure) by T+limit".

On timeout the client returns a synthetic `TaskResult(status=FAILED, error="timeout after Ns")`
rather than raising. This lets the orchestrator treat agent failure and
timeout uniformly (US-04 will need this).

## 6. Logging (AC7)

Stdlib `logging` with a `LoggerAdapter` that prefixes every line with
`[session=… task=…]`. We considered structured JSON logs but decided against
it for Phase 1 — the audit log story (US-14) will introduce a proper sink and
schema; for now stdout is enough to satisfy AC7 and keep the implementation
small.

Logged events: request dispatch (URL, task_type, timeout), HTTP response
status, sync completion, async accept (202), every SSE frame, timeout, and
terminal status. Request and response **bodies** are *not* logged by default —
they can contain backlog content, which the platform is contractually
forbidden from inspecting beyond what the protocol requires (Principle:
Zero Internal Visibility).

## 7. What was deliberately not built

Explicitly excluded by the story's "Out of Scope" section and therefore
deferred:

- Retry / exponential backoff on transient HTTP failures (Phase 2+)
- Polling fallback when SSE isn't available (we assume HTTP/1.1 SSE works)
- Persistent connection pools — each `send_task` creates a fresh
  `httpx.AsyncClient`. Cheap enough at Phase 1 scale; revisit if profiling
  shows it matters.
- Per-agent bearer tokens (see §4).
- Agent → platform push (agents only respond; design doc §3.4).

## 8. Verifying the implementation end-to-end

The platform exposes `POST /a2a/send` (router `a2a_debug`) purely as a manual
test hook. Once the orchestrator lands (US-04) this endpoint can be removed
or gated behind a debug flag.

```bash
# 1. register PO agent
curl -X POST http://localhost:8000/participants \
  -H 'content-type: application/json' \
  -d '{"agent_card_url":"http://po-agent:8001/.well-known/agent.json"}'

# 2. async path — present_backlog returns 202 then streams SSE
curl -X POST http://localhost:8000/a2a/send \
  -H 'content-type: application/json' \
  -d '{"participant_id":"<id>","task_type":"present_backlog"}'

# 3. sync path — vote returns 200 immediately
curl -X POST http://localhost:8000/a2a/send \
  -H 'content-type: application/json' \
  -d '{"participant_id":"<id>","task_type":"vote","payload":{"items":["PO-1"]}}'

# 4. timeout path — use a comically low limit on the async task
curl -X POST http://localhost:8000/a2a/send \
  -H 'content-type: application/json' \
  -d '{"participant_id":"<id>","task_type":"present_backlog","duration_limit_seconds":0.1}'
```
