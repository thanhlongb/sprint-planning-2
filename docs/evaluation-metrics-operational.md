# Evaluation Metrics for Qualitative Justifications — Operational Specification

**Version:** 2.0
**Date:** 2026-06-10
**Project:** HAiSP — Sprint Planning with Human-AI Agents
**Supersedes:** `evaluation-metrics.md` (v1), partially incorporates `evaluation-methodology-design.md`
**Purpose:** Single-source-of-truth operational definition for every metric in the ICSE
evaluation, structured so a developer can implement, an annotator can apply, and a reviewer
can reproduce.

---

Each metric entry follows a uniform schema:

| Field | Meaning |
|-------|---------|
| **Category** | One of the 5 task dimensions |
| **Mnemonic** | Short code for use in CSV/reports |
| **Definition** | One-sentence plain-English definition |
| **Formula** | Exact computation (pseudocode where needed) |
| **Range & Direction** | [min, max]; ↑ = better, ↓ = better, or ↔ = target |
| **Measurement Protocol** | Data source, extraction point, sampling, tools |
| **Annotator Requirements** | Who/what computes it, expertise, calibration |
| **Aggregation Method** | How to combine across N runs × M scenarios |
| **Application: Baseline** | How this metric evaluates Baselines A/B/C |
| **Application: HAiSP v2** | How this metric evaluates our algorithm |

---

## 1. Convergence Speed (Category 1)

### 1.1 M_RCONV — Rounds to Convergence

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_RCONV` |
| **Definition** | Number of discussion rounds until all convergence criteria are first satisfied. |
| **Formula** | ```r_conv = min(r) where convergence(r) == True, else max_rounds``` |
| **Range & Direction** | [1, max_rounds]; ↓ is better |
| **Measurement Protocol** | After each round, evaluate convergence criteria (see below). Record first round number where all criteria are met. If max_rounds is hit first, record max_rounds with a `forced=True` flag. Source: the round-robin loop log in `phase_orchestrator.py` (or transcript parser for Baseline A). |
| **Annotator Requirements** | **Deterministic** for v2 (all-agents-done + zero-mutations-applied). **LLM-as-judge** for Baseline A (rate transcript for "all agents expressed satisfaction and no new proposals in last 2 turns"). LLM judge: temperature=0, same model family as experiment agents, run twice for inter-judge reliability (Pearson r). |
| **Aggregation Method** | Per-scenario: mean RCONV across 3 independent runs. Cross-scenario: report mean ± std, plus a histogram (how many scenarios converge at r=1, 2, 3, ...). Also report `p_forced` = fraction of runs where convergence was forced (max_rounds hit). |
| **Application: Baseline** | Baseline A: LLM-judge convergence detection on transcript. Baseline B: always 1 (single-shot). Baseline C: always 0 (no negotiation). |
| **Application: HAiSP v2** | Deterministic: all agents `done=True` for 2 consecutive rounds AND zero mutations applied in the second of those rounds. |

#### Convergence Criteria

```
convergence(session_state, round_number):
    for v2:
        return (all_agents_done_for_N_consecutive(2)
                AND zero_mutations_applied_in_round(round_number))
    for baseline_A:
        return (llm_judge_rate(transcript)
                == "all agents satisfied, no new proposals in last 2 turns")
    for baseline_B:
        return True  # single-shot by definition
```

### 1.2 M_CNVG — Convergence Certainty

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_CNVG` |
| **Definition** | Fraction of agents that explicitly signal `done=True` at convergence. |
| **Formula** | ```cnvg = |{agent: signal_done(agent) == True}| / N_agents``` |
| **Range & Direction** | [0, 1]; ↑ is better (1.0 = genuine consensus) |
| **Measurement Protocol** | Extract `done` fields from the final round's turn responses. For Baseline A: LLM judge determines per-agent satisfaction from transcript. |
| **Annotator Requirements** | **Deterministic** for v2 (structured `done` field). **LLM-as-judge** for Baseline A (per-agent satisfaction from transcript; same judge config as M_RCONV). |
| **Aggregation Method** | Per-scenario: mean CNVG across 3 runs (continuous). Cross-scenario: mean ± std. Also report `p_genuine` = fraction of runs where CNVG = 1.0. |
| **Application: Baseline** | Baseline A: LLM extracts per-agent "satisfied" signal. Baseline B: 1.0 (all agents propose, no disagreement path). Baseline C: N/A. |
| **Application: HAiSP v2** | Structured `done` field from each agent response. |

---

## 2. Solution Quality (Category 2)

