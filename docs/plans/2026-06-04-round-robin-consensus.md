# Round-Robin Discussion & Agent Consensus — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace free-for-all pub/sub discussion with platform-directed round-robin turns (one message per participant per round) and per-agent stop conditions for definite consensus.

**Architecture:** Extend `_handle_discussion` with a new `ROUND_ROBIN` code path in the phase orchestrator. Platform sends `your_turn` A2A tasks sequentially, collects responses, synthesizes backlog proposals after each round, and tracks per-agent "done" signals to detect consensus. Template schema gains round-robin configuration fields. No Redis pub/sub subscription in round-robin mode — platform is the sole coordinator.

**Tech Stack:** Python 3.11, FastAPI, Redis (existing comm_bus), asyncio, Pydantic

---

## Design Decisions

### Turn Order
Participants ordered by role priority: PRODUCT_OWNER → ARCHITECT → DEVELOPER → HUMAN.
Within same role: by join order (participant_id alphabetical as tiebreak).

### Consensus Detection
Each participant's turn response includes `done: bool` (default `false`).
When ALL participants return `done: true` in the same round → consensus.
When ALL participants return `done: true` **and** no new items were proposed that round → definite consensus (stop condition met).

### Platform Synthesis After Each Round
After collecting all turn responses for a round:
1. Platform extracts all `add_item` / `modify_item` suggestions
2. Runs recommender against the updated backlog to re-rank
3. Broadcasts a `round_summary` with proposed changes + updated item list

### Timeout Per Turn
Each participant gets `turn_timeout_seconds` (default 30s) to respond. Timeout = auto-"done" with no content.

### Max Rounds
`max_rounds` (default 5) prevents infinite loops. Reaching max rounds = forced consensus.

### Humans in Round-Robin
Humans don't have A2A endpoints. Platform publishes `your_turn` to comm bus for the human participant. UI shows "It's your turn" prompt. Human response comes via the existing POST /sessions/{id}/chat endpoint. Platform waits for human response with the same turn timeout.

---

## Files Affected

| File | Change |
|------|--------|
| `src/platform/app/template_schema.py` | Add `RoundRobinConfig` fields to `OpenDiscussionAction` |
| `src/platform/templates/sprint_planning_v2.yaml` | Update OPEN_DISCUSSION → round-robin mode |
| `src/platform/app/phase_orchestrator.py` | New `_handle_round_robin_discussion()` function |
| `src/platform/app/a2a/models.py` | Add `your_turn` / `turn_response` task types |
| `tests/test_v2_e2e.py` | Update to work with round-robin flow |

---

### Task 1: Update Template Schema — Round-Robin Config Fields

**Objective:** Extend `OpenDiscussionAction` with round-robin configuration fields.

**Files:**
- Modify: `src/platform/app/template_schema.py`

**Changes:**
Add optional fields to `OpenDiscussionAction`:
```python
class OpenDiscussionAction(ActionBase):
    type: Literal["OPEN_DISCUSSION"]
    context: Literal["recommendation", "assignment"] | None = None
    allowed_actions: list[str] | None = None
    timeout_seconds: int | None = None
    strategy: str | None = None
    fallback: str | None = None
    # NEW — round-robin config
    turn_timeout_seconds: int | None = None   # per-participant turn timeout (default 30)
    max_rounds: int | None = None             # max discussion rounds (default 5)
    synthesize_proposals: bool | None = None  # whether platform proposes new items after each round
```

**Verification:** `template_schema.py` parses without errors; `sprint_planning_v2.yaml` still loads.

---

### Task 2: Update v2 Template YAML for Round-Robin

**Objective:** Switch discussion phases from free-for-all to round-robin with consensus stop.

**Files:**
- Modify: `src/platform/templates/sprint_planning_v2.yaml`

