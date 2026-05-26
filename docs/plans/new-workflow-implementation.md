# New Workflow Implementation Plan (v2)

**Date:** 2026-05-26
**Source:** May 25 meeting with Hoa — 7 decisions
**Design decisions:**
- Recommender: separate module `recommender.py`
- Capacity: hardcoded per-agent config (env vars in docker-compose)
- Discussion-driven refinement + assignment — the core research contribution
- v1 template: kept alongside v2

---

## Target Workflow

```
PO provides backlog + sprint goal
        ↓
[RECOMMENDATION]  Platform generates initial goal-aligned task group
        │         DISCUSSION — participants add/remove/modify
        │         Platform recalculates after each round
        │         ← CONVERGENCE measured here (rounds to settle)
        ↓
[ASSIGNMENT]      DISCUSSION — participants volunteer/negotiate
        │         Platform broadcasts opportunities, tracks claims
        │         ← CONVERGENCE measured here too (rounds to full assignment)
        ↓
[CONFIRMATION]    PO accepts final plan (single sign-off)
        ↓
    Sprint Backlog output
```

**Core insight:** Refinement and Assignment are NOT automated dispatches. They are
facilitated discussions. The platform's role is to:
1. Present the current state (recommended list, assignments)
2. Route structured messages between participants
3. Apply modifications when consensus emerges
4. Track round count for convergence measurement

---

## Discussion Protocol

Both recommendation and assignment phases use the existing `comm_bus.py` (Redis pub/sub
per session) and `_send_task_with_comm()` infrastructure for structured messages.

### Recommendation phase messages (generation + refinement)

| Direction | Type | Content |
|-----------|------|---------|
| Platform → all | `recommendation` | Initial ranked list with scores |
| Any → all | `add_item` | `{item_id, title, reason}` |
| Any → all | `remove_item` | `{item_id, reason}` |
| Any → all | `modify_item` | `{item_id, field, old, new}` |
| Platform → all | `recommendation_update` | Recalculated list after changes |

A round ends when: (a) no new proposals within timeout, OR
(b) PO signals `ready_for_assignment`.

### Assignment phase messages (algorithmic proposal + discussion)

| Direction | Type | Content |
|-----------|------|---------|
| Platform → all | `assignment_proposal` | Algorithmic assignment map `{item_id: participant_id}` |
| Any → all | `volunteer` | `{item_id, participant_id}` — claim a task |
| Any → all | `object` | `{item_id, participant_id, reason}` — contest an assignment |
| Any → all | `reassign` | `{item_id, from_pid, to_pid}` — propose reassignment |
| Platform → all | `assignment_update` | Recalculated assignment map after changes |

A round ends when: (a) no new messages within timeout, OR
(b) all items assigned with no objections.

---

## Tasks

### T1 — New template: `sprint_planning_v2.yaml`

File: `src/platform/templates/sprint_planning_v2.yaml`

3 phases:

```yaml
phases:
  - phase_id: recommendation
    name: "Goal-Aligned Recommendation & Refinement"
    actions:
      - type: GENERATE_RECOMMENDATION
      - type: OPEN_DISCUSSION
        context: recommendation
        allowed_actions: [add_item, remove_item, modify_item]
        timeout_seconds: 60
    turn_order: FACILITATOR_LED  # platform generates, then opens discussion
    transition: MANUAL            # PO or timeout advances to assignment

  - phase_id: assignment
    name: "Task Assignment (Algorithmic + Discussion)"
    actions:
      - type: GENERATE_ASSIGNMENT
        strategy: EXPERTISE_BASED
      - type: OPEN_DISCUSSION
        context: assignment
        allowed_actions: [volunteer, object, reassign]
        strategy: VOLUNTEER_FIRST
        fallback: AUTO_BALANCE
    turn_order: FACILITATOR_LED  # platform generates, then opens discussion
    transition: MANUAL

  - phase_id: confirmation
    name: "PO Confirmation"
    actions:
      - type: CONFIRM
        acceptor: PRODUCT_OWNER
    turn_order: ROLE_FIRST
    transition: AUTO
```

Required roles: PRODUCT_OWNER (all phases), DEVELOPER (recommendation, assignment)

### T2 — Recommender module: `recommender.py`

File: `src/platform/app/recommender.py`

Interface:
```python
def recommend(
    backlog_items: list[dict],
    sprint_goal: str,
    total_capacity: int,        # sum of all participants' story point capacity
) -> list[dict]:                # ranked items with scores
```

Algorithm (TF-IDF):
1. Concatenate item title + description
2. TF-IDF cosine similarity between sprint goal and each item
3. Score = α·similarity + β·priority_score (HIGH=3/MEDIUM=2/LOW=1)
4. Greedy selection under total capacity

Configurable via env: `RECOMMENDER_STRATEGY=tfidf`, `RECOMMENDER_ALPHA=0.7`, `RECOMMENDER_BETA=0.3`

### T3 — Assignment algorithm (new in phase_orchestrator.py)

New action handler `_handle_generate_assignment()`:

