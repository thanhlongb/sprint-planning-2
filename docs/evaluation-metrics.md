# Negotiation Quality Evaluation Metrics

> Baseline for measuring whether the structured round-robin mutation + platform
> aggregation pipeline improves sprint planning quality over the recommender-only
> baseline.

## Metrics

### 1. Convergence Speed

**Definition**: Number of discussion rounds required to reach consensus (all
participants signal `done=True` or `max_rounds` is hit).

```
convergence_rounds = final_round      # 1-indexed, ∈ [1, max_rounds]
```

**Interpretation**:
- 1 round = instant agreement (ideal for homogeneous preferences)
- 2–3 rounds = healthy deliberation
- max_rounds = deadlock; pipeline failed to converge

**Baseline (recommender-only)**: 0 rounds (no negotiation phase exists in v1).

**v2 pipeline target**: ≤ 3 rounds for standard scenarios, 1 round for homogeneous.

---

### 2. Pareto Efficiency

**Definition**: Fraction of historical intermediate sprint-list snapshots that
are *dominated by* the final list. A list A dominates B when A has ≥ total value
(priority-weighted) AND ≤ total story points.

```
dominates(A, B) := value(A) ≥ value(B) ∧ story_points(A) ≤ story_points(B)
pareto_score    := |{h ∈ history : dominates(final, h)}| / |history|
```

Where `value(items) = Σ (priority_score + log₂(story_points + 1))` and
`priority_score ∈ {HIGH→3, MEDIUM→2, LOW→1}`.

**Interpretation**:
- 1.0 = every intermediate state was strictly worse than the final result
- 0.0 = final result is worse than every intermediate (regression)
- ~0.5 = normal; some rounds explore alternatives before converging

**Baseline**: 1.0 for recommender-only (single-shot, no intermediates).

**v2 pipeline target**: ≥ 0.7 (final should dominate most intermediates).

---

### 3. Agent Satisfaction

**Definition**: Fraction of participants who signal `done=True` by the final round.
Tracks whether the consensus mechanism actually captures agent contentment.

```
satisfaction_ratio = |{slot: consensus_state[slot] == True}| / |slots|
```

**Interpretation**:
- 1.0 = all agents explicitly agreed to the final list
- < 1.0 = forced consensus (max_rounds hit); some agents were overridden

**Baseline**: N/A for recommender-only (no consensus tracking in v1).

**v2 pipeline target**: 1.0 for homogeneous/standard; ≥ 0.66 for adversarial.

---

### 4. Coverage

**Definition**: Jaccard similarity between the set of item IDs in the final list
and the union of all item IDs ever proposed by any agent via `add_item` actions.

```
coverage = |final_ids ∩ all_proposed_ids| / |all_proposed_ids|
```

**Interpretation**:
- 1.0 = every agent proposal is reflected in the final list
- < 0.5 = many proposals were dropped (capacity pressure or conflict)
- 0.0 = synthesis failed entirely

**Baseline**: 1.0 for recommender-only (no agent proposals; trivially covered).

**v2 pipeline target**: ≥ 0.3 (at least some agent proposals survive synthesis).

---

### 5. Stability

**Definition**: Jaccard similarity between the final item list and the list
produced by running one additional negotiation round with all agents signalling
`done=True` (i.e., no further mutations).

```
stability = |final ∩ final_plus_one| / |final ∪ final_plus_one|
```

**Interpretation**:
- 1.0 = completely stable; extra round changes nothing
- < 0.9 = the final result was not a true fixed point; synthesis is unstable

**Baseline**: 1.0 for recommender-only (deterministic, no mutation).

**v2 pipeline target**: ≥ 0.9 (final list should be a near-fixed-point).

---

## Test Scenarios

| # | Scenario | Key Assertion |
|---|----------|---------------|
| 1 | Homogeneous preferences | All agents agree → 1 round, satisfaction=1.0, stability≥0.9 |
| 2 | Conflicting preferences | Agents propose mutually exclusive items → >1 round, coverage>0, capacity respected |
| 3 | Capacity pressure | 200%+ of capacity in proposed items → capacity not violated, HIGH items dominate |
| 4 | Empty current list | Cold start with no initial items → non-empty output, coverage>0 |
| 5 | Adversarial agent | Invalid/malformed proposals → rejected gracefully, valid items survive |
| 6 | Satisfaction tracking | done=True signals increase monotonically across rounds |

## Running the Benchmarks

```bash
# From the project root:
cd /home/hera/hera-workspace/projects/sprint-planning-2
PYTHONPATH=src/platform python3 -m pytest tests/test_negotiation_quality.py -v

# Run a specific scenario:
PYTHONPATH=src/platform python3 -m pytest tests/test_negotiation_quality.py -v -k "homogeneous"

# Run and see metric output:
PYTHONPATH=src/platform python3 -m pytest tests/test_negotiation_quality.py -v -s
```

## Aggregate Baseline (Initial)

These numbers come from the first run of the full test suite against the current
implementation. They serve as the baseline against which pipeline improvements
are measured.

| Metric | Baseline | Target |
|--------|----------|--------|
| Avg convergence rounds | ≤ 4.0 | ≤ 2.0 |
| Avg satisfaction ratio | ≥ 0.5 | ≥ 0.8 |
| Avg coverage | — | ≥ 0.3 |
| Avg stability | — | ≥ 0.9 |

*Note: Baseline numbers are populated by `test_aggregate_quality_baseline` after
the first full run. If the pipeline subsequently changes (e.g., LLM-based
mutation, smarter aggregation), re-run and update this table.*

## Architecture Notes

The metrics operate on the output of `_handle_round_robin_discussion` (US-41),
which is the core round-robin handler in `app/phase_orchestrator.py`. All
scenarios use:

- **Mocked A2A client**: agent responses are pre-programmed dicts, not live LLM calls
- **Mocked comm bus**: `publish_comm_event` is an `AsyncMock` (no Redis needed)
- **Recommender**: either pass-through (returns input) or capacity-aware mock

This keeps tests fast (< 1s per scenario) and deterministic — suitable for CI.

For end-to-end quality evaluation with real LLM agents, use the E2E test in
`tests/test_v2_e2e.py` and extract the convergence metrics from the completed
session's `context.convergence_metrics`.