**Changes:**
```yaml
      actions:
        - type: GENERATE_RECOMMENDATION
          strategy: semantic_similarity
        - type: OPEN_DISCUSSION
          context: recommendation
          allowed_actions: [add_item, remove_item, modify_item]
          turn_timeout_seconds: 30
          max_rounds: 5
          synthesize_proposals: true
      turn_order: ROUND_ROBIN
      transition: AUTO
```
(Apply same to assignment phase OPEN_DISCUSSION)

**Verification:** Template loads via `load_yaml_template()` without validation errors.

---

### Task 3: Build `_handle_round_robin_discussion()` — Core Orchestrator Logic

**Objective:** Implement the round-robin discussion handler with consensus detection.

**Files:**
- Modify: `src/platform/app/phase_orchestrator.py`

**New function:** `_handle_round_robin_discussion()`

```
Signature:
async def _handle_round_robin_discussion(
    session, slots, context, allowed_actions,
    turn_timeout_seconds, max_rounds, synthesize_proposals,
    backlog_items, selected_items, assignments,
    phase_id, phase_name, phase_history, human_messages,
) -> tuple[list[str], dict[str, str], int]:

Returns: (final_selected_items, final_assignments, round_count)
```

**Algorithm:**

```
ordered_slots = sort slots by role priority (PO → ARCHITECT → DEV → HUMAN)
consensus_state = {slot.id: False for all ordered_slots}
round_count = 0

while round_count < max_rounds:
    round_messages = []
    new_items_proposed = False

    for slot in ordered_slots:
        if slot already done: skip (but still counts for consensus)
        send your_turn task to slot (or comm_bus for humans)
        response = await with timeout(turn_timeout_seconds)
        if timeout: mark slot as done, continue
        round_messages.append(response)
        consensus_state[slot.id] = response.get("done", False)

    # Check consensus: all done, no new items this round
    all_done = all(consensus_state.values())
    if all_done and not new_items_proposed:
        break

    # Platform synthesis
    if synthesize_proposals:
        new_items = _synthesize_from_round(round_messages, backlog_items)
        if new_items:
            backlog_items.extend(new_items)
            new_items_proposed = True
            # Re-run recommender to re-rank
            re_ranked = recommend(backlog_items, session.sprint_goal, total_capacity)
            selected_items = [it["item_id"] for it in re_ranked]

    # Broadcast round_summary
    await _broadcast_round_summary(...)
    round_count += 1

    if all_done:
        break  # consensus with proposals but all say done

return selected_items, assignments, round_count
```

**Sub-function:** `_synthesize_from_round()`
- Extracts add_item suggestions from round messages
- Validates them as BacklogItem
- Returns list of new item dicts

**Sub-function:** `_broadcast_round_summary()`
- Publishes CommEvent with: round number, who spoke, proposed new items, current state, consensus progress

**Verification:** Round-robin discussion enters, iterates participants, produces round_count ≥ 1.

---

### Task 4: Wire Round-Robin into Discussion Dispatcher

**Objective:** Route to round-robin handler when `turn_order == ROUND_ROBIN` on the phase.

**Files:**
- Modify: `src/platform/app/phase_orchestrator.py`

**Changes in `_orchestrate()`:**
In the `OPEN_DISCUSSION` / `GENERATE_RECOMMENDATION` / `GENERATE_ASSIGNMENT` action blocks, check if the **phase** has `turn_order: ROUND_ROBIN`. If so, call `_handle_round_robin_discussion()` instead of `_handle_discussion()`.

The phase's `turn_order` field needs to be accessible — it's in `template_row.phases[phase_index]`. Currently the orchestrator iterates phases but doesn't pass `turn_order`. Thread it through.

**Changes in `_handle_recommend()`:**
Pass `turn_order` through to decide whether to use round-robin discussion.

**Verification:** When template has `turn_order: ROUND_ROBIN`, the new handler is invoked. When not, old behavior preserved.

---

### Task 5: Add `your_turn` / `turn_response` to A2A Task Types

**Objective:** Define the task type contracts for round-robin communication.

**Files:**
- Modify: `src/platform/app/a2a/models.py`

