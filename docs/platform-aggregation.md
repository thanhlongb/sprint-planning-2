# Platform Aggregation Mechanism

> Sibling: `docs/mutation-algebra-and-agent-contract.md` (defines B_i mutation format)
> Parent analysis: ABN is overkill; keep aggregation LLM-driven but feed it structured agent outputs

## 1. Overview

Given N agent mutation sets B_1...B_n (each an ordered list of `{type, target_key, payload, justification}` tuples), produce a new sprint list A' that:

| Constraint | How enforced |
|---|---|
| Respects capacity | Stage 2 feasibility check rejects overflow; items trimmed by lowest score |
| Balances agent preferences | Stage 1 scores mutations by support count + preference rank, not just majority |
| Pareto improvement when possible | Stage 1 only applies mutations that improve or maintain total score; Stage 2 can override only with explicit trade-off rationale |
| Defined tie-breaking | 3-level cascade: agent provenance -> capacity utilization -> item key |

---

## 2. Mechanism Evaluation

### 2.1 Weighted Borda Count

**How it works:** Agents rank mutations by preference position (rank 1 = highest weight). Pick mutations with highest aggregate Borda score.

**Verdict: Supplemental only.** Borda works for ranking discrete alternatives (e.g., "which items should be in the sprint"), but mutations are *operations on state*, not candidates. `ADD(X)` from agent A and `REMOVE(X)` from agent B are not comparable by rank -- they're a conflict, not a preference ordering problem. Borda also ignores capacity constraints and inter-mutation dependencies (e.g., `SWAP(X,Y)` and `ADD(Y)` interact).

**Where it helps:** Within a mutation *type* for the same key, Borda can resolve "which variant wins." E.g., agent A proposes `RESCOPE(X, 5)`, agent B proposes `RESCOPE(X, 8)` -> Borda on position picks 5.

### 2.2 LLM-as-Judge

**How it works:** Feed all B_i + current A + capacity + goal to a fresh LLM with a balancing prompt. LLM outputs A'.

**Verdict: Best for edge cases, risky as sole mechanism.** The current `/synthesize` endpoint already does this with raw NL transcripts. With structured inputs it becomes more reliable, but:
- Non-deterministic -- same inputs can produce different outputs
- No formal guarantees (optimality, fairness)
- Cost per round scales with total tokens
- Hard to publish as a novel mechanism ("we asked GPT to decide")

### 2.3 Minimal Concession

**How it works:** Start from A. Each round, apply only mutations with >=2 agents in agreement. Iterate until no new mutations meet the threshold.

**Verdict: Safe but slow.** Produces Pareto improvements by construction (any change >=2 agents support is unlikely to harm any single agent's objective). But:
- Low agreement threshold (2/N) means many conflicts still pass
- High threshold (N) means gridlock
- No mechanism for resolving genuine disagreements
- Convergence not guaranteed without a fallback

### 2.4 Constraint Satisfaction

**How it works:** Encode each agent's mutation preferences as soft constraints (penalize violating agent A's top-ranked mutation). Solve with an optimizer (ILP, weighted MAX-SAT).

**Verdict: Formally strongest, practically brittle.** Guarantees an optimal solution under the encoded constraints. But:
- Encoding NL justifications as mathematical constraints is lossy
- Requires a solver dependency (ortools, z3)
- Tuning penalty weights is an art, not a science
- Agents can "game" the system by proposing extreme mutations knowing the optimizer will split the difference

---

## 3. Chosen Mechanism: Two-Stage Hybrid

```
B_1...B_n (ordered mutation lists)
         |
    -----+-----
    | Stage 1 |  Deterministic conflict resolution
    |         |  - Group mutations by target key
    |         |  - Score & select winner per conflict group
    |         |  - Apply non-conflicting mutations directly
    |         |  - Output: A1 (intermediate sprint list)
    -----+-----
         |
         |  A1 + unresolved conflicts + all justifications
         |
    -----+-----
    | Stage 2 |  LLM refinement
    |         |  - Validate feasibility (capacity check)
    |         |  - Resolve remaining edge cases
    |         |  - Fill gaps (items no agent proposed but should be in)
    |         |  - Output: A' (final sprint list) + reasoning trace
    -----+-----
         |
        A'  (new sprint list)
```