### 2.1 M_PWU — Priority-Weighted Utilization

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_PWU` |
| **Definition** | Total priority-weighted story points in the final sprint plan, normalized by capacity. |
| **Formula** | ```pwu = Σ(priority_weight(i) × story_points(i)) / capacity``` where ```priority_weight(HIGH)=3, MEDIUM=2, LOW=1``` |
| **Range & Direction** | [0, ∼3.0] in theory, typically [0.3, 1.0] in practice; ↑ is better |
| **Measurement Protocol** | Extract final sprint list A' (item IDs). Look up each item in the backlog for priority and story_points. Sum weighted SP, divide by capacity (total SP budget). Logging point: after Stage 2 aggregation produces A', before returning to caller. |
| **Annotator Requirements** | **Deterministic** — no human or LLM needed. Backlog fields must be clean (non-null priority, integer SP). |
| **Aggregation Method** | Per-scenario: mean PWU across 3 runs, ranked against ground-truth PWU (report Δpwu = PWU_actual − PWU_optimal). Cross-scenario: mean Δpwu ± std. Wilcoxon signed-rank across 24 paired observations (8 scenarios × 3 runs) comparing v2 vs Baseline A. |
| **Application: Baseline** | All baselines produce a final sprint list → same computation. Baseline A extraction: LLM parses transcript to extract final sprint plan. |
| **Application: HAiSP v2** | Final sprint list A' from stage 2 aggregation output. |

### 2.2 M_GOAL — Goal Alignment

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_GOAL` |
| **Definition** | Cosine similarity between the sprint goal embedding and the mean embedding of items in the final sprint plan. |
| **Formula** | ```goal = cosine(embed(sprint_goal_text), mean([embed(item.title + " " + item.description) for item in A']))``` |
| **Range & Direction** | [−1, 1]; ↑ is better (higher similarity = more aligned) |
| **Measurement Protocol** | Embed sprint goal text and all item title+description strings using a fixed sentence-transformer model (`all-MiniLM-L6-v2`, 384-dim). Compute cosine similarity. This is deterministic given the same embedding model — pin the model version. |
| **Annotator Requirements** | **Deterministic** — automated via sentence-transformers. No human or LLM needed. Embedding model must be pinned (e.g., `sentence-transformers/all-MiniLM-L6-v2`). |
| **Aggregation Method** | Per-scenario: mean GOAL across 3 runs. Cross-scenario: mean ± std. Note that absolute GOAL values are scenario-dependent (different goal texts) — primary comparison is ΔGOAL between v2 and baseline within the same scenario. |
| **Application: Baseline** | All baselines have a final sprint plan and sprint goal → same computation. |
| **Application: HAiSP v2** | Same. |

### 2.3 M_ROLE — Role Balance

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_ROLE` |
| **Definition** | How evenly the sprint plan serves each agent role, measured as 1 minus the spread between maximum and minimum role share. |
| **Formula** | ```role_balance = 1 − (max(role_shares) − min(role_shares))``` where ```role_share(r) = Σ(item_sp for items whose labels ∩ role_labels(r) ≠ ∅) / Σ(all item_sp)```. Role labels: FRONTEND={ui,frontend,ux,design,css,component,responsive,accessibility,animation,style}, BACKEND={backend,api,database,data,server,auth,security,performance,infra,scaling,integration}, QA={testing,qa,e2e,integration-test,unit-test,bug,tech-debt,regression,coverage}. |
| **Range & Direction** | [0, 1]; ↑ is better (1.0 = all roles equally served) |
| **Measurement Protocol** | Post-synthesis. For each role, sum SP of items whose labels intersect that role's label set. Compute shares. A plan that assigns all SP to one role's items gets role_balance = 0. A balanced plan gets close to 1. |
| **Annotator Requirements** | **Deterministic** — label sets are fixed, SP are integers. No annotator needed. |
| **Aggregation Method** | Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. |
| **Application: Baseline** | Same computation on any final sprint list. |
| **Application: HAiSP v2** | Same. This metric directly tests whether structured multi-role negotiation produces more balanced plans than single-shot synthesis or recommender-only. |

### 2.4 M_DEPS — Dependency Satisfaction

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_DEPS` |
| **Definition** | Fraction of items in the final sprint plan whose declared dependencies are also present in the plan or already completed. |
| **Formula** | ```deps = |{i ∈ A': all(dep ∈ A' or dep_is_completed(dep) for dep in deps(i))}| / |A'|``` |
| **Range & Direction** | [0, 1]; ↑ is better (1.0 = no dangling dependencies) |
| **Measurement Protocol** | Post-synthesis, before returning. For each item i in A', iterate its `dependencies` field. Check if each dep.id is either in A' or marked completed in the session state. Compute fraction. |
| **Annotator Requirements** | **Deterministic** — requires clean `dependencies` field in backlog items. If dependencies are sparse or empty (common in real backlogs), report M_DEPS separately for items that HAVE dependencies vs all items. |
| **Aggregation Method** | Two variants: `M_DEPS_all` (all items, treating no-deps items as trivially satisfied) and `M_DEPS_linked` (only items with non-empty deps). Report both. Cross-scenario: mean ± std. |
| **Application: Baseline** | Same computation. Baseline A requires LLM to also extract dependencies from transcript. |
| **Application: HAiSP v2** | Same. The hypothesis is that structured ADD/REMOVE with dependency-aware justifications produces plans with fewer dangling deps. |

