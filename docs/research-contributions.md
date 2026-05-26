# Research Contributions

**Project:** HASP — Human-AI Collaborative Sprint Planning Platform
**Status:** Draft
**Last Updated:** 2026-05-17

---

## Overview

HASP makes two primary research contributions, both of which address open algorithmic
problems in multi-agent collaborative planning. No prior work has formally designed or
evaluated these mechanisms in the context of AI-augmented Agile sprint planning.

The platform itself — built on the A2A protocol with a template-driven phase orchestrator —
is the vehicle that enables these contributions to be both implemented and empirically
evaluated. But the platform architecture alone is not the research claim. The algorithms are.

---

## Contribution 1 — Prioritization Consensus Algorithm

### The Problem

During the prioritization phase, every participant (agent or human) independently votes on
backlog items using dot voting. Agents vote based on technical priority inferred from their
responsibility scope — a frontend agent may rank UI bugs highly while a backend agent ranks
API stability issues first. The result is a set of conflicting, multi-stakeholder rankings
that must be resolved into a single agreed sprint priority order.

This is not a trivial aggregation problem. Standard dot vote tallying (sum votes, rank
descending) ignores:

- **Responsibility-weighted authority** — an agent responsible for a subsystem has more
  legitimate authority over technical priority within that domain than a general agent.
- **Conflict density** — when two or more agents rank the same items at opposing ends of
  the spectrum, simple summation masks genuine disagreement and produces a false consensus.
- **Dependency constraints** — a lower-voted item may be a blocker for a higher-voted item,
  making naive ranking selection technically invalid.
- **Business vs. technical priority tension** — the product owner's business priority and
  the developers' technical priority may point in opposite directions for the same item.

### The Research Question

RQ1 (technical): What prioritization consensus mechanism produces sprint priority orderings
that are coherent, conflict-aware, and respect both business and technical priority signals
in a multi-agent setting?

### Two Variants Required

The algorithm must be designed in two variants because the conflict resolution dynamics
differ fundamentally between the two session modes:

**Variant A — Agent-Only (Autonomous)**
All participants are agents. Votes are deterministic given the same inputs. Conflict
resolution can be purely algorithmic: responsibility-weighted rank aggregation, dependency
graph traversal, and capacity-constrained item selection. The algorithm can be evaluated
against a ground truth sprint plan produced by human practitioners on the same backlog.

**Variant B — Mixed Human-Agent**
Human participants introduce non-deterministic, socially-influenced behaviour. A human
developer may change their vote after discussion, defer to a more experienced colleague,
or vote strategically. The consensus algorithm must accommodate:
- Late votes or abstentions from human participants
- Human-initiated re-negotiation of rankings after the initial vote reveal
- Authority asymmetry between human roles (e.g. a senior architect's ranking carries
  social weight that a raw vote tally does not capture)

The mixed variant cannot be purely algorithmic — it must include a deliberation protocol
that structures human-agent negotiation without deadlocking on disagreement.

### Proposed Algorithm Sketch (to be formalised)

```
Input:
  V = { v_i : participant_i → [item rankings] }   # all votes
  W = { w_i : participant_i → responsibility_scope } # agent capability declarations
  D = dependency graph over backlog items
  C = sprint capacity (story points)

Step 1 — Responsibility-Weighted Rank Aggregation
  For each item j:
    score(j) = Σ_i [ rank_weight(rank_i(j)) × authority_weight(w_i, j) ]
  where authority_weight(w_i, j) = 1 + α if item j falls within participant_i's scope

Step 2 — Conflict Detection
  Flag item j as contested if:
    max_rank(j) - min_rank(j) > threshold T
    AND the high/low rankers have non-overlapping responsibility scopes

Step 3 — Dependency Resolution
  Topological sort of contested items against D.
  Promote blockers of high-priority items if not already in top-K.

Step 4 — Capacity-Constrained Selection
  Greedily select items by score until capacity C is filled.
  Contested items above the capacity cutoff trigger deliberation (Variant B only).

Step 5 (Variant B only) — Human Deliberation Protocol
  Broadcast contested items to all participants with conflict summary.
  Open structured discussion round (time-boxed).
  Re-vote on contested items only.
  Apply Step 1-4 to updated votes.
```

### Evaluation Metrics

- **Kendall's tau** — rank-order agreement between algorithm output and human reference
  plan on the same backlog (RQ2)
- **Conflict resolution rate** — proportion of contested items resolved without requiring
  manual facilitator intervention
- **Deliberation round count** — number of re-vote rounds before consensus (Variant B)
- **Dependency validity** — proportion of selected sprint items free of unresolved blockers

---

## Contribution 2 — Workload-Aware Task Assignment Algorithm

### The Problem

Once the sprint backlog is formed, items must be assigned to participants. The naive
approach is first-come-first-served: the first participant to volunteer gets the item.
This is inadequate for a multi-agent setting because:

- **Agent workload is not directly observable.** Unlike human developers who report velocity
  in story points, agents do not have a universally agreed unit of capacity. An agent backed
  by GPT-4o has different throughput than one backed by GPT-3.5. An agent handling a complex
  architectural task is not equivalent to one doing a UI label fix.
- **Capability-task mismatch.** Assigning a complex, multi-file refactor to a small LLM
  agent is technically valid but practically poor. Task complexity should be matched to
  agent capability tier.
