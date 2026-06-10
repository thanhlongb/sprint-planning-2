# Rapid Review: Evaluation Approaches for Multi-Agent Coordination Systems with Opaque Agent Internals

**Type:** Research Note (1-page rapid review)
**Date:** 2026-06-10
**Project:** HAiSP — Sprint Planning for Human-AI Agile Teams
**Purpose:** Identify evaluation challenges and candidate metrics for a coordination platform that orchestrates LLM agents without access to their internal states. Feeds into the evaluation methodology design document (t_69074f51).

---

## 1. The Core Evaluation Challenge

The HAiSP platform is a coordination layer — it structures round-robin negotiation among LLM agents using a mutation algebra (ADD/REMOVE/SWAP/REORDER/RESCOPE) with hybrid deterministic+LLM aggregation. Critically, the platform sees only structured mutation envelopes and NL justifications, not agent internals (reasoning traces, token logprobs, model-specific parameters). This opacity creates two fundamental evaluation tensions:

**Tension 1 — The Round-Limit Deadlock.** Giving both our algorithm and a baseline the same hard `max_rounds=N` collapses convergence speed to a constant. If both stop at N, the metric is uninformative. Yet removing the cap risks unbounded cost for unstructured baselines.

**Tension 2 — Qualitative Justification Quality.** Agents produce natural-language justifications ("MFA is a blocking dependency for the compliance milestone..."). Evaluating whether one set of justifications reflects better deliberation than another requires judging argument quality — a task that current automated metrics handle poorly.

These tensions are not unique to HAiSP. The broader multi-agent LLM evaluation literature (surveyed below) reveals that existing benchmarks overwhelmingly focus on single-agent task completion or narrow game-theoretic settings, with few addressing the evaluation of opaque coordination machinery.

---

## 2. Landscape of Multi-Agent LLM Evaluation

**Survey coverage.** Jurkovic (2025) surveyed 32 multi-agent LLM evaluation papers and found miscoordination to be the most represented failure mode (26 papers), while collusion (5 papers) and conflict are less studied. The survey identifies a critical gap: "We failed to find any multi-agent collusion evaluations that don't take place in a board game setting or are set in environments directly related to AI failure modes" — highlighting the field's immaturity for real-world coordination evaluation.

**Major benchmarks.** MultiAgentBench (Zhu et al., 2025; ACL 2025) provides the most comprehensive multi-agent evaluation to date, covering six scenarios (collaborative coding, research, gaming, database, bargaining, Werewolf) with milestone-based KPIs, structured planning/communication scores, and multiple coordination topologies (star, chain, tree, graph). Its MARBLE framework distinguishes planner/actor roles and measures coordination quality beyond task success. However, agents in MARBLE share memory and internal state — a luxury unavailable in HAiSP's opaque-agent setting.

**Beyond accuracy.** The CLEAR framework (Mehta, 2025) argues that single-run accuracy is insufficient for enterprise agent evaluation, proposing five dimensions: Cost, Latency, Efficacy, Assurance, and Reliability. CLEAR found 50× cost variation across agents with similar accuracy, and GPT-4 agent reliability dropping from 60% pass@1 to 25% pass@8. This multi-dimensional thinking is directly applicable to HAiSP: coordination quality must be measured across output quality, process efficiency, justification fidelity, and robustness — not just "did we get a plan."

**Negotiation-specific work.** The LLM-Coordination Benchmark (UCSB-AI, NAACL 2025) studies pure coordination games, finding that LLMs exhibit theory-of-mind-like coordination but degrade under information asymmetry. Negotiation benchmarks based on Scoreable Games provide structured evaluation of bargaining outcomes, but none address the structured-vs-unstructured coordination comparison central to HAiSP.

**Key gap.** No existing benchmark evaluates a coordination platform that (a) is agent-internals-agnostic, (b) compares structured negotiation against unstructured free-for-all deliberation at equal resource budget, and (c) measures the quality of NL justifications produced during coordination. This is the evaluation gap HAiSP must fill.

---

## 3. Candidate Metrics — Shortlist

Drawing from the literature and HAiSP's architecture, we propose five metric categories. Each includes concrete, measurable definitions that work across both structured (HAiSP v2) and unstructured (free-for-all baseline) settings.

