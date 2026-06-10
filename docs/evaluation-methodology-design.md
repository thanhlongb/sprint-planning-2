# HAiSP Evaluation Methodology — Design Document

**Version:** 2.0 (self-contained)
**Date:** 2026-06-10
**Project:** HAiSP — Sprint Planning for Human-AI Agile Teams
**Status:** Ready for Review
**Authors:** Hoa + research team

---

## 1. Problem Statement and Motivation

The HAiSP platform is a **coordination layer** that orchestrates round-robin
negotiation among LLM agents using a mutation algebra
(ADD / REMOVE / SWAP / REORDER / RESCOPE) with a hybrid deterministic+LLM
aggregation mechanism. Agents communicate through structured mutation envelopes and
natural-language justifications — the platform sees only this surface output, never
agent internals (reasoning traces, token logprobs, model-specific parameters).

Evaluating this opaque-coordination platform raises two fundamental tensions:

**Tension 1 — The Round-Limit Deadlock.** Giving both our algorithm and a baseline
the same hard `max_rounds = N` collapses convergence speed to a constant. If both
stop at N, the metric is uninformative. Yet removing the cap entirely risks
unbounded cost for unstructured baselines.

**Tension 2 — Qualitative Justification Quality.** Agents produce natural-language
justifications ("MFA is a blocking dependency for the compliance milestone…").
Evaluating whether one set of justifications reflects better deliberation than
another requires judging argument quality — a task that current automated metrics
handle poorly and for which no existing multi-agent benchmark provides ground truth.

These tensions sit inside a broader gap: no existing benchmark (Jurkovic, 2025
survey of 32 papers) evaluates a coordination platform that is (a) agent-internals-
agnostic, (b) compares structured negotiation against unstructured free-for-all
deliberation at equal resource budget, and (c) measures the quality of NL
justifications produced during coordination. This document defines an evaluation
methodology that fills that gap.

---

## 2. Baseline and Target Algorithm

### 2.1 Target Algorithm: HAiSP v2 Platform

Structured round-robin negotiation with the full mutation algebra. Each round:
1. Agents propose mutations (ADD / REMOVE / SWAP / REORDER / RESCOPE) with NL
   justifications. Each agent sees the current sprint list, the backlog, and the
   previous round's mutations.
2. **Stage 1 — Deterministic aggregation** resolves non-conflicting mutations
   automatically (e.g., two agents ADD different items, both are accepted; two
   agents propose conflicting mutations on the same item, both are queued).
3. **Stage 2 — LLM refinement** resolves remaining conflicts and applies
   non-conflicting mutations with additional synthesis reasoning.

Agents signal `done=True` when satisfied with the current plan.

### 2.2 Primary Baseline: Unstructured Free-for-All (Baseline A)

Agents communicate via natural language only in a shared chat channel — **no**
structured mutations, **no** round-robin ordering enforcement, **no** deterministic
aggregation algorithm. A final LLM call extracts the sprint plan from the full
transcript. This represents the state of the art *before* structured coordination.

**What this isolates:** the value of the mutation algebra + structured negotiation
format. If HAiSP v2 produces better plans, it is because structured mutations
eliminate ambiguity and the deterministic aggregation reduces coordination overhead.

Two secondary baselines round out the ablation:

- **Baseline B (Single-Shot Synthesis):** Each agent independently proposes their
  ideal sprint plan with no interaction. A single LLM call synthesizes all proposals
  into one plan. Isolates the value of *iterative deliberation*.
- **Baseline C (Recommender-Only):** The existing v1 recommender with no agent
  discussion layer. Isolates the value of the *entire negotiation layer*.

### 2.3 Control Variables

All approaches share: identical backlog scenarios, identical agent role definitions,
identical LLM model (DeepSeek V3, temperature = 0 for Phase 2 reproducibility),
identical initial sprint list A₀, and identical round-robin turn ordering (for
Baseline A and v2). The only thing that varies is the *coordination mechanism*.

---

## 3. Evaluation Metrics and Measurement Procedures

### 3.1 Output Quality (the Sprint Plan)

All metrics are computed from the final sprint plan A′ — they are baseline-agnostic
and deterministic.

| Metric | Definition | Range |
|--------|-----------|-------|
| **Priority-Weighted Utilization** (M_PWU) | Σ(priority_weight × SP) / capacity | [0, ~1.0], ↑ |
| **Goal Alignment** (M_GOAL) | Cosine similarity between sprint goal embedding and mean item embedding | [0, 1], ↑ |
| **Role Balance** (M_ROLE) | 1 − (max_role_share − min_role_share) | [0, 1], ↑ |
| **Dependency Satisfaction** (M_DEPS) | Fraction of planned items whose dependencies are also in the plan | [0, 1], ↑ |
| **Capacity Efficiency** (M_CAPE) | 1 − \|actual_SP − target_SP\| / target_SP | [0, 1], ↑ |

