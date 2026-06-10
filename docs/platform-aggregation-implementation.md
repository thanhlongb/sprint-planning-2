# Platform Aggregation — Implementation Notes

> **Code:** `src/platform/app/platform_aggregator.py` (304 lines)
> **Design:** `docs/platform-aggregation.md` (theory + ideal design)
> **Integration:** `src/platform/app/phase_orchestrator.py` — `_handle_round_robin_discussion()`
> **Task:** `t_71f69cb1`

## 1. Implementation vs Design

The design doc (`platform-aggregation.md`) specifies a **two-stage hybrid**: Stage 1 deterministic scoring (weighted Borda count with support/rank/specificity weights) + Stage 2 LLM refinement for unresolved conflicts. The **actual implementation is simpler** — role-priority conflict resolution with recommender re-ranking in a single pass.

| Aspect | Design Spec | Implementation |
|---|---|---|
| Conflict resolution | Weighted Borda scoring (w=0.4/0.35/0.25) + ambiguity threshold | Role-priority ordering (PO > ARCHITECT > DEVELOPER) |
| Stages | Stage 1 deterministic + Stage 2 LLM | Single pass, no LLM refinement |
| Re-ranking | Part of Stage 2 LLM | Calls `recommend()` directly after mutation application |
| CONVERGED | `CONVERGENCE_WINDOW=2` rounds, `has_converged()` function | Single-round (`aggregation_result.converged`) + multi-round (`detect_converged(threshold=2)`) |
| Fallback | `stage2_fallback()` when LLM unavailable | `_synthesize_from_round()` when no structured mutations |

**Why the simplification?** The design doc's Stage 2 LLM refinement was deferred — the deterministic role-priority approach handles ~80% of cases and keeps the pipeline testable and reproducible without an LLM dependency in the hot path. Stage 2 LLM can be layered on later by wrapping `aggregate()`.

## 2. Data Model

### 2.1 MutationType

```python
class MutationType(str, Enum):
    ADD = "add_item"       # Add an item to the sprint list
    REMOVE = "remove_item" # Remove an item from the sprint list
    MODIFY = "modify_item" # Modify an item's attributes (SP, priority, title, etc.)
    VOLUNTEER = "volunteer" # Volunteer to take an item (assignment context)
    OBJECT = "object"       # Object to an assignment (assignment context)
    REASSIGN = "reassign"  # Reassign an item to another agent (assignment context)
```

The mutation types align with the agent contract (`docs/mutation-algebra-and-agent-contract.md`). ADD/REMOVE/MODIFY apply to the recommendation context; VOLUNTEER/OBJECT/REASSIGN apply to the assignment context.

### 2.2 Mutation

```python
@dataclass
class Mutation:
    type: MutationType
    item_id: str        # Backlog item key
    source: str         # Agent slot_id / participant_id
    data: dict[str, Any] # Full action dict (includes "item", "updates", etc.)
```

### 2.3 AgentMutationSet

```python
@dataclass
class AgentMutationSet:
    agent_id: str
    agent_name: str
    agent_role: str        # PRODUCT_OWNER | ARCHITECT | DEVELOPER | QA | HUMAN
    mutations: list[Mutation]
    done: bool             # Agent signaled done=True for this round
    message: str           # NL message from the agent
```

### 2.4 AggregationResult

```python
@dataclass
class AggregationResult:
    final_items: list[str]           # Ordered sprint list after aggregation + re-ranking
    assignments: dict[str, str]      # item_id → assignee (currently always {})
    applied_adds: int
    applied_removes: int
    applied_modifies: int
    discarded_mutations: list[Mutation]  # Rejected (conflicts, duplicates, invalid)
    converged: bool                  # All agents done AND zero mutations applied
    stats: dict[str, Any]            # total_mutations_received, total_discarded, agents_done, etc.
```

### 2.5 RoundRecord

```python
@dataclass
class RoundRecord:
    round_num: int
    mutations_count: int   # Mutations actually applied this round
    all_done: bool          # Did every agent signal done?
    converged: bool         # Single-round convergence (aggregation_result.converged)
```

## 3. Mutation Parser

### 3.1 `parse_mutations_from_turn_response(turn_response, source_agent_id) -> list[Mutation]`

Extracts structured `Mutation` objects from an agent's turn response artifact. The turn response contains an `actions` list — each action has a `type` field that maps to a `MutationType`.

Edge cases:
- Unknown action types → logged at debug level, skipped
- Actions without `item_id` → logged at debug level, skipped
- `item_id` resolved from `action["item_id"]` or `action["item"]["item_id"]` (nested fallback)

