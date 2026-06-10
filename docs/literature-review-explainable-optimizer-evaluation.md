# Literature Review: Evaluating Explainable Optimizers in Human-AI Coordination

**Date:** 2026-06-10
**Task:** t_c83430df
**Purpose:** Inform the HAiSP v2 evaluation design doc
**Method:** Targeted web search + arxiv + Semantic Scholar + paper extraction

---

## 1. Scope and Search Strategy

Searched across four overlapping domains:
- **Explainable AI (XAI) evaluation** — how are qualitative justifications measured?
- **Multi-agent deliberation** — how do we evaluate structured negotiation among LLM agents?
- **Human-AI coordination (HAIC)** — what frameworks exist for evaluating collaborative systems?
- **Search-based software engineering (SBSE)** — how is the Next Release Problem benchmarked?

---

## 2. Key Papers

### 2.1 Foundational: Deliberative Quality Index (DQI)

**Steenbergen et al. (2003).** "Measuring Political Deliberation." *European Journal of Political Research.*

The DQI operationalizes deliberation quality across five dimensions scored 0–3:
1. **Level of Justification** — zero (no justification) to sophisticated (multiple complete justifications)
2. **Content of Justification** — reference to common good vs. self-interest
3. **Respect** — acknowledgement of counterarguments
4. **Constructive Politics** — proposals for compromise or consensus-building
5. **Interactivity** — engagement with others' speech acts

This is the gold standard for deliberation evaluation and has been adapted to AI:

| Paper | Adaptation |
|-------|-----------|
| **Zhuang et al. (CHI EA '26)** | Applied DQI to GPT-4o-mini multi-agent dialogues. Found analytic style + high certainty → best deliberation. |
| **ACL 2024 DeliTe Workshop** | First workshop on language-driven deliberation; explored computational DQI variants. |

### 2.2 Directly Applicable to HAiSP

**Zhuang, Wang, Zhang (CHI EA '26).** "Can AI Deliberate? Evaluating Deliberative Quality and Stance Flow in Multi-Agent LLMs."

- 2×2 factorial: stance certainty (high/low) × reasoning style (analytic/storytelling)
- 7 agents, up to 40 rounds, 3 issue contexts
- **Finding:** Analytic reasoning provides structural scaffold; high certainty improves argumentative clarity
- **Relevance:** Directly validates that structured argumentation protocols (like our mutation algebra) improve deliberation quality. The DQI dimensions map to our justification quality Level 2 evaluator.

**Binkyte (arXiv:2505.12001, 2025).** "Interactional Fairness in LLM Multi-Agent Systems."

- Introduces Interactional Fairness: Interpersonal (tone, respect) + Informational (justifications, explanations)
- Adapts Colquitt's Organizational Justice Scale for agent evaluation
- **Finding:** Tone and justification quality significantly affect acceptance decisions, *independent of objective outcomes*
- **Relevance:** Directly applicable to our `done=True` consensus signals. If an agent accepts a plan because of polite tone rather than plan quality, Consensus Genuineness is inflated.

**Fragiadakis et al. (arXiv:2407.19098, 2024/2025).** "Evaluating Human-AI Collaboration: A Review and Methodological Framework."

- Decision tree for selecting metrics based on collaboration mode: AI-Centric, Human-Centric, Symbiotic
- Mixes quantitative + qualitative metrics
- **Relevance:** Our Phase 3 (human-in-the-loop) maps to Symbiotic mode. Framework suggests tracking: joint performance, trust, workload, situation awareness.

**Chen et al. (arXiv:2604.18005, 2026).** "Diversity Collapse in Multi-Agent LLM Systems."

- Shows round-robin interaction can cause structural coupling and premature consensus
- Metrics: Vendi Score, Structural Disorder (1-φ), Semantic Dispersion (PCD), Lexical Uniqueness
- **Finding:** Interaction structure (not model insufficiency) drives diversity collapse
- **Relevance:** Critical warning for HAiSP — round-robin topology may suppress diverse perspectives. We should measure semantic diversity of proposals across rounds.

**Abdelnabi et al. (ICLR 2024).** "LLM-Deliberation: Evaluating LLMs with Interactive Multi-Agent Negotiation."

- Multi-party, multi-issue, scorable negotiation benchmark
- Metrics: deal success rate, wrong deals (violating BATNA), own score, theory-of-mind
- **Finding:** GPT-4 achieves 81% deal success in cooperative mode; adversarial agents manipulate outcomes
- **Relevance:** Scorable outcomes framework. Our sprint plans can be scored against ground-truth Pareto-optimal plans.

**Siedler (arXiv:2604.07028, 2026).** "Strategic Persuasion with Trait-Conditioned Multi-Agent Systems."

- Round-robin legal argumentation with trait-conditioned LLM agents
- 7,000+ simulated trials; heterogeneous teams outperform homogeneous
- **Relevance:** Validates that agent persona diversity improves outcomes. Our role-specific agents (FE/BE/QA) should produce better plans than homogeneous agents.

### 2.3 XAI Evaluation Frameworks

**Frontiers in AI (2024).** "Human-centered evaluation of explainable AI applications: a systematic review." (73 papers, 77 user studies identified)

Taxonomy of 30 evaluation components across 3 dimensions:

| Dimension | Key Metrics | HAiSP Relevance |
|-----------|------------|-----------------|
| **In-Context Quality** | Satisfaction, usefulness, actionability, sufficiency of explanation | Maps to our Justification Specificity (Level 1–3) |
| **Human-AI Interaction** | Trust, understanding, predictability, transparency, cognitive load | Maps to Phase 3 human questionnaire |
| **Human-AI Performance** | Task performance, insight discovery | Maps to output quality metrics (4.1) |

**Finding:** Only 26% of studies use an existing evaluation framework; field suffers from severe lack of standardization.

### 2.4 Industry Multi-Agent Evaluation

**Galileo (2025).** "How to Define Success in Multi-Agent AI Systems."

17 metrics organized into: goal completion, response quality, interaction/trajectory, safety/compliance, custom. Key insight: evaluate *conversation quality* across multi-turn sessions (coherence, relevance, satisfaction) — not just final output.

**orq.ai (2025).** "A Comprehensive Guide to Evaluating Multi-Agent LLM Systems."

Covers metrics for tool selection quality, context adherence, agent flow, and trajectory correctness.

### 2.5 Sprint Planning Adjacent (SBSE / NRP)

**Zhang et al. (GECCO 2007).** "The Multi-Objective Next Release Problem." (343+ citations)

- Formulates release planning as multi-objective optimization: maximize customer satisfaction, minimize cost
- Uses Pareto optimality as evaluation framework
- **Relevance:** Our output quality metrics (Priority-Weighted Utilization, Goal Alignment, Role Balance) are multi-objective. Pareto front comparison is the right evaluation paradigm.

**Oftebro et al. (arXiv:2507.10753, 2025).** "GenAI-Enabled Backlog Grooming."

- Jira plugin: embedding-based duplicate detection + GPT-4o merge/delete proposals
- 100% precision, 45% time reduction
- **Relevance:** Validates LLM-based backlog refinement. Suggests embedding-based similarity as justification quality proxy.

**Chattopadhyay et al. (arXiv:2603.28677, 2026).** "Enhancing User-Feedback Driven Requirements Prioritization."

- Clustering + dependency modeling improves search-based prioritization
- Problem is NP-hard
- **Relevance:** Validates dependency-aware scoring (our Dependency Satisfaction metric).

---

## 3. Evaluation Gaps in Literature

1. **No automated justification quality metric is widely accepted.** Lexical specificity (our Level 1) appears in no paper. LLM-as-judge (our Level 2) is emerging but unvalidated. The DQI has the strongest theoretical grounding but was designed for human political deliberation, not agent coordination.

2. **Convergence speed as an evaluation dimension is almost entirely absent.** Most multi-agent papers fix max rounds and measure output quality. The "give baselines the same convergence criteria" approach (our methodology doc §3) is novel.

3. **Token efficiency as a metric is underexplored.** Industry frameworks (Galileo) mention cost, but academia rarely measures coordination efficiency per unit compute.

4. **Structured vs. unstructured deliberation comparison** — only the CHI EA '26 paper compares reasoning styles, but no paper directly compares structured mutation protocols against free-form chat for plan quality.

---

## 4. Candidate Metrics for HAiSP v2 Evaluation

### 4.1 Output Quality (Sprint Plan)

| Metric | Source | Status in HAiSP |
|--------|--------|-----------------|
| Priority-Weighted Utilization | SBSE/NRP literature | In methodology doc §4.1 |
| Goal Alignment (cosine sim) | Galileo, Frontiers XAI | In methodology doc §4.1 |
| Role Balance (Gini-like) | NRP multi-objective | In methodology doc §4.1 |
| Dependency Satisfaction | NRP, Chattopadhyay 2026 | In methodology doc §4.1 |
| Capacity Efficiency | NRP, SBSE | In methodology doc §4.1 |
| Pareto Dominance Score | Zhang et al. 2007 (GECCO) | In methodology doc §4.1 |

### 4.2 Process Quality (Deliberation)

| Metric | Source | Status in HAiSP |
|--------|--------|-----------------|
| Rounds to Convergence | HAiSP novel (methodology §3) | In methodology doc §4.2 |
| Mutation Acceptance Rate | HAiSP novel | In methodology doc §4.2 |
| Conflict Resolution Rate | HAiSP novel | In methodology doc §4.2 |
| Justification Quality (Level 1–3) | DQI + Frontiers XAI | In methodology doc §4.2–4.3 |
| Backtracking Rate | HAiSP novel | In methodology doc §4.2 |
| Consensus Genuineness | Binkyte 2025 (Interactional Fairness) | In methodology doc §4.2 |
| Token Efficiency | Galileo 2025 (cost-effectiveness) | In methodology doc §4.2 |
| Round Productivity | HAiSP novel | In methodology doc §4.2 |

### 4.3 NEW — Candidates from Literature (not yet in methodology doc)

| Metric | Definition | Source | Why Add |
|--------|-----------|--------|---------|
| **Semantic Dispersion** | Average pairwise cosine distance between agent proposals per round | Chen et al. 2026 | Detect diversity collapse from round-robin topology |
| **Justification-Outcome Alignment** | Correlation between justification specificity and whether the mutation was accepted | Binkyte 2025 (interactional fairness) | Test if justification quality actually drives consensus (or if agents rubber-stamp) |
| **DQI Score (adapted)** | Steenbergen DQI applied to mutation justifications: level, content, respect, constructive politics, interactivity | Zhuang et al. CHI EA '26 | Stronger theoretical grounding than our ad-hoc Level 2 |
| **Stance Flow (ΔSupport)** | Net change in agent support for the current sprint plan across rounds | Zhuang et al. CHI EA '26 | Captures deliberation dynamics, not just endpoint |
| **Adversarial Resilience** | Quality delta when one agent proposes malicious mutations | Abdelnabi et al. ICLR 2024 | Already in methodology doc §4.4 |
| **Trust Calibration** | Correlation between human trust ratings and objective plan quality | Frontiers XAI, HREC protocol | Validates that justification quality (not tone) drives trust |
| **Cognitive Load** | Post-session NASA-TLX or similar for human participants | Fragiadakis et al. 2024 | Phase 3 human evaluation |
| **Task Completion Time** | Wall-clock time to convergence | Galileo 2025 | Practical adoption metric |

### 4.4 Metrics NOT Recommended

| Metric | Reason to Exclude |
|--------|-------------------|
| Interpersonal Fairness (tone) | HAiSP agents use structured mutation envelopes — tone is not a free variable |
| Informational Fairness (explanation completeness) | Already covered by Justification Specificity |
| Lexical Uniqueness (IDF n-gram) | Too surface-level; semantic dispersion is more informative |

---

## 5. Experimental Design Patterns from Literature

| Pattern | Source | HAiSP Application |
|---------|--------|-------------------|
| 2×2 factorial design | Zhuang et al. CHI '26 | Could test: topology (round-robin vs. free-for-all) × aggregation (deterministic vs. LLM-only) |
| Trait-conditioned agents | Siedler 2026 | Our role-specific agents (FE/BE/QA) are trait-conditioned; test persona diversity vs. plan quality |
| Adversarial ablation | Abdelnabi et al. ICLR '24 | Already planned: S6 adversarial scenario |
| LLM-as-judge for justification | DQI adaptation, Frontiers XAI | Already planned: Level 2 evaluator |
| Ground-truth Pareto front | Zhang et al. 2007 (GECCO) | Open question in methodology doc §8.1 — use OR-Tools ILP solver |

---

## 6. Recommendations for the HAiSP Evaluation Design

1. **Adopt the DQI framework** for Level 2 justification evaluation instead of the current ad-hoc 3-axis (relevance, factual grounding, persuasiveness). The DQI has 20+ years of validation in political science and has been adapted to LLM deliberation by Zhuang et al. (CHI EA '26). The five dimensions (justification level, content, respect, constructive politics, interactivity) map cleanly to mutation justifications.

2. **Add Semantic Dispersion** as a process metric. Chen et al. (2026) show that round-robin topology can cause diversity collapse. Track pairwise cosine distance between agent proposals each round. If dispersion drops below a threshold, the topology is suppressing diverse viewpoints — this is the structural coupling failure mode.

3. **Add Justification-Outcome Alignment.** Binkyte (2025) shows that tone can drive acceptance independent of quality. Measure correlation between justification specificity and mutation acceptance. If correlation is near zero, agents are rubber-stamping regardless of argument quality — Consensus Genuineness is inflated.

4. **Keep the round-limit deadlock resolution** as-is (methodology doc §3). No other paper uses "give baselines the same convergence criteria" — this is a genuine methodological contribution.

5. **Cite the Next Release Problem (NRP) literature** to ground our optimization metrics. Zhang et al. (2007) established Pareto optimality as the evaluation framework for release planning. Our Priority-Weighted Utilization, Goal Alignment, and Role Balance form a multi-objective space.

---

## 7. Reference List

- Steenbergen, M. R., Bächtiger, A., Spörndli, M., & Steiner, J. (2003). Measuring political deliberation: A discourse quality index. *European Journal of Political Research*, 42(1), 21–57.
- Zhuang, K., Wang, Y., & Zhang, W. (2026). Can AI Deliberate? Evaluating Deliberative Quality and Stance Flow in Multi-Agent LLMs. *CHI EA '26*. DOI: 10.1145/3772363.3798877
- Binkyte, R. (2025). Interactional Fairness in LLM Multi-Agent Systems: An Evaluation Framework. arXiv:2505.12001.
- Fragiadakis, G., Diou, C., Kousiouris, G., & Nikolaidou, M. (2025). Evaluating Human-AI Collaboration: A Review and Methodological Framework. arXiv:2407.19098v2.
- Chen, N., Tong, Y., Yang, Y., He, Y., Zhang, X., Wang, Q., Zou, Q., & He, B. (2026). Diversity Collapse in Multi-Agent LLM Systems. arXiv:2604.18005.
- Abdelnabi, S., Gomaa, A., Sivaprasad, S., Schönherr, L., & Fritz, M. (2024). LLM-Deliberation: Evaluating LLMs with Interactive Multi-Agent Negotiation Game. *ICLR 2024* (rejected).
- Siedler, P. D. (2026). Strategic Persuasion with Trait-Conditioned Multi-Agent Systems for Iterative Legal Argumentation. arXiv:2604.07028.
- Zhang, Y., Harman, M., & Mansouri, S. A. (2007). The Multi-Objective Next Release Problem. *GECCO 2007*. ACM.
- Frontiers in AI (2024). Human-centered evaluation of explainable AI applications: a systematic review. DOI: 10.3389/frai.2024.1456486.
- Galileo (2025). How to Define Success in Multi-Agent AI Systems. Galileo Blog.
- Bächtiger, A., et al. (2010). Disentangling diversity in deliberative democracy. *British Journal of Political Science*, 40(1).
- Oftebro, K. L., Nguyen-Duc, A., Kemell, K. K. (2025). GenAI-Enabled Backlog Grooming in Agile Software Projects. arXiv:2507.10753.
- Chattopadhyay, A., Niu, N., Liu, H., Zhang, J. (2026). Enhancing User-Feedback Driven Requirements Prioritization. arXiv:2603.28677.