**Measurement:** M_PWU uses priority weights (HIGH = 3, MEDIUM = 2, LOW = 1).
M_GOAL uses a pinned sentence-transformer model (`all-MiniLM-L6-v2`). M_ROLE maps
item labels to role categories (FRONTEND / BACKEND / QA). All are deterministic and
require clean backlog data only.

### 3.2 Process Quality (the Deliberation)

| Metric | Definition | Range |
|--------|-----------|-------|
| **Rounds to Convergence** (M_RCONV) | Round number where convergence criteria are first met | [1, max_rounds], ↓ |
| **Token Efficiency** (M_TEF) | M_PWU / (total_tokens / 1000) | [0, ∞), ↑ |
| **Consensus Genuineness** (M_CNVG) | Fraction of agents signaling `done=True` at convergence | [0, 1], ↑ |
| **Backtracking Rate** (M_UNDO) | Fraction of agents who REMOVE an item they previously ADDed | [0, 1], ↓ |
| **Mutation Acceptance Rate** | \|applied_mutations\| / \|proposed_mutations\| | [0, 1], ↑ |

**Measurement:** For HAiSP v2, convergence is deterministic: all agents `done=True`
for 2 consecutive rounds AND zero mutations applied in the second round. For
Baseline A, a separate LLM judge (temperature = 0) determines from the transcript
whether all agents have expressed satisfaction and no new proposals have emerged for
2 consecutive turns. Token counts use provider-reported token counts (input +
output), excluding evaluation-overhead calls.

### 3.3 Justification Quality (the Rationale) — Three-Level Hierarchy

This is the core qualitative dimension. We use a three-level approach from cheap to
expensive, following established LLM-as-judge methodology (Liu et al., G-Eval, 2023).

**Level 1 — Lexical Specificity (deterministic, free).** Score each justification by
four binary surface features, each worth 0.25:

- References specific item attributes (SP, priority, labels)
- References capacity or sprint goal
- References dependency chains or other items
- Cites evidence (past sprint data, velocity, known constraints)

Total ∈ {0, 0.25, 0.50, 0.75, 1.0}. Implemented via regex heuristics calibrated
against a held-out set of 50 justifications.

**Level 2 — LLM-as-Judge (semi-automated, ~$0.01/session).** A separate evaluator
LLM (same model family as experiment agents, temperature = 0) rates each
justification on three axes:

- **Relevance** (1–5): Does the justification support the proposed mutation?
- **Factual Grounding** (1–5): Does it reference verifiable item/sprint attributes?
- **Persuasiveness** (1–5): Would a reasonable product owner find it compelling?

Composite = mean of three scores. Inter-judge reliability: run evaluator twice
(temperature = 0.7), compute Pearson r (target > 0.7). A composite M_JQUAL ∈ [0, 1]
weights Level 1 and the three Level 2 axes equally.

**Level 3 — Human Expert Rating (manual, $50/session).** Human participants (HREC
H2026-0234, N ≈ 12) rate justifications they receive during live sessions on the
same three axes. This serves as ground-truth calibration for Level 2.

### 3.4 Cost and Robustness

CLEAR-framework (Mehta, 2025) resource metrics: total token consumption, cost per
converged plan, and wall-clock latency. Robustness is stress-tested via adversarial
resilience (one agent proposes bad-faith mutations), cold-start quality (empty
initial sprint list), and scaling behavior (2, 3, 5, 8 agents).

---

## 4. Experimental Protocol

### 4.1 Resolving the Round-Limit Deadlock

The core design decision: **all approaches share uniform convergence criteria, not
uniform round counts.** Every approach runs until natural convergence, with a
generous safety-net `max_rounds = 10` that should never be hit by a well-functioning
system. This gives us a dual-level comparison:

- **Level 1 — Convergence Quality (primary):** Both HAiSP v2 and Baseline A run
  until convergence (no token cap). Compare rounds-to-convergence, output quality at
  convergence, and total tokens consumed (secondary). This answers: "Given freedom
  to run, which produces better plans?"

- **Level 2 — Equal-Budget Quality (secondary):** Fix a token budget B equal to
  HAiSP v2's upper 95% CI token consumption across all Phase 2 scenarios. Run both
  systems and stop at budget exhaustion. Compare output quality at budget exhaustion.
  This answers: "Given the same compute, which produces better plans?"

If Baseline A hits `max_rounds = 10` without converging, the run is recorded with
`forced_convergence = true` and the plan is extracted from the partial transcript.
This becomes a data point *against* Baseline A.

### 4.2 Three-Phase Evaluation