**Changes:**
Add documentation/constants — no model changes needed since `task_type` is a free string and `content` is `dict[str, Any]`. But document the contract:

```python
# Round-Robin Task Types (US-41)

# Platform → Participant: "your_turn"
#   task_type: "your_turn"
#   content: {
#       "round": int,
#       "context": "recommendation" | "assignment",
#       "current_state": {...},  # current items/assignments
#       "discussion_so_far": [...],  # messages from this round so far
#   }

# Participant → Platform: turn response (returned as task artifact)
#   artifact: {
#       "message": str,             # free-text contribution
#       "actions": [                # structured actions
#           {"type": "add_item"|"remove_item"|"modify_item"|"volunteer"|"object"|"reassign", ...}
#       ],
#       "done": bool,               # True = nothing more to add
#   }
```

**Verification:** Documentation is clear; no breaking changes.

---

### Task 6: Update Agent Responses for `done` Signal

**Objective:** Ensure agents (po-agent, dev-agent, llm-po-agent, llm-dev-agent) handle `your_turn` and return `done` field.

**Files:**
- Modify: `src/agents/po-agent/app/main.py`
- Modify: `src/agents/dev-agent/app/main.py`
- Modify: `src/agents/llm-po-agent/app/main.py` (if needed)
- Modify: `src/agents/llm-dev-agent/app/main.py` (if needed)

**Changes:**
Each agent's task handler needs a new case for `task_type == "your_turn"`:
```python
if task_type == "your_turn":
    round_num = payload.get("round", 0)
    context = payload.get("context", "")
    # Agent decides: do I have something to say?
    message = agent_think(context, payload)
    done = agent_is_done(context, payload)  # True if nothing to add
    
    return {
        "message": message,
        "actions": agent_propose_actions(context, payload),
        "done": done,
    }
```

For reference agents (po-agent, dev-agent): implement simple heuristics.
- `done` = True if: (a) no new ideas after 3 rounds, or (b) current proposal already matches what agent would suggest
- LLM agents: let the LLM decide based on prompt

**Verification:** Agents respond to `your_turn` with a valid response including `done` field.

---

### Task 7: Update E2E Test for Round-Robin Flow

**Objective:** Adapt the e2e test (`test_v2_e2e.py`) to work with round-robin discussion.

**Files:**
- Modify: `tests/test_v2_e2e.py`

**Changes:**
Instead of injecting messages directly into Redis, the test needs to:
1. Wait for platform to send `your_turn` to agents
2. Agents auto-respond (reference agents handle `your_turn`)
3. Verify round_summary events are published
4. Verify consensus is reached (session completes)
5. Verify `recommendation_rounds` ≥ 1 and each round includes turn data

Also inject human "your_turn" response via POST /sessions/{id}/chat to exercise the human path.

**Verification:** `python3 test_v2_e2e.py` passes with the round-robin template.

---

### Task 8: Integration Test — Consensus Stop Condition

**Objective:** Verify that when all agents signal `done`, the phase terminates.

**Test scenario:**
1. Session with 2 agents (PO + DEV)
2. Round 1: both agents say `done: true`, no new items → phase should end after round 1
3. Verify `recommendation_rounds == 1`

**Implementation:** Unit test in `tests/` that mocks agent responses to return `done: true` immediately.

**Verification:** Test passes, consensus is detected.

---

## Rollback Safety
- Old `_handle_discussion()` is preserved for non-ROUND_ROBIN templates
- v1 template (`sprint_planning_v1.yaml`) is untouched
- Template field additions are optional (backwards-compatible)

## Pitfalls
- **Human turn timeout**: If the human doesn't respond within `turn_timeout_seconds`, they're marked done. This could be frustrating. Consider longer default timeout for humans (60s vs 30s for agents).
- **Deadlock**: If a participant never responds and never times out (no timeout configured), the phase hangs. Always enforce a turn timeout.
- **Message ordering**: Platform sends turns sequentially (not parallel), so round order is deterministic and predictable.
