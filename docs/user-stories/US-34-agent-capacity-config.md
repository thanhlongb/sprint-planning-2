# US-34: Agent Capacity Configuration

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md), May 25 meeting (dual capacity model)

## Story
As a **platform operator**, I want each agent to declare its capacity (story points + specialties) so that the recommender and assignment algorithm can make capacity-aware decisions.

## Acceptance Criteria
- [ ] AC1: Dev agents expose capacity via environment variables: `AGENT_CAPACITY_SP` (int) and `AGENT_SPECIALTIES` (comma-separated string).
- [ ] AC2: Capacity surfaced in Agent Card `/.well-known/agent.json` under `capabilities.capacity` as `{story_points: N, specialties: [...]}`.
- [ ] AC3: Platform reads capacity from Agent Card during participant registration and stores in the participant record.
- [ ] AC4: `docker-compose.yml` updated: `dev-agent` gets `AGENT_CAPACITY_SP=20`, `AGENT_SPECIALTIES=backend,API,Python`; `llm-dev-agent` gets `AGENT_CAPACITY_SP=15`, `AGENT_SPECIALTIES=frontend,React,TypeScript`.
- [ ] AC5: PO agent has no capacity fields (not a developer) but Agent Card remains valid.
- [ ] AC6: Missing capacity fields default to `story_points=0, specialties=[]` (graceful degradation).

## Out of Scope
- Per-session capacity overrides.
- Runtime capacity changes mid-session.
- Human capacity model (hours, seniority) and AI compute budget (token limits).