### 2.5 M_CAPE — Capacity Efficiency

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_CAPE` |
| **Definition** | How close the final sprint plan is to the target utilization (default 85% of capacity). |
| **Formula** | ```cape = 1 − |actual_SP − target_SP| / target_SP``` where ```target_SP = capacity × 0.85```, clamped to [0, 1]. |
| **Range & Direction** | [0, 1]; ↑ is better (1.0 = exactly hits target utilization) |
| **Measurement Protocol** | Sum SP of all items in A'. Compute deviation from target. |
| **Annotator Requirements** | **Deterministic** — integer arithmetic. |
| **Aggregation Method** | Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. |
| **Application: Baseline** | Same. Baseline A may over-fill or under-fill since no structured capacity enforcement. |
| **Application: HAiSP v2** | Stage 2 aggregation enforces capacity — this metric verifies the enforcement works. |

### 2.6 M_PAR — Pareto Score

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_PAR` |
| **Definition** | Fraction of intermediate sprint-list snapshots (from all rounds) that are dominated by the final plan. |
| **Formula** | ```par = |{h ∈ history: dominates(A', h)}| / |history|``` where ```dominates(a,b) = value(a) ≥ value(b) ∧ SP(a) ≤ SP(b)```. Value(item) = priority_score + log₂(SP+1). |
| **Range & Direction** | [0, 1]; ↑ is better (1.0 = monotonic improvement) |
| **Measurement Protocol** | After convergence, iterate all round-history snapshots. For each, check if final A' dominates it (≥ value, ≤ SP). Requires saving each round's intermediate sprint list. |
| **Annotator Requirements** | **Deterministic** — automated from round history. |
| **Aggregation Method** | Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. |
| **Application: Baseline** | Baseline A: save each transcript-round's extracted sprint plan. Baseline B: 1.0 (no intermediates). Baseline C: 1.0. |
| **Application: HAiSP v2** | Each round produces an intermediate A via Stage 1 aggregation. The hypothesis is v2 achieves monotonic improvement; regressions indicate aggregation failures. |

### 2.7 M_COV — Coverage

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_COV` |
| **Definition** | Jaccard similarity between final plan item IDs and the union of all item IDs ever proposed by any agent. |
| **Formula** | ```cov = |A'_ids ∩ all_proposed_ids| / |all_proposed_ids|```. Empty all_proposed → 1.0. |
| **Range & Direction** | [0, 1]; ↔ contextual (high = agents heard; but 1.0 on a bloated plan is bad. Interpret alongside M_CAPE.) |
| **Measurement Protocol** | Collect all `add_item` proposals across all rounds from all agents. Compute union of item IDs. Compute Jaccard vs final plan. |
| **Annotator Requirements** | **Deterministic** — set operations on item IDs. |
| **Aggregation Method** | Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. Report jointly with M_CAPE (coverage-efficiency trade-off). |
| **Application: Baseline** | Baseline A: extract proposed items from transcript. Baseline B: union of all independent proposals vs synthesized plan. Baseline C: 1.0 (no agent proposals, trivially covered). |
| **Application: HAiSP v2** | Aggregated from structured mutation history. |

### 2.8 M_STAB — Stability

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_STAB` |
| **Definition** | Jaccard similarity between the final sprint plan and the plan produced by running one additional negotiation round after convergence. |
| **Formula** | ```stab = |A'_ids ∩ A'_plus_one_ids| / |A'_ids ∪ A'_plus_one_ids|``` |
| **Range & Direction** | [0, 1]; ↑ is better (1.0 = fixed point) |
| **Measurement Protocol** | After convergence, run exactly one more round with all agents instructed `done=True` (they should not propose new mutations). If any agent proposes changes anyway, apply them and compare. Source: stability check appended to each scenario run. |
| **Annotator Requirements** | **Deterministic** — Jaccard on item ID sets. |
| **Aggregation Method** | Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. |
| **Application: Baseline** | Baseline A: run one more transcript turn. Baseline B: re-run synthesis with same inputs (should be 1.0 if deterministic). Baseline C: 1.0 (deterministic). |
| **Application: HAiSP v2** | Tests whether convergence is a genuine fixed point or artifacts of the round structure. |

---

## 3. Consistency Among Agents (Category 3)

### 3.1 M_CONS — Inter-Agent Agreement

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_CONS` |
| **Definition** | Mean pairwise Jaccard similarity between agents' proposed ADD item sets in the final round. |
| **Formula** | ```cons = mean(Jaccard(adds_i, adds_j) for all i≠j)```. If no ADD proposals → 1.0 (implicit agreement on existing plan). |
| **Range & Direction** | [0, 1]; ↑ is better (high agreement = agents converged on same items) |
| **Measurement Protocol** | For each agent in the final round, extract the set of item IDs they proposed ADD on. Compute all-pairs Jaccard, take mean. |
| **Annotator Requirements** | **Deterministic** for v2 (structured ADD mutations). **LLM-extraction** for Baseline A (extract per-agent item proposals from final transcript turn). |
| **Aggregation Method** | Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. Also report `Fleiss' κ` for categorical agreement (ADD/REMOVE/KEEP per item across agents). |
| **Application: Baseline** | Baseline A: extract from transcript. Baseline B: compare independent proposals. Baseline C: no agents → 1.0. |
| **Application: HAiSP v2** | Direct from structured mutation sets. Hypothesis: structured negotiation increases inter-agent agreement across rounds. |