### Rationale

Stage 1 is **deterministic and reproducible** -- the core of the research contribution. It handles ~80% of cases where mutations are either non-conflicting or have a clear winner via the scoring function. This is the part we can formalize, test, and publish.

Stage 2 is **LLM-driven** -- inherits the robustness of the current `/synthesize` approach but operates on structured inputs with much of the heavy lifting already done. It handles the ~20% edge cases: conflicting mutations with equal Stage 1 scores, capacity overflow, novel items the agents missed.

### Why not pure deterministic?

Pure deterministic aggregation (Borda, approval voting, constraint solving) can't handle the semantic content of justifications. Two agents might propose `REMOVE(X)` for different reasons -- one because X is too large for the sprint, another because X is low priority. The LLM can read these justifications and decide that the first agent's concern is resolved by `RESCOPE(X, 3)` while the second agent's concern is valid -- a nuance no deterministic scorer captures.

### Why not pure LLM?

Because we need a reproducible mechanism for the paper. "Ask GPT" is not a research contribution. The hybrid gives us both: a formal core with a practical fallback.

---

## 4. Stage 1 Algorithm

### 4.1 Input

```
A     = current sprint list (set of item keys)
B     = [B_1, B_2, ..., B_n]  where each B_i is an ordered list of mutations
        B_i[j] = {type, target_key, payload, justification}
        Lower j = higher agent preference
capacity = total story points allowed
backlog  = full backlog (key -> {story_points, ...} map)
```

### 4.2 Conflict Groups

Two mutations *conflict* if they target the same key and their combined application would be ambiguous or contradictory:

| Mutation A | Mutation B | Conflict? |
|---|---|---|
| ADD(X) | ADD(X) | No -- both want it added |
| ADD(X) | REMOVE(X) | **Yes** -- opposite intent |
| REMOVE(X) | REMOVE(X) | No -- both want it removed |
| SWAP(X, Y) | ADD(X) | **Yes** -- one removes X, other adds it |
| SWAP(X, Y) | SWAP(X, Z) | **Yes** -- incompatible replacements for X |
| RESCOPE(X, 5) | RESCOPE(X, 8) | **Yes** -- different SP values for same item |
| REORDER(X, 0) | REORDER(X, 2) | **Yes** -- different positions for same item |
| ADD(Y) | REMOVE(X) | No -- target different keys |

A **conflict group** is the transitive closure of mutations that conflict.

### 4.3 Scoring Function

For each mutation m in a conflict group:

```
score(m) = w1 * support_ratio(m) + w2 * rank_score(m) + w3 * specificity_score(m)

where:
  support_ratio(m) = |{B_i : m' in B_i st m' ~= m}| / N
    (how many agents proposed this same mutation, 0..1)

  rank_score(m) = 1 - (rank(m) / max_rank)
    where rank(m) = average position of m across all B_i (0 = highest preference)
    max_rank = max mutation list length across all agents

  specificity_score(m) = heuristic from justification:
    +0.2 if justification references specific item attributes (SP, labels, deps)
    +0.2 if justification references capacity or sprint goal
    +0.1 if justification cites evidence (past sprint data, dependency chain)
    capped at 1.0

  w1 = 0.4  (support weight)
  w2 = 0.35 (rank weight)
  w3 = 0.25 (specificity weight)
```

### 4.4 Selection

```
for each conflict_group:
    winner = argmax(score(m) for m in conflict_group)
    apply winner to A -> intermediate A1

for each non-conflicting mutation:
    apply directly to A1
```

### 4.5 Pseudocode

