# Baseline Comparison Approach — Resource Budget & Experimental Design

**Status:** Refinement of `evaluation-methodology-design.md` §2–3, §8 Q2
**Date:** 2026-06-10
**Feeds into:** `t_dbb9d4dc` (final design doc synthesis)

---

## 1. The Resource Budget Problem (Resolving §8 Q2)

The existing doc defines three baselines and convergence-based comparison well. The gap:
how to operationalize "equal resource budget" between our structured coordination
and an unstructured LLM free-for-all.

Four options evaluated:

| Option | Mechanism | Problem |
|--------|-----------|---------|
| Equal wall-clock | Same timeout for both | Baseline chat agents may produce fewer tokens/sec; budget not truly equal |
| Equal LLM call count | Same number of API calls | Calls differ wildly in token count between structured vs. free-form |
| Equal token budget | Cap total tokens across all calls | Prevents Baseline A from ballooning; directly measures efficiency |
| No cap (convergence-only) | Both run until natural stop | Baseline A may never converge; risks unbounded cost |

### Chosen Design: Dual-Level Comparison

**Level 1 — Convergence Quality (primary):** Both systems run until convergence
with a generous safety-net `max_rounds=10`. No token cap. Compare:
- `rounds_to_convergence` (lower = better)
- `output_quality` at convergence
- `total_tokens_consumed` (secondary resource metric)

This answers: "Given freedom to run, which produces better plans?"

**Level 2 — Equal-Budget Quality (secondary):** Fix a token budget B, run both
systems, stop at budget exhaustion. For Baseline A (free-for-all), this means
the chat transcript is cut at budget B and the final plan is extracted from
whatever was said. Compare output quality at budget exhaustion.

This answers: "Given the same compute, which produces better plans?"

### How to set the token budget B

B is the mean total tokens consumed by HAiSP v2 across all Phase 2 scenarios
(8 scenarios × 3 replicates = 24 observations). Calculate:

```
B = mean(tokens_v2) + 1.96 * SE(tokens_v2)  # upper 95% CI
```

This ensures Baseline A is NEVER token-starved — it gets at least as many tokens
as v2 typically uses, and usually more. Any quality advantage v2 shows at this
budget is therefore conservative.

### Fallback: If Baseline A never converges

In Level 1, if Baseline A hits `max_rounds=10` without convergence:
- Record `forced_convergence=true`
- Extract final plan from transcript (same extraction LLM call)
- This becomes a data point AGAINST Baseline A — it failed to converge

In Level 2, budget exhaustion is the stopping condition — no convergence issue.

---

## 2. Baseline Implementations — Concrete Specs

### Baseline A: Unstructured Free-for-All

**Setup:** N agents in a shared chat channel. No mutation algebra, no round-robin
ordering, no aggregation algorithm. Agents see the full transcript history and
respond in free-form NL.

**Protocol:**
```
1. System prompt to each agent: "You are a {role} in a sprint planning session.
   The sprint goal is: {goal}. Capacity: {capacity} SP. Backlog: {backlog_items}.
   Current sprint list: {initial_list}. Discuss and agree on the final sprint
   list. Respond in natural language. When you believe the group has reached
   consensus, say CONSENSUS: followed by the agreed item keys."

2. Round-robin turns (to control for ordering effects — same ordering as v2):
   Agent 1 responds → Agent 2 responds → ... → Agent N responds → repeat

3. After each full round, an evaluator LLM checks: has consensus emerged?
   - Criterion: All agents stated agreement (CONSENSUS: tag or equivalent) AND
     no new item proposals for 2 consecutive turns.
   - Evaluator outputs: {converged: bool, final_items: [keys]}

4. Continue until convergence or max_rounds=10.

5. Extract final sprint plan: if converged, use the last CONSENSUS: list.
   If not converged, ask evaluator LLM to synthesize plan from full transcript.
```

**Key differences from HAiSP v2:**
- No structured mutation format — agents speak in NL
- No conflict detection — disagreements resolved through persuasion only
- No deterministic aggregation — all synthesis is LLM-driven
- No convergence signal beyond NL agreement

### Baseline B: Independent Proposal + Single-Shot Synthesis

**Setup:** Each agent independently proposes their ideal sprint plan. No
inter-agent communication. A single LLM call synthesizes all proposals.

**Protocol:**
```
1. Each agent independently: given backlog + capacity + goal, produce ideal
   sprint list with justifications. Same system prompt as HAiSP v2 agents
   minus the round-robin/mutation instructions.

2. Synthesizer LLM: given all N proposals + backlog + capacity + goal,
   produce a single sprint plan. Prompt: "Synthesize these N independent
   sprint plan proposals into one optimal plan. Resolve conflicts by
   preferring proposals with stronger justifications. Respect capacity."

3. Output: final sprint list.
```

**Key difference from HAiSP v2:** No iteration. One shot. Isolates the value
of iterative deliberation.

### Baseline C: Recommender-Only (v1 platform)

The existing `sp2-moo` recommender with no agent discussion layer.
Directly from `src/platform/app/recommender.py`.

**Protocol:**
```
1. Given backlog + capacity + goal, recommender produces sprint list.
2. No agent involvement, no negotiation, no mutations.
3. Output: ranked sprint list.
```