### 3.2 M_AGREE — Agreement Progression

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_AGREE` |
| **Definition** | Slope of inter-agent agreement (M_CONS) across rounds — does agreement increase monotonically? |
| **Formula** | Fit OLS regression: `M_CONS(r) ~ β₀ + β₁ × r`. Report β₁ (slope). Also report Spearman ρ between round number and M_CONS. |
| **Range & Direction** | β₁ ∈ ℝ, ρ ∈ [−1, 1]; β₁ > 0 and ρ > 0.5 = agreement improves over time (desirable) |
| **Measurement Protocol** | Compute M_CONS for each round 1..R_convergence. Fit linear trend. |
| **Annotator Requirements** | **Deterministic** — computed from M_CONS time series. |
| **Aggregation Method** | Per-scenario: mean β₁ and mean ρ across 3 runs. Cross-scenario: mean ± std of both. |
| **Application: Baseline** | Baseline A: compute from transcript rounds. Baseline B: only 1 round → cannot compute. Baseline C: N/A. |
| **Application: HAiSP v2** | Tests whether structured negotiation causes genuine convergence of preferences, not just exhaustion. |

### 3.3 M_UNDO — Backtracking Rate

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_UNDO` |
| **Definition** | Fraction of agents who propose REMOVE on an item they themselves previously proposed ADD on. |
| **Formula** | ```undo = |{a: ∃i ∈ REMOVES(a, final_round) ∩ ADDS(a, any_prior_round)}| / N_agents``` |
| **Range & Direction** | [0, 1]; ↓ is better (less backtracking = more deliberative consensus) |
| **Measurement Protocol** | Track per-agent mutation history across rounds. In final round, check if any REMOVE targets were previously ADDed by the same agent. |
| **Annotator Requirements** | **Deterministic** — mutation history tracking. |
| **Aggregation Method** | Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. |
| **Application: Baseline** | Baseline A: LLM-extract agent-specific proposals from transcript rounds. More difficult for free-form chat. Baseline B: single round → 0. |
| **Application: HAiSP v2** | Tracks whether agents "change their mind" — high backtracking suggests the earlier consensus was spurious. |

### 3.4 M_SAT — Consensus Genuineness

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_SAT` |
| **Definition** | Fraction of agents signaling `done=True` at convergence (same formula as M_CNVG, but interpreted as satisfaction quality, not convergence detection). |
| **Formula** | Same as M_CNVG. |
| **Range & Direction** | [0, 1]; ↑ is better (1.0 = genuine, <1.0 = forced/overridden) |
| **Measurement Protocol** | Same as M_CNVG. |
| **Annotator Requirements** | Same as M_CNVG. |
| **Aggregation Method** | Same as M_CNVG. These two metrics share a data source but answer different questions: M_CNVG = "did we converge?" M_SAT = "were agents happy about it?" For Baseline A, they diverge (LLM-judge may detect convergence without per-agent satisfaction). |
| **Application: Baseline** | Baseline A: LLM-judge per-agent satisfaction. Baseline B: 1.0. Baseline C: N/A. |
| **Application: HAiSP v2** | Structured `done` fields. |

---

## 4. Resource Efficiency (Category 4)

### 4.1 M_TOK — Total Token Consumption

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_TOK` |
| **Definition** | Total tokens consumed across all LLM calls during a session (agents + aggregation + evaluation). |
| **Formula** | ```tok = Σ tok(model_call) for all calls in session``` (input + output tokens) |
| **Range & Direction** | ℝ⁺; ↓ is better |
| **Measurement Protocol** | Instrument the LLM client to log `(model, input_tokens, output_tokens)` for every call. Sum across: agent turn responses, aggregation Stage 2 LLM calls, convergence judge calls. Exclude evaluation-only LLM calls (justification evaluator, transcript parser for baseline extraction) — those are measurement overhead, not algorithm cost. |
| **Annotator Requirements** | **Deterministic** — depends on LLM provider token counting. Use provider-reported token counts when available; fall back to `tiktoken` estimation for the agent model family. |
| **Aggregation Method** | Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. Also report breakdown: agent_tokens vs aggregation_tokens. |
| **Application: Baseline** | Baseline A: full transcript tokens + final extraction call. Expected to be 2–5× v2 due to unconstrained chat. Baseline B: N independent proposals + 1 synthesis call. Baseline C: 1 recommender call. |
| **Application: HAiSP v2** | N × R × (turn_prompt + response) + R × aggregation_stage2 + 1 × convergence_judge. Structured mutation envelopes keep prompts short. |