```python
def stage1_resolve(
    A: set[str],
    B: list[list[Mutation]],
    backlog: dict[str, Item],
    capacity: int,
) -> tuple[set[str], list[Mutation], list[ConflictGroup]]:
    """
    Returns:
      A1: intermediate sprint list
      applied: mutations that were applied
      unresolved: conflict groups that couldn't be resolved deterministically
    """
    all_mutations = flatten(B)
    groups = build_conflict_groups(all_mutations)

    A1 = set(A)
    applied = []
    unresolved = []

    for group in groups:
        if len(group) == 1:
            # No conflict -- apply directly if feasible
            m = group[0]
            if is_feasible(A1, m, backlog, capacity):
                A1 = apply(A1, m, backlog)
                applied.append(m)
        else:
            # Score and select winner
            scored = [(score(m, B), m) for m in group]
            scored.sort(reverse=True)

            winner_score, winner = scored[0]
            runner_up_score, _ = scored[1] if len(scored) > 1 else (0, None)

            # If winner is clearly better (margin > threshold), apply
            if winner_score - runner_up_score > AMBIGUITY_THRESHOLD:
                if is_feasible(A1, winner, backlog, capacity):
                    A1 = apply(A1, winner, backlog)
                    applied.append(winner)
            else:
                # Too close to call -- defer to Stage 2
                unresolved.append(group)

    return A1, applied, unresolved


def score(m: Mutation, B: list[list[Mutation]]) -> float:
    support = count_support(m, B) / len(B)
    rank = average_rank(m, B)
    max_rank = max(len(bi) for bi in B)
    rank_score = 1.0 - (rank / max_rank) if max_rank > 0 else 1.0
    specificity = justification_specificity(m.justification)
    return W_SUPPORT * support + W_RANK * rank_score + W_SPEC * specificity


# Configuration
AMBIGUITY_THRESHOLD = 0.15
W_SUPPORT = 0.40
W_RANK = 0.35
W_SPEC = 0.25
```

---

## 5. Stage 2 Algorithm

### 5.1 Input

```
A1          = Stage 1 output sprint list
unresolved  = list of conflict groups (mutation sets too close to call)
applied     = mutations already applied (for traceability)
B           = original agent mutation sets (for context)
backlog     = full backlog
capacity    = total story points
goal        = sprint goal string
```

### 5.2 LLM Prompt Structure

```python
STAGE2_SYSTEM = """You are the Sprint Planning Aggregator. Your job is to resolve
conflicts that the deterministic resolver couldn't settle and produce the final
sprint list.

You receive:
- The current sprint list after deterministic resolution
- Conflict groups where two or more agents disagreed strongly
- All agent justifications for each conflicting mutation
- Capacity constraints

Rules:
1. Respect the capacity limit -- total story points must not exceed capacity
2. Every change must be justified by at least one agent's argument
3. If you override the deterministic resolver, explain why
4. Output the final sprint list as a sorted list of item keys
5. Prefer mutations supported by more agents, unless a minority argument is
   clearly stronger on the merits
"""

STAGE2_PROMPT = """Sprint goal: {goal}
Capacity: {capacity} story points

=== CURRENT SPRINT LIST (after deterministic resolution) ===
{current_list_text}

=== RESOLVED MUTATIONS (already applied) ===
{applied_text}

=== UNRESOLVED CONFLICTS ===
{conflicts_text}

=== ALL AGENT MUTATION SETS (for context) ===
{agent_sets_text}

Produce the final sprint list. Output format:
1. Brief reasoning (2-4 sentences)
2. ---FINAL---
   KEY-001
   KEY-002
   ...
   ---END---
"""
```

### 5.3 LLM Output Parsing

```python
def parse_stage2_output(response: str) -> tuple[list[str], str]:
    """Extract final item list and reasoning from LLM response."""
    # Extract reasoning (everything before ---FINAL---)
    reasoning = response.split("---FINAL---")[0].strip()

    # Extract item keys
    block_match = re.search(r"---FINAL---\s*(.*?)\s*---END---", response, re.DOTALL)
    if block_match:
        keys = re.findall(r"[A-Z]+-\d+", block_match.group(1))
        return keys, reasoning

    # Fallback: scan for keys anywhere
    keys = re.findall(r"[A-Z]+-\d+", response)
    return keys, reasoning
```

### 5.4 Feasibility Check

After LLM output, validate:

```python
def validate_feasibility(keys: list[str], backlog: dict, capacity: int) -> bool:
    total_sp = sum(backlog[k].story_points for k in keys if k in backlog)
    return total_sp <= capacity

def trim_to_capacity(keys: list[str], backlog: dict, capacity: int) -> list[str]:
    """If LLM output exceeds capacity, drop lowest-priority items."""
    items = [(k, backlog[k]) for k in keys if k in backlog]
    items.sort(key=lambda x: (x[1].priority_rank, x[1].goal_similarity or 0))
    selected = []
    total_sp = 0
    for k, item in items:
        if total_sp + item.story_points <= capacity:
            selected.append(k)
            total_sp += item.story_points
    return selected
```

### 5.5 No-LLM Fallback

When LLM is unavailable (API error, timeout, offline mode):

```python
def stage2_fallback(
    A1: set[str],
    unresolved: list[ConflictGroup],
    B: list[list[Mutation]],
    backlog: dict,
    capacity: int,
) -> list[str]:
    """Deterministic fallback when LLM is unavailable."""
    A_final = set(A1)

    for group in unresolved:
        # Apply the mutation with highest support_count (ignore rank/specificity)
        best = max(group, key=lambda m: count_support(m, B))
        if is_feasible(A_final, best, backlog, capacity):
            A_final = apply(A_final, best, backlog)

    return sorted(A_final)
```

---

## 6. Tie-Breaking Rules

When `score(m1) == score(m2)` in Stage 1 (within floating-point epsilon):

### 6.1 Agent Provenance (Priority 1)

Mutations proposed by higher-priority agents win. Priority order:

```
1. PRODUCT_OWNER     (highest -- PO has final authority)
2. ARCHITECT         (system-level design perspective)
3. DEVELOPER         (implementation perspective)
4. QA                (quality perspective)
5. HUMAN             (lowest priority in automated aggregation)
```

If multiple agents of the same role propose competing mutations, the mutation from the agent with the **lower participant_id** (earlier registrant) wins.

### 6.2 Capacity Utilization (Priority 2)

If agent provenance doesn't resolve (same role, same participant):

- Prefer mutations that bring total SP closer to `capacity * 0.85` (optimal utilization target)
- If both overshoot, prefer the one closer to capacity
- If both undershoot, prefer the higher-SP mutation

### 6.3 Lexicographic by Item Key (Priority 3)

Deterministic last resort. Prefer the mutation whose `target_key` sorts first alphabetically. Guarantees reproducibility.

```python
def tiebreak(m1: Mutation, m2: Mutation, backlog: dict, capacity: int,
             current_set: set[str]) -> Mutation:
    """Resolve score ties deterministically."""
    # Priority 1: Agent provenance
    p1 = ROLE_PRIORITY[m1.agent_role]
    p2 = ROLE_PRIORITY[m2.agent_role]
    if p1 != p2:
        return m1 if p1 < p2 else m2  # lower number = higher priority

    # Same role: earlier registrant wins
    if m1.participant_id != m2.participant_id:
        return m1 if m1.participant_id < m2.participant_id else m2

    # Priority 2: Capacity utilization
    u1 = utilization_after(m1, current_set, backlog, capacity)
    u2 = utilization_after(m2, current_set, backlog, capacity)
    target = capacity * 0.85
    if abs(u1 - target) != abs(u2 - target):
        return m1 if abs(u1 - target) < abs(u2 - target) else m2

    # Priority 3: Lexicographic
    return m1 if m1.target_key < m2.target_key else m2
```

---

## 7. Round Limit and Convergence

### 7.1 Parameters

| Parameter | Default | Description |
|---|---|---|
| `MAX_ROUNDS` | 3 | Maximum mutation->aggregation cycles |
| `CONVERGENCE_WINDOW` | 2 | Consecutive rounds with no new items |
| `AMBIGUITY_THRESHOLD` | 0.15 | Min score margin for Stage 1 to resolve a conflict |

### 7.2 Convergence Detection

```python
def has_converged(
    round_num: int,
    rounds_history: list[RoundResult],
) -> bool:
    """True if the negotiation has reached a stable state."""
    # Hard cap
    if round_num >= MAX_ROUNDS:
        return True

    # Need at least CONVERGENCE_WINDOW rounds to check
    if len(rounds_history) < CONVERGENCE_WINDOW:
        return False

    # Check last CONVERGENCE_WINDOW rounds: no new items proposed
    recent = rounds_history[-CONVERGENCE_WINDOW:]
    new_items_proposed = any(r.new_items_proposed for r in recent)

    # All agents must signal done in the most recent round
    all_done = all(r.all_agents_done for r in recent)

    return (not new_items_proposed) and all_done
```