- **Organisational budget constraints.** In a multi-organisation setting, larger LLM calls
  cost more. An organisation may declare a token budget that constrains which tasks their
  agent can accept.
- **Responsibility scope.** An agent responsible for the payment service should have
  preferential claim on payment-related tasks, not just any available item.

### The Research Question

RQ1 (technical): What task assignment strategy produces balanced, capability-matched
workload distribution across heterogeneous agents in a multi-agent sprint planning session?

### Two Variants Required

**Variant A — Agent-Only (Autonomous)**
All participants are agents with declared capabilities (model tier, token budget, scope).
Assignment is fully algorithmic. The platform has complete information about all
participants' declared constraints and can optimise globally across all items and agents.

**Variant B — Mixed Human-Agent**
Human participants volunteer for tasks based on preference and perceived expertise —
not algorithmic constraints. The assignment algorithm must:
- Give human volunteers unconditional priority for items they claim (humans cannot be
  algorithmically outbid by agents in their own sprint)
- Fall back to agent assignment only for items no human claimed
- Accommodate human withdrawal from a volunteered task (agent takes over)

### Proposed Algorithm Sketch (to be formalised)

```
Input:
  S = selected sprint backlog items (from Contribution 1 output)
  P = { p_i : participant_i → (role, scope, model_tier, token_budget, current_load) }
  complexity(j) = estimated complexity of item j (LOW / MEDIUM / HIGH)
    derived from: story points, label tags, dependency count

For each item j in S (ordered by priority descending):

  Step 1 — Collect Volunteers
    Broadcast assign_opportunity(j) to all participants.
    Collect responses within timeout T.

  Step 2 — Human Priority (Variant B only)
    If any human participant volunteers → assign to human, skip Steps 3-5.

  Step 3 — Scope Filtering
    Filter volunteers to those whose scope overlaps with item j's domain labels.
    If no scoped volunteers remain → revert to full volunteer pool.

  Step 4 — Capability Matching
    Filter volunteers to those where model_tier >= required_tier(complexity(j)).
    If no capable volunteers remain → assign to highest-tier available participant.

  Step 5 — Workload Balancing
    Among remaining candidates:
      score(p_i) = token_budget_remaining(p_i) / estimated_tokens(j, model_tier_i)
    Assign to participant with highest score (most remaining relative capacity).
    Tiebreak: random selection.

  Step 6 — Auto-Balance Fallback
    If no volunteers at all → apply Steps 3-5 across all participants regardless of
    volunteering, treating all as implicit candidates.

Output:
  assignments = { item_id → participant_id }
  reasons = { item_id → VOLUNTEERED | SCOPE_MATCHED | CAPABILITY_MATCHED |
                         LOAD_BALANCED | AUTO_BALANCED }
```

### Open Research Questions Within This Contribution

- **Workload quantification:** What is the right unit of agent capacity — token budget,
  task count, story points, or a composite? This is an open question explicitly raised
  in the May 2026 supervisor meetings. The algorithm above uses token budget as a proxy;
  this assumption needs empirical validation.
- **Model tier classification:** How do we formally define complexity tiers for tasks, and
  how do we map those to model capabilities? A taxonomy needs to be established.
- **Cross-organisation budget transparency:** Should agents declare their budget to the
  platform, or should the platform infer capacity from observed response latency and output
  quality? Privacy vs. optimality tradeoff.

### Evaluation Metrics

- **Gini coefficient** — workload distribution equity across agents post-assignment
  (lower = more balanced)
- **Capability match rate** — proportion of items assigned to a participant whose model
  tier meets or exceeds the required tier for that item's complexity
- **Scope alignment rate** — proportion of items assigned to a participant whose declared
  scope overlaps the item's domain
- **Volunteer satisfaction rate** (Variant B) — proportion of human volunteers who
  received their claimed item (measures whether humans feel agency in the process)

---

## How These Contributions Relate to the Platform

The platform is necessary to instantiate and test both algorithms, but it is not the
contribution. The relationship is:

```
Platform (A2A + Template Engine + Phase Orchestrator)
    └── enables execution of both algorithms in a realistic session context
            └── Contribution 1: Prioritization Consensus (Phase 2 of session)
            └── Contribution 2: Task Assignment (Phase 4 of session)
                    └── evaluated via:
                            - Autonomous simulation (RQ1, RQ2)
                            - Human study with TAM instrument (RQ3)
```

The platform's architectural contribution (A2A protocol, template-driven sessions,
participant symmetry) supports a separate paper or is documented as a technical report.
The research paper's main claims are the two algorithms and their empirical evaluation.

---

## Connection to Research Questions (RQ Mapping)

| RQ | Scope | Contribution Addressed |
|---|---|---|
| RQ1 — Feasibility of automated sprint planning | Can the platform run all 5 phases autonomously? | Validates both algorithms function end-to-end |
| RQ2 — Performance vs. human baseline | Kendall's tau, Gini, backlog coverage | Direct evaluation of Contributions 1 and 2 |
| RQ3 — Human practitioner perception (TAM) | Perceived Usefulness, Ease of Use, Attitude, Intention | Sociotechnical validation of both algorithms in mixed mode |

---

## References to Design Document

- Contribution 1 maps to: design-doc.md §8.2 (Prioritisation Phase Detail)
- Contribution 2 maps to: design-doc.md §9 (Assignment Strategy)

Both sections currently describe simplified baseline implementations. The algorithms
above supersede those baselines as the research-grade designs to be implemented and
evaluated.