**Key difference from HAiSP v2:** No agent discussion, no mutation algebra.
Isolates the value of the entire negotiation layer.

---

## 3. Control Variables

| Variable | How Controlled | Why |
|----------|---------------|-----|
| **Backlog instance** | Same 8 scenarios for all approaches | Identical problem instances |
| **Agent roles** | Same role definitions, same capability declarations | Same participants |
| **LLM model** | Same model (DeepSeek V3), same temperature (0 for Phase 2 reproducibility) | Same underlying intelligence |
| **Agent system prompts** | Same backlog/goal/capacity presentation; differ only in coordination mechanism | Isolate mechanism, not information |
| **Turn ordering** | Round-robin for both v2 and Baseline A (same order) | Control for ordering effects |
| **Initial sprint list** | Same A_0 for all approaches (or same empty list for cold-start) | Same starting conditions |
| **Evaluation protocol** | Same metrics, same extraction method, same judge LLM | Fair comparison |

---

## 4. Measurement Protocol

### Primary Metrics (per scenario × replicate)

| Metric | v2 | Baseline A | Baseline B | Baseline C |
|--------|-----|-----------|------------|------------|
| Priority-Weighted Utilization | ✓ | ✓ | ✓ | ✓ |
| Goal Alignment | ✓ | ✓ | ✓ | ✓ |
| Role Balance | ✓ | ✓ | ✓ | ✓ |
| Dependency Satisfaction | ✓ | ✓ | ✓ | ✓ |
| Capacity Efficiency | ✓ | ✓ | ✓ | ✓ |
| Rounds to Convergence | ✓ | ✓ | N/A | N/A |
| Total Tokens Consumed | ✓ | ✓ | ✓ | ✓ |
| Wall-Clock Time | ✓ | ✓ | ✓ | ✓ |

### Secondary Metrics (where applicable)

| Metric | v2 | Baseline A |
|--------|-----|-----------|
| Mutation Acceptance Rate | ✓ | N/A |
| Conflict Resolution Rate | ✓ | N/A |
| Justification Specificity | ✓ | ✓ (extracted from chat) |
| Backtracking Rate | ✓ | ✓ (detected via NL analysis) |
| Consensus Genuineness | ✓ | ✓ (CONSENSUS: tag presence) |

---

## 5. How This Demonstrates Our Contribution

The comparison isolates three separable advantages:

1. **Baseline A vs. v2** → Isolates the value of **structured coordination**.
   Hypothesis: v2 converges faster (fewer rounds), produces better plans
   (higher priority-weighted utilization), and uses fewer tokens, because
   structured mutations are explicit, non-overlapping, and resolved
   deterministically.

2. **Baseline B vs. v2** → Isolates the value of **iterative deliberation**.
   Hypothesis: v2 outperforms single-shot because agents can respond to
   each other's proposals and refine the plan across rounds.

3. **Baseline C vs. v2** → Isolates the value of **the entire negotiation
   layer** over pure recommendation. Hypothesis: v2 outperforms because
   agents surface domain-specific constraints the recommender misses.

4. **Level 2 (equal-token budget)** → Isolates **efficiency**. Hypothesis:
   v2 achieves higher quality at equal token budget because structured
   mutations are compact while free-form chat consumes tokens on social
   niceties, repetition, and coordination overhead.

---

## 6. Edge Cases & Failure Modes

| Scenario | v2 Behavior | Baseline A Behavior | Comparison |
|----------|-------------|---------------------|------------|
| All agents agree | Converges in 1 round; all `done=True` | May still chat for multiple rounds (no explicit done signal) | v2 saves tokens |
| Severe conflict | Stage 2 LLM resolves or forced consensus at max_rounds | Agents may argue indefinitely; convergence check may fail | v2 guarantees termination |
| Adversarial agent | Stage 1 rejects most adversarial mutations (low support_ratio) | Adversarial agent can derail chat; no structural guard | v2 is more robust |
| Empty initial list | v2 bootstraps from agent proposals via ADD mutations | Agents propose items in chat; extraction synthesizes | Comparable |

---

## 7. Implementation Notes

### What needs building (for Phase 2):

1. **`src/platform/testing/baseline_freeforall.py`** — Baseline A protocol
   - Multi-agent chat loop with round-robin ordering
   - Consensus detection evaluator LLM
   - Transcript-to-plan extraction

2. **`src/platform/testing/baseline_singleshot.py`** — Baseline B protocol
   - Independent agent proposals
   - Synthesis LLM prompt

3. **`src/platform/testing/baseline_runner.py`** — Unified runner
   - Runs scenario against any baseline + v2
   - Collects all metrics
   - Outputs comparison CSV

### Equal-budget tracking:
```python
class TokenBudget:
    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    def consume(self, tokens: int) -> bool:
        """Returns False when budget exhausted."""
        self.used += tokens
        return self.used <= self.limit

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)
```

Each LLM call deducts from the budget. When budget is exhausted:
- v2: stops at current round, applies forced consensus
- Baseline A: chat is cut, plan extracted from partial transcript
- Baseline B: single call — budget exhaustion means the synthesis call fails (rare, since individual proposals are limited)