### 7.3 Forced Consensus at Round Limit

When `round_num == MAX_ROUNDS`:

1. Run **Stage 1 only** (no LLM Stage 2)
2. Apply all non-conflicting mutations
3. For conflicts: take mutation with highest `support_ratio` (ignore rank and specificity)
4. For capacity overflow: drop lowest-priority items until feasible
5. Return A' + metadata flag `forced_consensus: true`

### 7.4 Convergence Criteria (for the paper)

| Metric | Definition |
|---|---|
| Round efficiency | Rounds to convergence / MAX_ROUNDS |
| Mutation acceptance rate | |applied| / |proposed| across all rounds |
| Conflict resolution rate | |Stage 1 resolved| / |total conflicts| |
| Forced consensus rate | % of sessions reaching MAX_ROUNDS |
| Change magnitude | |A' delta A| / |A| (items changed vs initial) |

---

## 8. Full Aggregation Pipeline

```python
async def aggregate(
    A: set[str],                        # current sprint list
    agent_outputs: list[AgentOutput],   # B_1...B_n, each with ordered mutations
    backlog: dict[str, Item],
    capacity: int,
    goal: str,
    round_num: int,
    rounds_history: list[RoundResult],
) -> AggregationResult:
    """
    Main aggregation entry point. Called once per round after all agents
    have submitted their mutation sets.
    """
    # Extract ordered mutation lists
    B = [ao.mutations for ao in agent_outputs]

    # Check convergence before doing work
    if has_converged(round_num, rounds_history):
        return AggregationResult(
            final_list=sorted(A),
            converged=True,
            forced=False,
            reasoning="Consensus reached -- no changes needed.",
            applied_mutations=[],
        )

    # Force consensus at round limit
    if round_num >= MAX_ROUNDS:
        A1, applied, _ = stage1_resolve(A, B, backlog, capacity)
        return AggregationResult(
            final_list=sorted(A1),
            converged=True,
            forced=True,
            reasoning=f"Forced consensus at round {MAX_ROUNDS}.",
            applied_mutations=applied,
        )

    # Normal round: Stage 1 -> Stage 2
    A1, applied, unresolved = stage1_resolve(A, B, backlog, capacity)

    if not unresolved:
        # Stage 1 resolved everything
        return AggregationResult(
            final_list=sorted(A1),
            converged=False,
            forced=False,
            reasoning=f"All conflict(s) resolved deterministically.",
            applied_mutations=applied,
            unresolved_conflicts=[],
        )

    # Stage 2: LLM resolves remaining conflicts
    try:
        final_keys, reasoning = await stage2_llm_refine(
            A1, unresolved, applied, B, backlog, capacity, goal
        )
        final_keys = validate_and_trim(final_keys, backlog, capacity)
    except LLMUnavailableError:
        # Fallback: best-effort deterministic resolution
        final_keys = stage2_fallback(A1, unresolved, B, backlog, capacity)
        reasoning = "LLM unavailable -- used deterministic fallback."

    return AggregationResult(
        final_list=sorted(final_keys),
        converged=False,
        forced=False,
        reasoning=reasoning,
        applied_mutations=applied,
        unresolved_conflicts=unresolved,
    )
```

---

## 9. Edge Cases

| Case | Handling |
|---|---|
| All agents propose empty B_i | A' = A, convergence detected immediately |
| All agents propose identical mutations | Stage 1 resolves all (no conflicts), Stage 2 skipped |
| Capacity exceeded after aggregation | Stage 2 feasibility check trims lowest-priority items |
| Capacity under-utilized (< 50%) | Stage 2 LLM prompted to suggest gap-filling items from backlog |
| Agent proposes item not in backlog | Mutation rejected (validator catches invalid keys) |
| Current sprint list A is empty | First round: Stage 1 conflict groups are all ADD -> non-conflicting, apply all; Stage 2 fills to capacity |
| LLM unavailable for Stage 2 | Fallback to support-count-only selection (Section 5.5) |
| Multiple rounds produce identical A' | Convergence detected at round+1 (no new items) |