### 3.1 Output Quality (the Sprint Plan)

These measure the *final artifact* — the sprint plan itself. All are computable from structured plan data, making them baseline-agnostic.

| Metric | Definition | Range | Source |
|--------|-----------|-------|--------|
| **Priority-Weighted Utilization** | Σ(priority_score × story_points) / capacity, where priority ∈ {HIGH=3, MEDIUM=2, LOW=1} | [0, 1], ↑ | Extends MultiAgentBench's task-specific KPIs |
| **Goal Alignment** | Cosine similarity between sprint goal embedding and mean item-description embedding | [0, 1], ↑ | Standard semantic similarity; G-Eval (Liu et al., 2023) CoT rubric applicable |
| **Dependency Satisfaction** | Fraction of planned items whose dependencies are also in the plan or already completed | [0, 1], ↑ | Task-specific; derived from backlog graph structure |
| **Capacity Efficiency** | 1 − |actual_SP − target_SP| / target_SP | [0, 1], ↑ | Standard optimization metric |
| **Role Balance** | 1 − (max_role_share − min_role_share), where role_share = fraction of SP relevant to each role | [0, 1], ↑ | Inspired by fairness metrics in multi-stakeholder evaluation (CLEAR §4.5) |

### 3.2 Process Quality (the Deliberation)

These measure *how* the plan was reached — the quality of the coordination process itself.

| Metric | Definition | Range | Source |
|--------|-----------|-------|--------|
| **Rounds to Convergence** | Number of rounds until convergence criteria are first met (all agents satisfied, no new proposals) | [1, max_rounds], ↓ | Adapted from MultiAgentBench milestone tracking; convergence criteria per approach |
| **Mutation Acceptance Rate** | |applied_mutations| / |proposed_mutations| | [0, 1], ↑ | HAiSP-specific; measures deliberation efficiency |
| **Token Efficiency** | (final_plan_quality) / (total_tokens / 1000) | [0, ∞), ↑ | CLEAR Cost-Normalized Accuracy (CNA) adapted to coordination |
| **Backtracking Rate** | Fraction of agents who propose REMOVE on an item they previously ADD-ed | [0, 1], ↓ | Novel; proxies deliberation stability |
| **Consensus Genuineness** | Fraction of agents signaling satisfaction at convergence | [0, 1], ↑ | Extends MultiAgentBench's "all agents agree" criterion |

### 3.3 Justification Quality (the Rationale)

These measure the *quality of natural-language justifications* — the core qualitative dimension. We propose a three-level hierarchy from cheap to expensive, following established LLM-as-judge methodology.

**Level 1 — Lexical Specificity (deterministic, free).** Score each justification by surface features: +0.25 for referencing specific item attributes (SP, priority, labels); +0.25 for referencing capacity or sprint goal; +0.25 for referencing dependency chains or other items; +0.25 for citing evidence (past sprint data, velocity). Range [0, 1], ↑.

**Level 2 — LLM-as-Judge (semi-automated).** A separate evaluator LLM rates each justification on three axes using a G-Eval-style rubric (Liu et al., 2023): *Relevance* (1–5: does the justification support the mutation?), *Factual Grounding* (1–5: does it reference verifiable attributes?), *Persuasiveness* (1–5: would a reasonable product owner find it compelling?). Composite = mean of three scores. Inter-judge reliability via duplicate evaluation (temperature=0.7, compute Pearson r). This follows the ChatEval multi-agent referee pattern (Chan et al., 2024) but uses a single judge for cost efficiency.

**Level 3 — Human Expert Rating (manual).** Human participants (HREC H2026-0234) rate justifications they receive during live sessions on the same three axes. Serves as ground-truth calibration for Level 2.

### 3.4 Cost & Efficiency

Following CLEAR (Mehta, 2025), we measure resource consumption explicitly.

| Metric | Definition | Range | Source |
|--------|-----------|-------|--------|
| **Total Token Consumption** | Sum of all LLM API tokens across all agents and rounds | [0, ∞), ↓ | CLEAR Cost dimension |
| **Cost per Converged Plan** | Total API cost / number of plans that converged | [0, ∞), ↓ | CLEAR Cost per Success (CPS) |
| **Wall-Clock Latency** | End-to-end time from session start to convergence | [0, ∞), ↓ | CLEAR Latency dimension |