### 4.2 M_TEF — Token Efficiency

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_TEF` |
| **Definition** | Priority-weighted utilization per thousand tokens consumed. |
| **Formula** | ```tef = (M_PWU / (M_TOK / 1000))```. Higher = more output quality per unit of compute. |
| **Range & Direction** | ℝ⁺; ↑ is better |
| **Measurement Protocol** | Divide M_PWU by M_TOK/1000. Both source metrics must be from the same run. |
| **Annotator Requirements** | **Deterministic** — composite of two deterministic metrics. |
| **Aggregation Method** | Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. This is the primary efficiency comparison metric — it answers "does v2 achieve equal or better quality with fewer tokens?" |
| **Application: Baseline** | Same formula. Baseline A expected to have low TEF (many tokens, variable quality). Baseline B moderate. Baseline C highest TEF (fewest tokens) but likely lower M_PWU. |
| **Application: HAiSP v2** | Key metric. The paper's primary comparison constrains token budget to be equal across conditions — TEF normalizes this. |

### 4.3 M_LAT — End-to-End Latency

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_LAT` |
| **Definition** | Wall-clock time from session start to convergence (or max_rounds timeout). |
| **Formula** | ```lat = t_convergence − t_session_start``` (seconds) |
| **Range & Direction** | ℝ⁺; ↓ is better |
| **Measurement Protocol** | Record `time.time()` at session start and at convergence detection. Excludes scenario setup and metric computation time. For parallel LLM calls, wall-clock is measured, not sum-of-call-times. |
| **Annotator Requirements** | **Deterministic** — wall-clock measurement. Requires controlling for: model provider latency variance, rate limiting. Run all conditions interleaved (not all v2 then all baseline) to avoid time-of-day bias. |
| **Aggregation Method** | Per-scenario: median across 3 runs (median better than mean for latency — resistant to outlier slow runs). Cross-scenario: median ± IQR. |
| **Application: Baseline** | Baseline A: end-to-end chat transcript generation + extraction. Baseline B: parallel proposal generation + synthesis. Baseline C: single recommender call. |
| **Application: HAiSP v2** | Sequential round-robin turns naturally add latency. Report alongside M_TOK and M_TEF to show the trade-off. |

### 4.4 M_RPROD — Round Productivity

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_RPROD` |
| **Definition** | Number of mutations applied per round — measures how much "work" each round accomplishes. |
| **Formula** | ```rprod = |applied_mutations| / rounds_to_convergence```. Applied mutations = Stage 1 accepted mutations + Stage 2 refined mutations. |
| **Range & Direction** | ℝ⁺; ↑ is better (more work per round = more efficient deliberation) |
| **Measurement Protocol** | Track mutations accepted by the aggregation mechanism each round. Divide by M_RCONV. |
| **Annotator Requirements** | **Deterministic** — aggregation log. |
| **Aggregation Method** | Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. |
| **Application: Baseline** | Baseline A: extract "actionable proposals" per transcript turn via LLM. Less meaningful due to unstructured format. Baseline B: 1 round → all mutations at once. |
| **Application: HAiSP v2** | Direct from mutation history. Hypothesis: v2 has high early-round productivity (agents front-load their strongest proposals), declining in later rounds. |

---

## 5. Explainability Quality (Category 5)

### 5.1 M_LEX — Lexical Specificity Score (Level 1)

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_LEX` |
| **Definition** | Surface-feature score of justification specificity — deterministic, zero-cost proxy for richness. |
| **Formula** | ```lex(j) = 0.25 × [references SP/priority/labels] + 0.25 × [references capacity/sprint_goal] + 0.25 × [references dependencies/other_items] + 0.25 × [references past_data/velocity/constraints]```. Each term is binary (0 or 1). Total ∈ {0, 0.25, 0.50, 0.75, 1.0} |
| **Range & Direction** | [0, 1]; ↑ is better (more specific justifications) |
| **Measurement Protocol** | Run regex heuristics on every justification string: SP/priority → `\b(story.points?|sp|priority|HIGH|MEDIUM|LOW)\b`; capacity/goal → `\b(capacity|budget|sprint.goal|goal)\b`; dependencies → `\b(depends?|block|chain|requires?)\b`; evidence → `\b(velocity|sprint.\d|past|histor|previous)\b`. Each regex match sets the corresponding bit. |
| **Annotator Requirements** | **Deterministic** — regex-based. No annotator needed. Calibrate regex patterns against a held-out set of 50 justifications. |
| **Aggregation Method** | Per-session: mean M_LEX across all justifications in all rounds. Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. Also report M_LEX distribution (histogram of 0, 0.25, ..., 1.0). |
| **Application: Baseline** | Baseline A: extract all agent utterances that propose changes to the sprint plan from transcript. Apply same regex. Baseline B: each agent's independent justification. Baseline C: N/A (no justifications). |
| **Application: HAiSP v2** | Extract `justification` field from every mutation across all rounds. Hypothesis: v2's structured format encourages more specific justifications than free-form chat. |