1. Input: selected items (from recommendation phase), participant list with capacity + expertise
2. Match each item to best-fit participant:
   - Filter: participants with remaining capacity ≥ item story points
   - Score: expertise match to item labels + workload balance
   - Assign to highest-scoring participant
3. Output: assignment map `{item_id: participant_id}`
4. Broadcast as `assignment_proposal` message
5. Then the discussion loop (T4) takes over

### T4 — Discussion phase handler (new in phase_orchestrator.py)

File: `src/platform/app/phase_orchestrator.py`

New action handler `_handle_discussion()` — used by both recommendation and assignment phases:

```
1. Broadcast current state (recommendation list or assignment map)
2. Subscribe to session comm channel
3. Loop:
   a. Wait for messages (with timeout)
   b. If structured action message: validate and apply
      - Recommendation context: add_item, remove_item, modify_item
      - Assignment context: volunteer, object, reassign
   c. Platform recalculates and broadcasts update
   d. If timeout with no activity → advance phase
   e. If all items assigned with no objections → advance phase
   f. PO can signal advance at any time
4. Return final state
```

This replaces the old fire-and-forget `_handle_vote` / `_handle_select` / `_handle_assign` pattern.

### T5 — Phase orchestrator wiring

- Add `_handle_recommend()` — calls recommender, stores initial list, then enters discussion
- Add `_handle_generate_assignment()` — algorithmic expertise-based assignment
- Add `_handle_discussion()` — the core discussion loop (shared by both phases)
- `_handle_confirm()` — simplified: poll PO only, no quorum
- Wire action types: `GENERATE_RECOMMENDATION`, `GENERATE_ASSIGNMENT`, `OPEN_DISCUSSION`, `CONFIRM` (simplified)

### T6 — Agent capacity config

File: `src/docker-compose.yml`

Capacity model per participant:
```json
{
    "story_points": 20,
    "specialties": ["backend", "API", "Python"]
}
```

Env vars:
```yaml
dev-agent:
  environment:
    AGENT_CAPACITY_SP: 20
    AGENT_SPECIALTIES: "backend,API,Python"
llm-dev-agent:
  environment:
    AGENT_CAPACITY_SP: 15
    AGENT_SPECIALTIES: "frontend,React,TypeScript"
```

Surfaced in Agent Card:
```json
{
  "capabilities": {
    "capacity": {
      "story_points": 20,
      "specialties": ["backend", "API", "Python"]
    }
  }
}
```

Usage:
- **Recommender:** sums all participants' `story_points` → total capacity ceiling for item selection
- **Assignment:** matches item `labels` to participant `specialties`; respects per-participant `story_points` limits

### T7 — Convergence tracking

In session context:

| Field | When set | Meaning |
|-------|----------|---------|
| `initial_recommendation` | Start of recommendation discussion | Snapshot of platform's starting list |
| `recommendation_rounds` | Incremented during recommendation | Number of add/remove/modify rounds before list stabilizes |
| `assignment_rounds` | Incremented during assignment | Number of volunteer/negotiate rounds |
| `retention_pct` | At confirmation | len(final ∩ initial) / len(initial) |

### T8 — Agent contract changes

PO agent:
- Handle `accept_plan` — respond `{"accepted": true}` if backlog non-empty
- Keep existing handlers for v1 compatibility

Dev agent:
- Handle `recommendation_update` — ack the message
- Handle `assignment_round` — respond with volunteer/object decisions
- Keep existing vote/confirm handlers for v1

### T9 — Template schema update

Add `OPEN_DISCUSSION`, `GENERATE_RECOMMENDATION`, and `GENERATE_ASSIGNMENT` to action types.
Add `context` and `allowed_actions` fields to action schema.

### T10 — End-to-end test

1. Register agents
2. Create session with `sprint_planning_v2`
3. Verify recommendation phase produces scored list
4. Verify refinement phase accepts add/remove messages
5. Verify assignment phase routes volunteer messages
6. Verify PO accept_plan completes session
7. Verify convergence metrics in session context

---

## Files Changed

| File | Action |
|------|--------|
| `src/platform/templates/sprint_planning_v2.yaml` | New |
| `src/platform/app/recommender.py` | New |
| `src/platform/app/phase_orchestrator.py` | Modify (add recommend + discussion handlers, rewire) |
| `src/platform/app/template_schema.py` | Modify (new action types) |
| `src/docker-compose.yml` | Modify (capacity env vars) |
| `src/agents/po-agent/app/main.py` | Modify (accept_plan handler) |
| `src/agents/dev-agent/app/main.py` | Modify (capacity in Agent Card, new task handlers) |
| `src/agents/llm-dev-agent/app/main.py` | Modify (capacity in Agent Card) |

---

## Out of Scope (Phase 2)

- Human capacity model (hours + expertise + seniority)
- AI compute budget (token limits)
- Multi-round convergence experiment harness
- Anti-gaming metrics
- Future-proof task attributes (business value, AI suitability)
- Natural language discussion parsing (structured messages only for now)