**Phase 1 — Synthetic Scenarios (CI, deterministic, < 1s/scenario).** 8 predefined
backlog scenarios with manually constructed ground-truth Pareto-optimal sprint plans.
Mock agents use deterministic persona-specific scoring (temperature = 0). No real
LLM calls. Tests Baselines B and C against v2 (Baseline A is not meaningful with
deterministic agents). Collects all output-quality and process-quality metrics.

**Phase 2 — LLM Agent Scenarios (semi-deterministic, ~30s/scenario).** Same 8
scenarios with real LLM agents (DeepSeek V3, temperature = 0). **3 independent runs
per scenario** to measure variance (24 paired observations per algorithm). Tests all
three baselines (A, B, C) against v2. Collects all output, process, justification
(Levels 1 and 2), cost, and robustness metrics. Interleaved execution to control for
time-of-day API latency variance.

**Phase 3 — Human-in-the-Loop (qualitative, N ≈ 12 participants).** Per HREC
H2026-0234 protocol. Human participants join HAiSP sessions alongside LLM agents.
Post-session questionnaire captures perceived fairness, satisfaction, trust, and
qualitative feedback. Human ratings serve as Level 3 calibration for automated
justification quality metrics.

### 4.3 Sample Size and Statistical Plan

**Primary hypothesis (H1):** HAiSP v2 produces sprint plans with higher M_PWU than
Baseline A at equal token budget, across 8 scenarios × 3 replicates = 24 paired
observations. Paired t-test (or Wilcoxon signed-rank if non-normal), α = 0.05.

**Secondary hypotheses:** H2 — v2 converges in fewer rounds (Mann-Whitney U on
M_RCONV); H3 — v2 produces higher M_LEX scores (paired t-test); H4 — v2 degrades
less under adversarial behavior (two-way ANOVA: algorithm × scenario type). Effect
sizes as Cohen's d (t-tests) and Cliff's delta (Mann-Whitney).

---

## 5. Limitations

1. **Synthetic backlog scope.** All 8 scenarios are drawn from a single synthetic
   backlog. Real-world sprint planning involves diverse backlogs with different
   dependency densities, priority distributions, and labeling schemes. Generalization
   to production backlogs requires cross-project validation, which Phase 3 begins to
   address but does not fully cover.

2. **LLM-as-judge reliability.** Level 2 justification quality ratings inherit the
   biases of the judge LLM (position bias, verbosity bias, self-enhancement bias).
   While inter-judge reliability checks and human calibration (Level 3) mitigate
   this, they do not eliminate it. The composite M_JQUAL should be interpreted as a
   proxy, not a definitive measure of argument quality.

3. **Single model family.** Phase 2 uses only DeepSeek V3. Agent behavior and
   justification quality almost certainly vary across model families (GPT-4, Claude,
   Llama). The results may not generalize to other LLM backends without additional
   cross-model experiments.

4. **Convergence criteria asymmetry.** HAiSP v2 convergence is deterministic
   (structured `done=True` fields), while Baseline A convergence requires LLM judge
   interpretation of NL transcripts. The LLM judge may be more conservative or
   liberal than the deterministic criteria, introducing a measurement artifact that
   favors one side. Sensitivity analysis with varied judge prompts is recommended.

5. **No human-only baseline.** The current design compares HAiSP v2 against other
   AI configurations but does not include human-only sprint planning sessions as a
   "gold standard" upper bound. This makes it impossible to calibrate how close
   either AI approach comes to expert human performance.

6. **Small N for Phase 3.** N ≈ 12 human participants is adequate for qualitative
   calibration but insufficient for statistical comparisons between v2 and any
   human-only condition. Phase 3 is best interpreted as validation and insight
   generation, not hypothesis testing.

7. **Round-robin ordering as a confound.** Both v2 and Baseline A use the same
   round-robin turn order. Turn order may affect deliberation outcomes (first-mover
   advantage, anchoring effects). The current design controls for it but does not
   measure its effect. Randomizing turn order across replicates would strengthen the
   design.

---

## References

1. Zhu, K. et al. (2025). "MultiAgentBench: Evaluating the Collaboration and
   Competition of LLM Agents." *ACL 2025*. arXiv:2503.01935.
2. Mehta, S. (2025). "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating
   Enterprise Agentic AI Systems (CLEAR)." arXiv:2511.14136.
3. Liu, Y. et al. (2023). "G-Eval: NLG Evaluation using GPT-4 with Better Human
   Alignment." *EMNLP 2023*.
4. Jurkovic, N. (2025). "Survey of Multi-agent LLM Evaluations." LessWrong.
5. Chan, C.-M. et al. (2024). "ChatEval: Towards Better LLM-based Evaluators
   through Multi-Agent Debate." *ICLR 2024*.
6. UCSB-AI Lab. "LLM-Coordination Benchmark." *NAACL 2025*.