### 5.2 M_JREL — Justification Relevance (Level 2)

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_JREL` |
| **Definition** | LLM-judge rating (1–5) of how directly each justification supports its corresponding mutation. |
| **Formula** | ```jrel(j, mutation) = llm_judge(j, mutation, "relevance")``` → 1–5 Likert |
| **Range & Direction** | [1, 5]; ↑ is better (5 = perfectly relevant) |
| **Measurement Protocol** | For each (justification, mutation_type, item) triple, call evaluator LLM with prompt: "On a scale of 1–5, how directly does this justification support the proposed {type} on {item_title}? 1=irrelevant, 3=somewhat relevant, 5=directly and exclusively relevant." Temperature=0. Run evaluator twice for inter-judge reliability. |
| **Annotator Requirements** | **LLM-as-judge** — separate evaluator LLM (not same instance as agents). Model: same family as experiment agents (e.g., DeepSeek V3) temperature=0 for reproducibility. Cost: ~$0.003 per justification. Inter-judge reliability: run twice at temperature=0.7, report Pearson r (target > 0.7). If r < 0.7, flag metric as unreliable. |
| **Aggregation Method** | Per-session: mean M_JREL across all justifications. Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. Report inter-judge r. |
| **Application: Baseline** | Baseline A: extract proposal utterances from transcript, pair with extracted mutations. Baseline B: pair each proposal with its justification. |
| **Application: HAiSP v2** | Pair each mutation's `justification` field with its `type` and `target_key`. |

### 5.3 M_JFACT — Justification Factual Grounding (Level 2)

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_JFACT` |
| **Definition** | LLM-judge rating (1–5) of whether the justification references verifiable item/sprint attributes. |
| **Formula** | ```jfact(j, item, sprint_context) = llm_judge(j, item, sprint_context, "factual_grounding")``` → 1–5 |
| **Range & Direction** | [1, 5]; ↑ is better (5 = all claims are verifiable against item data) |
| **Measurement Protocol** | Provide the evaluator LLM with: justification text, item dict (title, description, priority, SP, labels, deps), sprint goal, capacity. Prompt: "On a scale of 1–5, rate whether this justification's factual claims are grounded in the provided item data and sprint context. 1=hallucinated or unsupported, 3=partially grounded, 5=every claim matches provided data." |
| **Annotator Requirements** | **LLM-as-judge** — same config as M_JREL. Inter-judge reliability: target r > 0.7. |
| **Aggregation Method** | Per-session: mean M_JFACT. Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. |
| **Application: Baseline** | Same as M_JREL. Baseline A at risk for hallucinated justifications — M_JFACT should be lower. |
| **Application: HAiSP v2** | Structured item data always available to agents. Hypothesis: v2 justifications are more factually grounded because items are explicitly referenced by ID. |

### 5.4 M_JPER — Justification Persuasiveness (Level 2)

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_JPER` |
| **Definition** | LLM-judge rating (1–5) of whether a reasonable product owner would find the justification compelling. |
| **Formula** | ```jper(j, mutation, item, sprint_context) = llm_judge(j, mutation, item, sprint_context, "persuasiveness")``` → 1–5 |
| **Range & Direction** | [1, 5]; ↑ is better (5 = highly compelling to a product owner) |
| **Measurement Protocol** | Prompt: "You are an experienced product owner. On a scale of 1–5, how compelling is this justification for {mutation_type}ing {item_title}? 1=unconvincing/would reject, 3=reasonable/would consider, 5=highly persuasive/would accept." |
| **Annotator Requirements** | **LLM-as-judge** — same config as M_JREL. This is the most subjective of the three Level 2 axes — inter-judge r expected lower (~0.5–0.6). |
| **Aggregation Method** | Per-session: mean M_JPER. Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. |
| **Application: Baseline** | Same as M_JREL. Comparative analysis: do v2's structured justifications produce more persuasive arguments than free-form chat? |
| **Application: HAiSP v2** | Same — hypothesis is yes due to explicit justification field forcing agents to articulate reasoning. |

### 5.5 M_JQUAL — Composite Justification Quality

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_JQUAL` |
| **Definition** | Weighted composite of all justification quality axes into a single [0, 1] score. |
| **Formula** | ```jqual = 0.25 × M_LEX + 0.25 × (M_JREL/5) + 0.25 × (M_JFACT/5) + 0.25 × (M_JPER/5)``` |
| **Range & Direction** | [0, 1]; ↑ is better |
| **Measurement Protocol** | Compute from the four sub-metrics. Weights are uniform (equal emphasis on specificity, relevance, factual grounding, persuasiveness). |
| **Annotator Requirements** | **Composite** — combines deterministic (M_LEX) and LLM-judge (JREL, JFACT, JPER) sources. |
| **Aggregation Method** | Per-session: one M_JQUAL. Per-scenario: mean across 3 runs. Cross-scenario: mean ± std. This is the single-number summary for justification quality in the paper's results table. |
| **Application: Baseline** | Same composite formula. |
| **Application: HAiSP v2** | Same. |