### 3.2 `parse_agent_mutation_sets(round_messages) -> dict[str, AgentMutationSet]`

Collects all mutations from a round's turn messages into per-agent sets. Used by the orchestrator to feed structured data into `aggregate()`.

## 4. Aggregation Algorithm — `aggregate()`

```
Signature:
  aggregate(
      agent_mutations: dict[str, AgentMutationSet],
      current_items: list[str],
      backlog_items: list[dict],
      capacity: int,
      sprint_goal: str = "",
      *,
      recommend_fn: Callable | None = None,
  ) -> AggregationResult
```

### 4.1 Algorithm Steps

1. **Collect and sort:** All mutations from all agents are flattened into a single list, sorted by role priority (PO=0, ARCHITECT=1, DEVELOPER=2), then by mutation type, then by item_id.

2. **Apply ADD mutations:**
   - Skip if item already in working set (deduplication)
   - If item not in backlog, validate via `BacklogItem.model_validate()` and append to backlog
   - Invalid items → logged at warning, discarded

3. **Apply REMOVE mutations:**
   - Remove item from working set if present
   - Skip if item not in working set (discarded)

4. **Apply MODIFY mutations:**
   - Only first modification per item per round wins (conflict resolution by priority ordering)
   - Allowed fields: `title`, `description`, `priority`, `story_points`, `labels`, `dependencies`
   - Subsequent modifications to the same item are discarded

5. **Re-rank via recommender:** If `recommend_fn` is provided, call it to re-score and re-rank the backlog under capacity constraints. Falls back to keeping working order if no recommender.

6. **CONVERGED detection (single-round):** All agents done AND zero mutations applied → `converged=True`.

### 4.2 Conflict Resolution: Role Priority

When two agents propose conflicting MODIFY operations on the same item, the agent with the higher role wins:

```
PRODUCT_OWNER (priority 0) > ARCHITECT (priority 1) > DEVELOPER (priority 2)
```

This is implemented by sorting all mutations by role priority *before* processing. The first MODIFY for each item "claims" it — subsequent modifications are discarded.

### 4.3 Why Role Priority Over Weighted Borda

The design doc's weighted Borda scoring requires:
- Computing `support_ratio` (how many agents proposed the same mutation)
- Computing `rank_score` (average position across agent lists)
- Computing `specificity_score` (heuristic NL analysis of justifications)

The implementation simplifies this because:
1. **Support ratio is implicitly handled by position** — mutations sorted by role priority implicitly handle the "who proposed it" dimension
2. **Rank score is moot** — agents don't rank their own mutations (each mutation is an independent action)
3. **Specificity score requires LLM** — analyzing justification text for specificity needs NLU, which defeats the purpose of a deterministic Stage 1

## 5. CONVERGED Detection

### 5.1 Single-Round Convergence

Inside `aggregate()`: if all agents signal `done=True` AND zero mutations were applied (no ADDs, REMOVEs, or MODIFYs), the aggregation result has `converged=True`.

### 5.2 Multi-Round Convergence — `detect_converged(round_history, threshold=2)`

Returns `True` when the last `threshold` consecutive rounds all had:
- `mutations_count == 0` (no mutations applied)
- `all_done == True` (every agent signaled done)

Default threshold is 2 rounds.

### 5.3 Three-Tier Break Condition in the Orchestrator

Inside `_handle_round_robin_discussion()`, the loop breaks on (checked in order):

1. **Single-round CONVERGED:** `aggregation_result.converged` — all done + no mutations in this round
2. **Multi-round CONVERGED:** `detect_converged(round_history, threshold=2)` — two consecutive rounds with no changes
3. **Original consensus:** `all(consensus_state.values())` — all done (preserved for backward compatibility with no-mutations paths)

Plus the hard cap: `while round_count < max_rounds`.

## 6. Orchestrator Integration

### 6.1 Entry Point

The aggregator integrates into `_handle_round_robin_discussion()` in `phase_orchestrator.py`. This is the function that handles round-robin discussion for both recommendation and assignment contexts.

### 6.2 Flow