---

## 10. Integration with Mutation Algebra Contract

### 10.1 Expected Input Format

Each agent output:
```json
{
  "agent_id": "dev-agent-1",
  "agent_role": "DEVELOPER",
  "participant_id": "part_abc123",
  "round": 2,
  "mutations": [
    {
      "type": "ADD",
      "target_key": "TAWOS-42",
      "payload": {"position": 1},
      "justification": "TAWOS-42 adds API pagination which TAWOS-12 (already in sprint) depends on. Adding it reduces integration risk."
    },
    {
      "type": "REMOVE",
      "target_key": "TAWOS-07",
      "payload": {"reason": "overscoped"},
      "justification": "TAWOS-07 is 13 SP -- too large for a single sprint. We should split it or defer."
    },
    {
      "type": "RESCOPE",
      "target_key": "TAWOS-15",
      "payload": {"new_sp": 3},
      "justification": "Based on last sprint velocity, TAWOS-15 took 3 SP not the estimated 5."
    }
  ],
  "done": false
}
```

### 10.2 Output Format (AggregationResult)

```json
{
  "round": 2,
  "final_list": ["TAWOS-01", "TAWOS-12", "TAWOS-15", "TAWOS-42"],
  "converged": false,
  "forced": false,
  "reasoning": "Applied 5/7 mutations deterministically. LLM resolved SWAP vs ADD conflict on TAWOS-03 in favor of ADD (2 agents cited dependency risk).",
  "applied_mutations": [
    {"type": "ADD", "target_key": "TAWOS-42", "source": "stage1", "support": 3},
    {"type": "REMOVE", "target_key": "TAWOS-07", "source": "stage1", "support": 2},
    {"type": "ADD", "target_key": "TAWOS-03", "source": "stage2", "support": 2}
  ],
  "unresolved_conflicts": [
    {
      "target_key": "TAWOS-03",
      "mutations": [
        {"type": "SWAP", "payload": {"remove_key": "TAWOS-03", "add_key": "TAWOS-18"}, "score": 0.72},
        {"type": "ADD", "payload": {}, "score": 0.71}
      ]
    }
  ],
  "metrics": {
    "total_mutations_proposed": 9,
    "applied_count": 6,
    "stage1_resolved": 4,
    "stage2_resolved": 1,
    "unresolved_count": 0,
    "capacity_utilization_pct": 88.5
  }
}
```

---

## 11. Configuration

```python
@dataclass
class AggregationConfig:
    # Stage 1
    w_support: float = 0.40       # weight for agent support count
    w_rank: float = 0.35          # weight for preference rank
    w_specificity: float = 0.25   # weight for justification specificity
    ambiguity_threshold: float = 0.15  # min score margin to resolve in Stage 1

    # Stage 2
    llm_model: str = "deepseek/deepseek-chat"
    llm_max_tokens: int = 800
    llm_temperature: float = 0.2  # low temp for reproducibility

    # Convergence
    max_rounds: int = 3
    convergence_window: int = 2   # rounds with no new items + all done
    target_utilization: float = 0.85

    # Role priority (lower = higher priority)
    role_priority: dict[str, int] = {
        "PRODUCT_OWNER": 0,
        "ARCHITECT": 1,
        "DEVELOPER": 2,
        "QA": 3,
        "HUMAN": 4,
    }
```

---

## 12. Why This Design

1. **Reproducible core.** Stage 1 is deterministic -- same inputs -> same output. Testable, debuggable, publishable.
2. **LLM handles semantics.** Stage 2 reads justifications and resolves nuance the deterministic scorer can't.
3. **Graceful degradation.** LLM unavailable -> support-count fallback still produces a valid list.
4. **Defined convergence.** Round limit prevents infinite loops. Convergence window makes the stop condition measurable.
5. **Paper-ready metrics.** Round efficiency, mutation acceptance rate, conflict resolution rate, forced consensus rate -- all measurable per session.
6. **Composable with sibling tasks.** Takes structured B_i from mutation algebra contract. Feeds A' into assignment phase. Metrics flow into evaluation task.
