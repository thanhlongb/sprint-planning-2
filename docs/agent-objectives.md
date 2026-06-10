# Agent-Specific Objective Functions

**Version:** 1.0
**Date:** 2026-06-08
**Project:** SP2 — Sprint Planning with Human-AI Agents
**Source:** `src/platform/app/agent_objectives.py` (workspace: `t_13885d73`)
**Related:** [Mutation Algebra + Agent Contract](mutation-algebra-and-agent-contract.md)

---

## 1. Purpose

`agent_objectives.py` implements domain-specific scoring functions for three agent personas — **Frontend**, **Backend**, and **QA**. Each persona evaluates backlog items through its own lens, producing different priorities from the same input. These priorities drive structured mutation proposals (ADD, REMOVE, MODIFY) that the agent can propose during round-robin sprint negotiation.

### Why three different scoring functions?

A Frontend agent should naturally rate UI/UX items higher than backend infrastructure items. A QA agent should flag untested or buggy items as highest priority. Without persona-specific objectives, all agents would produce identical rankings — eliminating the value of multi-agent negotiation.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    agent_objective()                     │
│  ┌───────────────────────────────────────────────────┐  │
│  │           1. Resolve persona                      │  │
│  │   AgentContext.resolved_persona → persona enum    │  │
│  └─────────────────┬─────────────────────────────────┘  │
│                    ▼                                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │           2. Score every backlog item             │  │
│  │   _SCORER[persona](item, sprint_goal) → [0,1]    │  │
│  └─────────────────┬─────────────────────────────────┘  │
│                    ▼                                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │           3. Classify mutations                   │  │
│  │   score ≥ 0.50  →  ADD (if not in sprint)        │  │
│  │   score < 0.25  →  REMOVE (if in sprint)         │  │
│  │   score 0.25–0.50 → MODIFY (if in sprint,         │  │
│  │                     borderline)                   │  │
│  └─────────────────┬─────────────────────────────────┘  │
│                    ▼                                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │           4. Generate justifications              │  │
│  │   _build_justification() — template-based,        │  │
│  │   persona-tagged, LLM integration point           │  │
│  └─────────────────┬─────────────────────────────────┘  │
│                    ▼                                      │
│             list[Mutation]                                │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Personas

### 3.1 Persona Inference

Personas are inferred from agent name and role (heuristic), with explicit override available:

| Agent Name Contains | Inferred Persona |
|---------------------|-----------------|
| `frontend`, `fe`, `ui`, `ux` | `FRONTEND` |
| `qa`, `test`, `quality` | `QA` |
| `backend`, `be`, `api`, `data` | `BACKEND` |

**Role-based fallback:** `PRODUCT_OWNER` → `FRONTEND`, everything else → `BACKEND`.

**Override:** Set `AgentContext.persona` explicitly to bypass inference.

### 3.2 Label Sets

Each persona has a curated set of labels it considers relevant:

| Persona | Relevant Labels |
|---------|----------------|
| **FRONTEND** | `ui`, `frontend`, `ux`, `design`, `css`, `component`, `responsive`, `accessibility`, `animation`, `style` |
| **BACKEND** | `backend`, `api`, `database`, `data`, `server`, `auth`, `security`, `performance`, `infra`, `scaling`, `integration` |
| **QA** | `testing`, `qa`, `e2e`, `integration-test`, `unit-test`, `bug`, `tech-debt`, `regression`, `coverage` |

Label relevance is computed as a Jaccard-like ratio: `intersection / max(|item_labels|, 1)`.

---

## 4. Scoring Formulas

All scores are clamped to `[0.0, 1.0]`. Priority is mapped to: `HIGH=1.0`, `MEDIUM=0.6`, `LOW=0.3`.

### 4.1 Frontend: UI/UX Focus

```
score = 0.60 × label_relevance(ui_labels)
      + 0.15 × priority_score
      + 0.25 × goal_similarity
```

- **Dominant term:** label relevance (60%) — items matching `ui`, `frontend`, `ux`, etc. score highest.
- **Goal similarity** (25%) uses word overlap between item title/description and the sprint goal text.
- A UI item with `HIGh priority` and goal alignment scores ~0.85. A backend-only item with no UI labels scores ~0.45.

### 4.2 Backend: Data Integrity + Business Value

```
score = 0.45 × label_relevance(backend_labels)
      + 0.40 × priority_score
      + 0.15 × goal_similarity
      + 0.10  bonus if item contains data-integrity keywords
             ("data", "validation", "integrity", "consistency",
              "migration", "schema")
```