### 5.6 M_HUMAN — Human Expert Rating (Level 3)

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_HUMAN` |
| **Definition** | Post-session Likert ratings from human participants on justification quality (Phase 3 only). |
| **Formula** | ```human_quality = mean(human_ratings across questionnaire items Q7–Q9)``` where Q7="The AI agents' justifications were clear and understandable" (1–5), Q8="The justifications helped me understand why changes were proposed" (1–5), Q9="I trusted the justifications provided by the AI agents" (1–5). |
| **Range & Direction** | [1, 5]; ↑ is better |
| **Measurement Protocol** | Post-session questionnaire (HREC H2026-0234). N≈12 participants. Each participant rates 3 Likert items. Collected via Qualtrics or paper form. |
| **Annotator Requirements** | **Human participants** — domain experts (software developers, product owners). Requirements: ≥1 year agile experience, fluent English. No training needed (questionnaire is self-administered). |
| **Aggregation Method** | Per-participant: mean of Q7-Q9. Cross-participant: mean ± std (N≈12). Report Cronbach's α for internal consistency of the 3-item scale (target > 0.7). |
| **Application: Baseline** | N/A for Phase 1–2. Phase 3: human participants rate the HAiSP v2 session they participated in. A separate human-only baseline group may be added (Open Question 3 in design doc). |
| **Application: HAiSP v2** | Ground truth calibration for automated metrics. Correlate M_JQUAL against M_HUMAN to validate the automated pipeline. |

---

## 6. Robustness Metrics (Cross-Cutting)

### 6.1 M_ADV — Adversarial Resilience

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_ADV` |
| **Definition** | Output quality (M_PWU) when one agent is adversarial, normalized against the non-adversarial baseline for the same scenario. |
| **Formula** | ```adv_ratio = M_PWU(S_adversarial) / M_PWU(S_normal)```. Closer to 1.0 = resilient. |
| **Range & Direction** | (0, 1]; ↑ is better (1.0 = adversarial agent has no impact) |
| **Measurement Protocol** | Run scenario S6 with one agent configured for adversarial behavior (always REMOVE highest-priority items, always ADD lowest). Compare M_PWU against S2 (same items, no adversarial). |
| **Annotator Requirements** | **Deterministic** — scenario configuration + M_PWU computation. |
| **Aggregation Method** | Per-scenario-pair: ratio across 3 runs. Cross-scenario: N/A (only S6 exists as adversarial scenario). |
| **Application: Baseline** | Baseline A: inject adversarial utterances into agent turn. Baseline B: one independent proposal is adversarial. Baseline C: N/A (no agents). |
| **Application: HAiSP v2** | Tests whether the aggregation mechanism can reject clearly bad-faith mutations. Stage 1 deterministic conflict resolution should block adversarial proposals that no other agent supports. |

### 6.2 M_SCALE — Scaling Behavior

| Field | Value |
|-------|-------|
| **Mnemonic** | `M_SCALE` |
| **Definition** | How M_RCONV and M_TOK grow as the number of agents increases. |
| **Formula** | Run with N ∈ {2, 3, 5, 8}. Fit: ```RCONV(N) ~ α × N^β```. Report β (scaling exponent). β < 1 = sublinear scaling (good). β = 1 = linear. β > 1 = superlinear (bad). Same for TOK(N). |
| **Range & Direction** | β < 1 desirable; target β < 0.5 |
| **Measurement Protocol** | Scenario S7 but with variable N. Fix all other parameters (same backlog, same capacity). Run 3 reps per N. Fit power law to means. |
| **Annotator Requirements** | **Deterministic** — from M_RCONV and M_TOK time series. |
| **Aggregation Method** | Report β_rcnv, β_tok, and R² of each fit. |
| **Application: Baseline** | Baseline A: expected to scale superlinearly (all-to-all chat explosion). Baseline B: O(N) by definition (N independent proposals + 1 synthesis). |
| **Application: HAiSP v2** | Round-robin is O(N) by design. Test whether token consumption per round grows with N (does agent prompt size increase with more participant context?). |

---

## 7. Summary: Metric-by-Metric Application Matrix

| # | Metric | Annotator | Phase 1 (Synthetic) | Phase 2 (LLM) | Phase 3 (Human) | Bsl A | Bsl B | Bsl C |
|---|--------|-----------|---------------------|----------------|-----------------|-------|-------|-------|
| 1.1 | M_RCONV | Det / LLM† | ✓ | ✓ | ✓ | ✓† | ✓ (≡1) | ✓ (≡0) |
| 1.2 | M_CNVG | Det / LLM† | ✓ | ✓ | — | ✓† | ✓ (≡1) | — |
| 2.1 | M_PWU | Det | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2.2 | M_GOAL | Det | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2.3 | M_ROLE | Det | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2.4 | M_DEPS | Det | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2.5 | M_CAPE | Det | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2.6 | M_PAR | Det | ✓ | ✓ | — | ✓ | ✓ (≡1) | ✓ (≡1) |
| 2.7 | M_COV | Det | ✓ | ✓ | — | ✓ | ✓ | ✓ (≡1) |
| 2.8 | M_STAB | Det | ✓ | ✓ | — | ✓ | ✓ (≡1) | ✓ (≡1) |
| 3.1 | M_CONS | Det / LLM† | ✓ | ✓ | — | ✓† | ✓ | — |
| 3.2 | M_AGREE | Det / LLM† | ✓ | ✓ | — | ✓† | — | — |
| 3.3 | M_UNDO | Det / LLM† | ✓ | ✓ | — | ✓† | — | — |
| 3.4 | M_SAT | Det / LLM† | ✓ | ✓ | — | ✓† | ✓ (≡1) | — |
| 4.1 | M_TOK | Det | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| 4.2 | M_TEF | Det | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| 4.3 | M_LAT | Det | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| 4.4 | M_RPROD | Det | ✓ | ✓ | — | ✓† | ✓† | — |
| 5.1 | M_LEX | Det | ✓ | ✓ | — | ✓ | ✓ | — |
| 5.2 | M_JREL | LLM | — | ✓ | — | ✓ | ✓ | — |
| 5.3 | M_JFACT | LLM | — | ✓ | — | ✓ | ✓ | — |
| 5.4 | M_JPER | LLM | — | ✓ | — | ✓ | ✓ | — |
| 5.5 | M_JQUAL | Composite | — | ✓ | — | ✓ | ✓ | — |
| 5.6 | M_HUMAN | Human | — | — | ✓ | — | — | — |
| 6.1 | M_ADV | Det | ✓ | ✓ | — | ✓ | ✓ | — |
| 6.2 | M_SCALE | Det | ✓ | ✓ | — | ✓ | ✓ | — |

