# Task Context for LLM-Agent Implementation

## Repository
`/home/hera/hera-workspace/projects/sprint-planning-2`
Branch: `feat/llm-agents`

## What to Build
Two A2A Remote Agent implementations that listen on HTTP endpoints and respond to platform task messages:

### 1. LLM-Backed PO Agent (US-24)
- Uses an LLM to dynamically generate a realistic backlog from a `sprint_goal`
- Streams reasoning/thoughts during long-running tasks
- Votes intelligently (prioritises items aligned with sprint goal)
- Stateless: relies on full `session_ctx` injected into LLM prompt context per decision
- Correctly formats LLM output to match platform JSON schemas

### 2. LLM-Backed Dev Agent (US-25)
- Uses an LLM to evaluate `backlog_items` against a configurable developer persona (e.g., frontend specialist)
- Reasons about workload/capabilities before volunteering for tasks
- Streams reasoning/thoughts during `vote` and `assign_opportunity` tasks
- Handles platform timeouts gracefully (5000ms fallback for assignments)

## Platform Architecture (Key Facts)

- FastAPI backend at `/src/platform`
- A2A client at `src/platform/app/a2a/client.py`
- Agent Card protocol: `GET /.{well-known}/agent.json` → returns `{name, role, capabilities, endpoint, auth}`
- Task endpoint: `POST {endpoint}/tasks` with `TaskEnvelope` body
- Sessions go through phases: backlog_presentation → prioritisation → assignment → confirmation

### Key Platform Files
- `src/platform/app/a2a/client.py` — how platform sends tasks
- `src/platform/app/a2a/models.py` — TaskEnvelope, TaskEvent schema (import these to understand the message format)
- `src/platform/app/phase_orchestrator.py` — what task types are sent and when
- `src/platform/app/api/registry.py` — registration flow

### Task Types Each Agent Must Handle

For PO Agent (role: PRODUCT_OWNER):
- `session_invite` — platform invites to session
- `session_ready` — session starts
- `present_backlog` — generate backlog from sprint_goal (AC1-US-24)
- `vote` — cast ballot (AC3-US-24)
- `acknowledge_assignment` — ack
- `confirm` — confirm sprint goal
- `sprint_backlog` — receive final backlog

For Dev Agent (role: DEVELOPER):
- `session_invite` — platform invites to session
- `session_ready` — session starts
- `vote` — evaluate items against persona (AC1-US-25)
- `assign_opportunity` — decide whether to volunteer (AC2-US-25)
- `acknowledge_assignment` — confirm assignment
- `confirm` — confirm sprint goal
- `sprint_backlog` — receive final backlog

### Message Format
The platform sends a `TaskEnvelope` (see `src/platform/app/a2a/models.py`):
- `task_id`, `task_type`, `session_ctx`, `payload`
- For sync response: return `{task_id, status, artifact?: {...}}`
- For async response: return `{task_id, status: "working"}` then stream `{status, artifact, progress}` via SSE

Session context contains: `session_id`, `sprint_goal`, `template_id`, `participants[]`, `current_phase`, `backlog_items`, `selected_items`, `assignments`, `phase_history`, etc.

### Agent Card Format
Each agent exposes `GET /.well-known/agent.json`:
```json
{
  "name": "LLM PO Agent",
  "description": "Dynamic backlog generation + intelligent voting",
  "role": "PRODUCT_OWNER",
  "capabilities": {
    "can_provide_backlog": true,
    "can_vote": true
  },
  "endpoint": "http://localhost:8011",
  "auth": { "scheme": "none" }
}
```

## Directory Structure
```
src/
  agents/          ← NEW: put agent implementations here
    po_agent/      ← PO Agent (US-24)
    dev_agent/     ← Dev Agent (US-25)
  ui/              ← existing UI
  platform/        ← existing platform
```

## LLM Provider
Use OpenAI API (gpt-4o) as default. Make it configurable via env var `LLM_PROVIDER=openai|anthropic` with corresponding env vars (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).

## Implementation Requirements
- Each agent is a standalone FastAPI app with its own `main.py`
- Run agents at ports 8011 (PO) and 8012 (Dev)
- Use Pydantic models for strict response validation (AC5-US-24, AC4-US-25)
- Add `requirements.txt` or `pyproject.toml` for each agent with dependencies
- Dockerfile for each agent
- Update `docker-compose.yml` to include both agents
- The PO agent should generate 10-15 diverse backlog items from a sprint goal
- The Dev agent should support persona configuration (e.g., `specialties: ["frontend", "UI"]`)
- Streaming progress messages should use the SSE format the platform expects
- Include clear prompts/templates for the LLM calls
- The agents must be stateless (per-session state passed in `session_ctx`)

## Quality Gates
- Both agents validate their LLM output against the expected schema
- If LLM returns malformed data, fallback to a reasonable default
- If LLM call fails, return a graceful error with `status: "failed"`, not a crash
- Include logging with `session_id` and `task_id` context
- No hardcoded backlog — items must come from LLM generation
- No deterministic voting — votes must be LLM-informed
- Timeout handling: 5s for assignments, 30s for other tasks (matches platform defaults)