- **Priority-heavy** (40%) — business value drives backend scoring more than any other persona.
- **Data-integrity bonus** (10% flat) triggers on keywords in title/description. This creates a clear separation between pure-infra items and data-related items.
- A `HIGh`-priority migration item with `backend` labels hits ~0.90. A frontend-only item scores ~0.45.

### 4.3 QA: Inverse Test Coverage Risk

```
score = 0.50 × risk_score
      + 0.30 × priority_score
      + 0.15 × label_relevance(qa_labels)
      + 0.05 × goal_similarity

risk_score:
  1.0  if item has "bug" or "tech-debt" label
  0.2  if item has "testing", "qa", "e2e", etc. label
  0.7  otherwise (untested)
```

- **Risk dominates** (50%): bugs and tech-debt score highest (risk=1.0). Well-tested items score lowest (risk=0.2). Untested items score moderate (risk=0.7).
- **Goal similarity is minimal** (5%) — QA cares about risk regardless of sprint goal alignment.
- A `HIGh`-priority bug hits ~0.90. A well-tested, low-priority item scores ~0.30.

---

## 5. Mutation Generation

### 5.1 Thresholds

| Condition | Mutation Type | Threshold |
|-----------|--------------|-----------|
| Item **not** in sprint, score ≥ `add_threshold` | `ADD` | 0.50 (default) |
| Item **in** sprint, score < `remove_threshold` | `REMOVE` | 0.25 (default) |
| Item **in** sprint, `remove_threshold` ≤ score < `add_threshold` | `MODIFY` | borderline |

Thresholds are configurable via `agent_objective(top_n, add_threshold, remove_threshold)`.

### 5.2 Output: Mutation Objects

```python
@dataclass
class Mutation:
    mutation_type: MutationType   # ADD | REMOVE | MODIFY
    item_id: str                  # Backlog item ID
    score: float                  # Agent's score [0.0, 1.0]
    priority_rank: int            # 0-indexed rank among all scored items
    updates: dict | None          # For MODIFY: field→new_value
    justification: str            # NL explanation with [Persona] tag
    item_data: dict | None        # Full item dict for ADD proposals
```

### 5.3 Justification Templates

Justifications are persona-tagged templates (e.g., `[Frontend] Adding 'Dashboard' — addresses UI impact needs...`). The function `_build_justification()` is designed as an **LLM integration point**: the template is a fallback; the architecture supports replacing it with an LLM call to produce richer, discussion-aware justifications.

---

## 6. API Reference

### 6.1 `agent_objective(agent_id, context, *, top_n=10, add_threshold=0.5, remove_threshold=0.25) → list[Mutation]`

Main entry point. Scores all backlog items against the agent's persona, classifies into mutations, and returns the top-N ordered by descending score.

**Parameters:**
- `agent_id` (str): Agent identifier (participant_id or slot_id).
- `context` (AgentContext): Full agent context.
- `top_n` (int): Max mutations to return (default 10).
- `add_threshold` (float): Minimum score to propose ADD.
- `remove_threshold` (float): Maximum score to propose REMOVE.

**Returns:** Ordered list of `Mutation` objects (highest priority first).

### 6.2 `score_items(context) → list[dict]`

Convenience function. Scores all backlog items for an agent context and returns them augmented with an `agent_score` field, sorted descending.

### 6.3 `AgentContext`

```python
@dataclass
class AgentContext:
    agent_id: str                         # Required
    agent_name: str = ""                  # For persona inference
    agent_role: str = "DEVELOPER"         # For persona fallback
    discussion: str = ""                  # Full transcript
    backlog_items: list[dict] = []        # All backlog items
    current_sprint: list[str] = []        # Sprint item IDs
    sprint_goal: str = ""                 # For goal similarity
    persona: AgentPersona | None = None   # Explicit override
```

### 6.4 `AgentPersona.from_role_and_name(role, name) → AgentPersona`

Static method for persona inference. Use before constructing `AgentContext` if you need to know the persona upfront.

---

## 7. Integration Guide

### 7.1 Pattern A: Per-Agent Turn Augmentation (round-robin)

Called after each agent's turn in the discussion phase. The agent's NL response becomes context; mutations are extracted and attached as `objective_proposals` alongside the NL response actions.