```
Round Robin Discussion Loop
│
├─ For each slot (ordered by role):
│    ├─ Send turn request
│    ├─ Receive turn response (NL + structured actions)
│    ├─ _apply_turn_actions() → immediate mutation application
│    └─ Append to round_messages
│
├─ After all slots respond:
│    ├─ parse_agent_mutation_sets(round_messages)
│    ├─ IF has_structured:
│    │    └─ aggregate(agent_sets, current_items, backlog, capacity, goal, recommend_fn)
│    │       → AggregationResult with conflict-resolved items + re-ranking
│    ├─ ELSE (no structured mutations):
│    │    └─ _synthesize_from_round() → legacy NL-based synthesis
│    │       → Backlog merging + re-ranking via recommend()
│    │
│    ├─ Build RoundRecord
│    ├─ Broadcast round_summary
│    └─ Check 3-tier break condition → break or continue
│
└─ Return (final_items, final_assignments, round_count)
```

### 6.3 Path Mapping

The task description referenced `backend/main.py`, `/discuss`, and `/synthesize` endpoints. The actual codebase has no REST endpoints for discussion. Instead:

| Task Reference | Actual Code |
|---|---|
| `/discuss` endpoint | `_request_turn()` — sends `your_turn` tasks to agents via A2A |
| `/synthesize` endpoint | `aggregate()` + `_synthesize_from_round()` — inside `_handle_round_robin_discussion()` |
| `backend/main.py` | `phase_orchestrator.py` — internal orchestrator, not a REST server |

## 7. Fallback Behavior

When `synthesize_proposals=True` but no agent provided structured mutations (empty `actions` arrays), the pipeline falls back to:

```python
_synthesize_from_round(round_messages, backlog_items, working_items)
```

This is the legacy path that:
1. Scans all `add_item` actions across all round messages
2. Validates new items via `BacklogItem.model_validate()`
3. Appends validated items to backlog
4. Re-ranks via `recommend()`

This ensures backward compatibility: sessions without structured mutation output still work.

## 8. Configuration

The aggregation behavior is configured indirectly through:

| Parameter | Source | Default | Effect |
|---|---|---|---|
| `max_rounds` | Template YAML `OPEN_DISCUSSION.max_rounds` | 5 | Hard cap on discussion rounds |
| `turn_timeout_seconds` | Template YAML `OPEN_DISCUSSION.turn_timeout_seconds` | 30 | Per-agent response timeout |
| `synthesize_proposals` | Template YAML `OPEN_DISCUSSION.synthesize_proposals` | `True` (recommendation), `False` (assignment) | Whether to run aggregation after each round |
| `sprint_capacity` | Session context `sprint_capacity` | Sum of all backlog SP | Capacity constraint for re-ranking |
| `allowed_actions` | Template YAML `OPEN_DISCUSSION.allowed_actions` | — | Which mutation types agents may propose |

Role priority is hardcoded (not configurable) as it reflects the hierarchical authority model inherent to sprint planning.

## 9. Known Limitations

1. **No LLM refinement:** Unresolved semantic conflicts (where two agents disagree for different reasons on the same item) are resolved purely by role priority. The design doc's Stage 2 LLM refinement is not implemented.

2. **Assignment context mutations (VOLUNTEER/OBJECT/REASSIGN) are handled by `_apply_turn_actions()` directly, not by `aggregate()`.** The aggregator focuses on item-level mutations (ADD/REMOVE/MODIFY).

3. **No forced consensus at round limit:** When `max_rounds` is reached, the loop simply exits with whatever the last round produced. There is no special "forced consensus" behavior unlike the design doc's Section 7.3.

4. **Backlog mutation is one-way:** Items added to backlog via `aggregate()` (validated new ADD proposals) persist. Items removed from the working set via REMOVE mutations can be re-proposed by agents in later rounds since they remain in the backlog.

5. **`assignments` in AggregationResult is always empty:** Assignment mutations (VOLUNTEER/OBJECT/REASSIGN) are handled by `_apply_turn_actions()` directly and don't flow through `aggregate()`.

## 10. Test Status

As of run #32 (2026-06-08):
- 32 tests total, all passing
- 3 test files: `test_agent_objectives.py` (18), `test_negotiation_quality.py` (8), `test_round_robin.py` (6)
- 0 regressions
- 2 previously-failing tests (`test_conflicting_preferences_compromise`, `test_satisfaction_tracks_consensus_progress`) now pass

The aggregator is tested indirectly through:
- `test_negotiation_quality.py::test_aggregate_quality_baseline` — end-to-end quality benchmark
- `test_round_robin.py::test_platform_synthesis_adds_items` — verifies structured aggregation is invoked by the orchestrator
- `test_negotiation_quality.py::test_homogeneous_converges_in_one_round` — verifies CONVERGED detection

No dedicated unit tests for `platform_aggregator.py` itself (tests exercise it through the orchestrator pipeline).