> † requires LLM-as-judge for Baseline A (free-form chat), deterministic for v2.
> (≡1) trivially 1.0. (≡0) trivially 0. — means N/A or not applicable.

---

## 8. Statistical Analysis Pipeline

### 8.1 Phase 1 Output

Each scenario × run produces a JSON record:

```json
{
  "scenario": "S2",
  "run": 1,
  "algorithm": "haisp_v2",
  "metrics": {
    "M_RCONV": 3, "M_CNVG": 1.0,
    "M_PWU": 0.82, "M_GOAL": 0.65, "M_ROLE": 0.71,
    "M_DEPS": 0.95, "M_CAPE": 0.88, "M_PAR": 0.75,
    "M_COV": 0.42, "M_STAB": 0.94,
    "M_CONS": 0.68, "M_AGREE_beta": 0.12, "M_UNDO": 0.0,
    "M_SAT": 1.0, "M_RPROD": 4.5
  }
}
```

### 8.2 Phase 2 Output

Same as Phase 1 plus: `M_TOK`, `M_TEF`, `M_LAT`, `M_LEX`, `M_JREL`, `M_JFACT`, `M_JPER`, `M_JQUAL`, and inter-judge reliability for each LLM-judge metric.

### 8.3 Aggregation for Paper

| Analysis | Method | Report |
|----------|--------|--------|
| Primary (H1) | Paired t-test M_PWU (v2 vs Bsl A) across 24 pairs | Mean ± SD, t, df, p, Cohen's d |
| Convergence (H2) | Mann-Whitney U on M_RCONV | Median [IQR], U, p, Cliff's δ |
| Justification (H3) | Paired t-test M_LEX (v2 vs Bsl A) | Mean ± SD, t, df, p, Cohen's d |
| Robustness (H4) | Two-way ANOVA: algo × scenario_type | F, df, p, η² |
| Efficiency | Descriptive comparison M_TEF | Mean ± SD, ratio v2/Bsl_A |
| Quality breakdown | Per-metric table | Full matrix of mean ± SD for all metrics × all algorithms |

---

## 9. Implementation Checklist

### Week 1 — Deterministic Metrics Engine
- [ ] `src/platform/metrics/__init__.py` — module init
- [ ] `src/platform/metrics/convergence.py` — M_RCONV, M_CNVG
- [ ] `src/platform/metrics/output_quality.py` — M_PWU, M_GOAL, M_ROLE, M_DEPS, M_CAPE, M_PAR, M_COV, M_STAB
- [ ] `src/platform/metrics/consistency.py` — M_CONS, M_AGREE, M_UNDO, M_SAT
- [ ] `src/platform/metrics/efficiency.py` — M_TOK, M_TEF, M_LAT, M_RPROD
- [ ] `src/platform/metrics/justification_level1.py` — M_LEX (regex heuristics)
- [ ] `src/platform/metrics/collector.py` — `MetricsCollector` class that wires all above into a single `dict` output
- [ ] `tests/test_metrics_deterministic.py` — unit tests for each metric with known inputs → expected outputs

### Week 2 — LLM-Based Metrics & Scenario Runner
- [ ] `src/platform/metrics/justification_level2.py` — M_JREL, M_JFACT, M_JPER, M_JQUAL via LLM-as-judge
- [ ] `src/platform/testing/scenarios.py` — 8 scenario definitions with ground truth
- [ ] `src/platform/testing/scenario_runner.py` — run any algorithm on any scenario, collect all metrics
- [ ] `src/platform/testing/baseline_freeforall.py` — Baseline A
- [ ] `src/platform/testing/baseline_singleshot.py` — Baseline B
- [ ] `scripts/run_evaluation.py` — CLI: `python scripts/run_evaluation.py --phase 2 --reps 3 --output results.csv`

### Week 3 — Analysis
- [ ] `analysis/statistical_tests.py` — H1-H4 tests
- [ ] `analysis/plots.py` — convergence curves, quality-by-round, token efficiency scatter
- [ ] `analysis/tables.py` — LaTeX table generation for paper