```python
# Inside _handle_round_robin_discussion(), after _request_turn():
ctx = AgentContext(
    agent_id=slot.participant_id,
    agent_name=slot.name,
    agent_role=slot.role,
    discussion=discussion_text,
    backlog_items=backlog_items,
    current_sprint=working_items,
    sprint_goal=session.sprint_goal,
)
mutations = agent_objective(ctx.agent_id, ctx, top_n=3)
turn_response["objective_proposals"] = [
    {
        "type": m.mutation_type.value,
        "item_id": m.item_id,
        "justification": m.justification,
        "score": m.score,
        "source": "agent_objective",
    }
    for m in mutations
]
```

Reference: `integration_sketch.py → augment_turn_with_objective()`.

### 7.2 Pattern B: Pre-Discussion Mutation Seeding

Called before the first round-robin round. Generates initial mutation proposals for every agent, seeding the discussion with structured proposals.

```python
proposals = {}
for slot in joined_slots:
    ctx = AgentContext(
        agent_id=slot.participant_id,
        agent_name=slot.name,
        agent_role=slot.role,
        backlog_items=backlog_items,
        current_sprint=working_items,
        sprint_goal=session.sprint_goal,
    )
    proposals[ctx.agent_id] = agent_objective(ctx.agent_id, ctx, top_n=5)
```

Reference: `integration_sketch.py → generate_agent_proposals()`.

---

## 8. Relationship to Mutation Algebra Contract

The [mutation-algebra-and-agent-contract.md](mutation-algebra-and-agent-contract.md) defines the **full algebra** (ADD, REMOVE, SWAP, REORDER, RESCOPE) and the agent I/O contract for the discussion phase. `agent_objectives.py` implements a **scoring subset**:

| Feature | Contract Spec | agent_objectives.py |
|---------|--------------|-------------------|
| Mutation types | ADD, REMOVE, SWAP, REORDER, RESCOPE | ADD, REMOVE, MODIFY (subset) |
| Agent roles | FRONTEND, BACKEND, QA | FRONTEND, BACKEND, QA |
| Scoring approach | Additive bonuses + base_score = α·goal_similarity + β·priority | Weighted: label_relevance + priority + goal_similarity |
| Justification | LLM-generated | Template-based (LLM integration point documented) |
| Capacity awareness | Yes (via `capacity` field) | Not yet — scored items don't check SP budget |

The `MODIFY` mutation type here maps loosely to `RESCOPE` + field modifications in the full algebra. SWAP and REORDER are not generated by the scoring function (they require combinatorial reasoning across item pairs) — they come from the NL discussion layer, parsed by the mutation parser.

---

## 9. Design Decisions

| Decision | Rationale |
|----------|-----------|
| Additive scoring, not multiplicative | Additive makes it easy to compare mutation impact across personas. Multiplicative would make the aggregator's conflict resolution harder. |
| Template-based justifications with `[Persona]` tag | Deterministic, testable, clearly attributable. LLM integration point is documented for future upgrade. |
| Three mutation types, not five | SWAP and REORDER require pairwise comparison (A vs B) rather than per-item scoring. They're generated at the NL discussion layer, not the objective layer. |
| `MODIFY` for borderline items | Items that score between ADD and REMOVE thresholds are "meh" — the agent sees potential but wants adjustment. |
| Default thresholds: 0.50 ADD, 0.25 REMOVE | Conservative: only clear winners get proposed for addition, only clear losers for removal. Reduces noise in multi-agent negotiation. |

---

## 10. Test Coverage

18 tests in `test_agent_objectives.py` cover:

- **AC1 (Different priorities):** Frontend vs Backend score divergence, QA bug prioritization, mutation set uniqueness across personas
- **AC2 (Valid mutations):** All item_ids exist in backlog, REMOVE targets sprint items, ADD targets non-sprint items, scores in [0,1], ranks sequential
- **AC3 (Domain-appropriate justifications):** Persona tag presence, item title reference, non-empty
- **Edge cases:** Empty backlog, empty sprint goal, top_n limit, persona inference (8 variants), QA inverse risk logic, explicit persona override

Run: `cd workspace && python -m pytest test_agent_objectives.py -v`

---

## 11. Future Work

1. **LLM-driven justifications.** Replace `_build_justification()` template with an LLM call that consumes the discussion transcript for richer, context-aware justifications.
2. **Capacity-aware scoring.** Factor sprint capacity into scoring — don't propose ADD if SP budget is exhausted without also proposing compensating REMOVEs.
3. **SWAP/REORDER generation.** Extend scoring to identify candidate swaps (high-score not-in-sprint vs low-score in-sprint pairs) and priority-based reordering.
4. **Tunable thresholds per persona.** Backend might want a higher ADD threshold (conservative on scope creep); QA might want a lower REMOVE threshold (keep buggy items in). Currently global but parameterized.