### 3.5 Robustness

These stress-test the coordination layer under adverse conditions, following the reliability dimension of CLEAR and MultiAgentBench's adversarial scenario design.

| Metric | Definition |
|--------|-----------|
| **Adversarial Resilience** | Output quality when one agent proposes mutations designed to game the system |
| **Cold-Start Quality** | Output quality when initial sprint list is empty |
| **Scaling Behavior** | Output quality and convergence speed with 2, 3, 5, 8 agents |

---

## 4. Resolving the Round-Limit Deadlock

The solution: **give all approaches uniform convergence criteria, not uniform round counts.** Every approach runs until natural convergence, with a generous safety-net `max_rounds` (e.g., 10) that should never be hit by a well-functioning system.

- **HAiSP v2 convergence:** All agents `done=True` for 2 consecutive rounds AND zero mutations applied in the second round (deterministic).
- **Baseline A (free-for-all) convergence:** LLM judge determines from transcript that all agents have expressed satisfaction and no new proposals have emerged for 2 consecutive turns.
- **Secondary comparison:** Fix a token budget equal to HAiSP v2's upper 95% CI and compare output quality at budget exhaustion (Level 2 in `baseline-comparison-approach.md`).

---

## 5. Summary and Recommendations

1. **Primary comparison:** HAiSP v2 vs. unstructured free-for-all (Baseline A) using uniform convergence criteria — this resolves the round-limit deadlock without artificially capping either side.
2. **Primary metrics:** Priority-Weighted Utilization (output quality) and Rounds-to-Convergence (process quality), with token efficiency as a secondary cost metric.
3. **Qualitative dimension:** Three-level justification quality assessment (lexical → LLM-as-judge → human expert), with LLM-as-judge following established G-Eval methodology (Liu et al., 2023).
4. **Statistical rigor:** Follow CLEAR's `pass@k` reliability measurement (at least 3 independent runs per scenario) and MultiAgentBench's milestone-based tracking.
5. **Open challenge:** No existing benchmark provides ground-truth "optimal deliberation" — we must construct scenario-specific ground-truth sprint plans (manually or via ILP solver) as a quality ceiling.

---

## References

1. Zhu, K., Du, H., Hong, Z., et al. (2025). "MultiAgentBench: Evaluating the Collaboration and Competition of LLM Agents." *ACL 2025*. arXiv:2503.01935. — Comprehensive multi-agent benchmark with milestone-based KPIs and multiple coordination topologies.

2. Mehta, S. (2025). "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems (CLEAR)." arXiv:2511.14136. — Five-dimensional evaluation framework (Cost, Latency, Efficacy, Assurance, Reliability); introduced Cost-Normalized Accuracy and pass@k reliability.

3. Liu, Y., Iter, D., Xu, Y., et al. (2023). "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment." *EMNLP 2023*. — LLM-as-judge with chain-of-thought rubric generation; foundation for Level 2 justification quality assessment.

4. Jurkovic, N. (2025). "Survey of Multi-agent LLM Evaluations." LessWrong. — Survey of 32 multi-agent evaluation papers; identifies gaps in collusion evaluation and real-world scenario coverage.

5. Chan, C.-M., Chen, W., Su, Y., et al. (2024). "ChatEval: Towards Better LLM-based Evaluators through Multi-Agent Debate." *ICLR 2024*. — Multi-agent referee team for evaluation; informs LLM-as-judge calibration approach.

6. UCSB-AI Lab. "LLM-Coordination Benchmark." NAACL 2025. GitHub: eric-ai-lab/llm_coordination. — Pure coordination games evaluating LLM theory-of-mind in multi-agent settings.

7. Li, G., Hammoud, H., Itani, H., et al. (2023). "CAMEL: Communicative Agents for 'Mind' Exploration of Large Language Model Society." *NeurIPS 2023*. — Early framework for LLM agent societies; foundational for multi-agent interaction paradigms.

8. Park, J.S., O'Brien, J.C., Cai, C.J., et al. (2023). "Generative Agents: Interactive Simulacra of Human Behavior." *UIST 2023*. — Architecture for believable agent behavior; relevant for agent persona design in evaluation scenarios.
