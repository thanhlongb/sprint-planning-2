# Mutation Algebra + Agent Objective Function Contract

**Version:** 1.0
**Date:** 2026-06-05
**Project:** SP2 — Sprint Planning with Human-AI Agents
**Status:** Design Spec

---

## 1. Domain Model (Existing, for Reference)

Backlog items use the `BacklogItem` schema (from `src/platform/app/phase_orchestrator.py`):

```json
{
  "item_id":       "B-042",
  "title":         "Add multi-factor authentication",
  "description":   "Implement TOTP-based MFA for login flow...",
  "priority":      "HIGH",
  "story_points":  8,
  "labels":        ["security", "backend", "auth"],
  "dependencies":  ["B-018"]
}
```

The **sprint list** is an ordered list of `item_id` strings referencing the backlog. Position matters — the sprint list is the working set that agents mutate.

The **sprint capacity** is a total story-point ceiling (sum of all participants' `story_points`). Mutations that would exceed capacity MUST be accompanied by compensating mutations or explicit justification.

---

## 2. Mutation Algebra

### 2.1 Universal Mutation Envelope

Every mutation is a JSON object with this structure:

```json
{
  "type":          "ADD",
  "target_key":    "B-042",
  "payload":       { ... },
  "justification": "MFA is a blocking dependency for the compliance milestone..."
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `type` | yes | One of: `ADD`, `REMOVE`, `SWAP`, `REORDER`, `RESCOPE` |
| `target_key` | yes | The `item_id` of the primary item affected |
| `payload` | depends on type | Type-specific parameters (see below) |
| `justification` | yes | Natural-language rationale. Free text, no character limit but agents SHOULD keep under 500 chars. |

### 2.2 Mutation Types

#### ADD(key, position?)

Add an item from the backlog to the sprint list.

```json
{
  "type": "ADD",
  "target_key": "B-042",
  "payload": {
    "position": 3
  },
  "justification": "This is the highest-priority security item not yet in the sprint."
}
```

**Payload fields:**

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `position` | no | int (1-indexed) | Insertion position in the sprint list. If omitted, appends to end. If > len(list) + 1, appends to end. |

**Pre-conditions:**
- `target_key` MUST exist in the full backlog.
- `target_key` MUST NOT already be in the sprint list.

**Post-conditions:**
- Sprint list gains `target_key` at `position` (or end).
- If capacity exceeded, the mutation is still applied — capacity violations are flagged for downstream resolution (aggregator / PO).

**Edge cases:**
- `position = 1` on empty list: becomes sole item.
- `position > len(list) + 1`: treated as append.
- Duplicate ADD for same key: second ADD is a no-op or rejected by platform validation.

---

#### REMOVE(key, reason)

Remove an item from the sprint list.

```json
{
  "type": "REMOVE",
  "target_key": "B-027",
  "payload": {},
  "justification": "Redundant with B-035 which covers the same API surface with better test coverage."
}
```

**Payload fields:** none required. `justification` carries the reason.

**Pre-conditions:**
- `target_key` MUST be in the sprint list.

**Post-conditions:**
- Sprint list no longer contains `target_key`.
- Remaining items shift to close the gap (positions re-indexed).

**Edge cases:**
- Last remaining item REMOVEd: sprint list becomes empty. Valid state — treated as "reset" scenario in aggregator.
- REMOVE on item not in sprint: rejected by platform validation.

---

#### SWAP(remove_key, add_key)

Atomically replace one sprint item with another from the backlog. This is logically equivalent to `REMOVE(remove_key)` + `ADD(add_key)` but atomic — both succeed or both fail.

```json
{
  "type": "SWAP",
  "target_key": "B-027",
  "payload": {
    "add_key": "B-042",
    "position": null
  },
  "justification": "B-042 addresses the same risk as B-027 but with lower story-point cost (8 vs 13)."
}
```

**Payload fields:**

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `add_key` | yes | string | Item to add from backlog. |
| `position` | no | int or null | Where to insert the new item. `null` (default) = same position as removed item. |

**Pre-conditions:**
- `target_key` MUST be in the sprint list (the item being removed).
- `add_key` MUST exist in the backlog.
- `add_key` MUST NOT already be in the sprint list.

**Post-conditions:**
- `target_key` removed, `add_key` inserted. Net list length unchanged.
- The swap is atomic — partial application is not allowed.

**Edge cases:**
- SWAP where `add_key == target_key`: rejected. Self-swap is a no-op.
- SWAP where `add_key` IS in sprint list: rejected. Use REORDER instead.
- Position `null`: inherits `target_key`'s old position.

---

#### REORDER(key, new_position)

Change the position of an existing sprint item.

```json
{
  "type": "REORDER",
  "target_key": "B-042",
  "payload": {
    "new_position": 1
  },
  "justification": "This is a blocking dependency — must be completed before any other sprint item."
}
```

**Payload fields:**

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `new_position` | yes | int (1-indexed) | Target position. |

**Pre-conditions:**
- `target_key` MUST be in the sprint list.

**Post-conditions:**
- `target_key` moved to `new_position`. Items between old and new position shift accordingly.

**Edge cases:**
- `new_position == current_position`: no-op. Platform MAY skip application.
- `new_position > len(list)`: clamped to last position.
- `new_position < 1`: clamped to 1.

---

#### RESCOPE(key, new_sp)

Propose a different story-point estimate for a sprint item. This does NOT change the item's `story_points` in the backlog — it is a proposal that requires PO or aggregator approval.

```json
{
  "type": "RESCOPE",
  "target_key": "B-042",
  "payload": {
    "new_sp": 5
  },
  "justification": "After reviewing the API spec, the OAuth integration already exists — this is a thin wrapper, not a full implementation."
}
```

**Payload fields:**

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `new_sp` | yes | int ≥ 1 | Proposed story-point estimate. |

**Pre-conditions:**
- `target_key` MUST be in the sprint list.
- `target_key` MUST have a `story_points` field set.

**Post-conditions:**
- The sprint list's effective SP for this item is `new_sp` for capacity calculations (pending approval).
- The backlog item's canonical `story_points` is NOT modified until explicitly committed.

**Edge cases:**
- `new_sp == current_sp`: no-op. Platform SHOULD reject.
- `new_sp = 0`: rejected. Minimum is 1.
- `new_sp` would push sprint over capacity: flagged. Aggregator may pair with compensating REMOVEs.
- RESCOPE on an item with no `story_points`: treated as initial estimate. Backlog `story_points` set to `new_sp`.

---

### 2.3 Mutation Validity Rules

The platform enforces these rules on mutation application:

1. **Referential integrity:** `target_key` and `add_key` must reference real backlog items.
2. **No duplicates:** ADD cannot insert an item already in the sprint list.
3. **Capacity flagging:** mutations that cause capacity overflow are applied but flagged.
4. **Atomic SWAP:** SWAP is all-or-nothing.
5. **Idempotency:** applying the same mutation twice has no effect on the second application.

### 2.4 Mutation Ordering and Composability

Mutations in a batch are applied sequentially in the order the agent provides. The platform:
1. Validates each mutation against the state *after* all preceding mutations have been applied.
2. If any mutation fails validation, the entire batch is rejected and the sprint list is reverted to its pre-batch state (transactional rollback).

This means agents must order their mutations carefully:
- Good: `[SWAP(B-027, B-042), REORDER(B-042, 1)]` — swap first, then reposition the newly inserted item.
- Bad: `[REORDER(B-042, 1), SWAP(B-027, B-042)]` — REORDER fails if B-042 wasn't yet in the list.

---

## 3. Agent Objective Function Contract

### 3.1 Input Specification

Each agent receives a structured prompt with:

```json
{
  "transcript": {
    "current_round": 2,
    "history": [
      {
        "round": 1,
        "sender": "FrontendDev",
        "message": "We need to prioritize the login redesign — it's blocking the dashboard work.",
        "actions": [
          {"type": "ADD", "target_key": "B-055", "payload": {"position": 1}, "justification": "..."}
        ]
      }
    ],
    "this_round_messages": [ ... ]
  },
  "backlog": [
    {"item_id": "B-001", "title": "...", "description": "...", "priority": "HIGH", "story_points": 8, "labels": ["frontend", "ui"], "dependencies": []},
    {"item_id": "B-002", "title": "...", "description": "...", "priority": "MEDIUM", "story_points": 5, "labels": ["backend", "api"], "dependencies": ["B-001"]}
  ],
  "sprint_list": ["B-001", "B-003", "B-007"],
  "capacity": {
    "total_sp": 34,
    "used_sp": 21,
    "remaining_sp": 13
  },
  "agent_role": "FRONTEND",
  "participants": [
    {"name": "FrontendDev", "role": "DEVELOPER", "specialties": ["frontend", "React", "TypeScript"], "capacity_sp": 15},
    {"name": "BackendDev", "role": "DEVELOPER", "specialties": ["backend", "Python", "API"], "capacity_sp": 20},
    {"name": "QAEngineer", "role": "QA", "specialties": ["testing", "e2e", "integration"], "capacity_sp": 10}
  ]
}
```

| Field | Description |
|-------|-------------|
| `transcript` | Discussion context: previous rounds + current round messages. Each message includes sender, text, and any structured actions they proposed. |
| `backlog` | Full backlog — all candidate items with their canonical fields. |
| `sprint_list` | Current sprint list A (ordered list of `item_id` strings). |
| `capacity` | Sprint-level capacity snapshot. |
| `agent_role` | One of `FRONTEND`, `BACKEND`, `QA`. Determines weighting (see 3.3). |
| `participants` | All session participants with their specialties and individual capacity. |

### 3.2 Output Specification

Each agent outputs an ordered list of mutations, each with NL justification. The order reflects the agent's preference — most important mutation first.

```json
{
  "agent_role": "BACKEND",
  "message": "The current sprint list over-indexes on UI polish. We should swap B-055 (login redesign) for B-042 (MFA) — MFA is a security requirement, not cosmetic.",
  "mutations": [
    {
      "type": "SWAP",
      "target_key": "B-055",
      "payload": {"add_key": "B-042", "position": null},
      "justification": "B-042 (MFA) is a security prerequisite. B-055 (login redesign) can be deferred."
    },
    {
      "type": "REMOVE",
      "target_key": "B-033",
      "payload": {},
      "justification": "B-033 is a 'nice to have' analytics dashboard. Sprint capacity is tight."
    },
    {
      "type": "RESCOPE",
      "target_key": "B-018",
      "payload": {"new_sp": 3},
      "justification": "B-018's API migration is mostly done — only the final endpoint remains."
    }
  ],
  "done": false
}
```

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `agent_role` | yes | string | Must match the agent's configured role. |
| `message` | yes | string | Free-text contribution to the discussion thread. |
| `mutations` | yes | array of Mutation | Ordered list — position in array = agent's preference ranking. |
| `done` | yes | boolean | `true` if agent believes the sprint list is optimal and has no further proposals. Signals consensus readiness. |

### 3.3 Agent Type Weighting

Each agent type applies a **role-specific objective function** when evaluating backlog items. The function scores each candidate item, and mutations are proposed to maximize the weighted sum of the sprint list.

Common base score (shared by all agents):

```
base_score(item) = α · goal_similarity(item, sprint_goal) + β · priority_score(item)
```

Role-specific modifiers modulate `α` and `β` and introduce bonus terms:

#### FRONTEND Agent

Weights items matching frontend/UI/UX labels higher. Penalizes items with no frontend surface.

```
frontend_score(item) = base_score(item)
    + γ_fe · label_match(item, {"frontend", "ui", "ux", "design", "css", "react", "typescript"})
    - δ_fe · (1 if item has no frontend-relevant label else 0)

where:
  label_match  = fraction of item.labels intersecting the FE label set
  γ_fe = 0.15  (bonus for frontend relevance)
  δ_fe = 0.05  (penalty for purely non-frontend items)
```

#### BACKEND Agent

Weights items matching backend/data/infrastructure labels. Penalizes items that are purely cosmetic.

```
backend_score(item) = base_score(item)
    + γ_be · label_match(item, {"backend", "api", "database", "infra", "security", "python", "data"})
    - δ_be · (1 if item has only frontend labels else 0)

where:
  γ_be = 0.15
  δ_be = 0.05
```

#### QA Agent

Weights items by test coverage risk. Items with many dependencies, no tests, or high complexity score higher (more value in having them in sprint to test early).

```
qa_score(item) = base_score(item)
    + γ_qa · risk_factor(item)
    - δ_qa · (1 if item has zero dependencies else 0)

where:
  risk_factor(item) = min(1.0, (len(item.dependencies) * 0.1) + (sp_factor * 0.05))
  sp_factor = min(item.story_points or 5, 20)  # cap at 20
  γ_qa = 0.15
  δ_qa = 0.03  (penalty for items with no dependencies — low risk of integration bugs)
```

### 3.4 Mutation Preference Ordering

Agents order their mutation list by **impact on their role-specific score**:

1. Mutations that most improve the agent's weighted score come first.
2. Ties broken by: SWAP > ADD > REMOVE > RESCOPE > REORDER (higher-impact mutations first).
3. REORDER is lowest priority — ordering reflects execution preference, not composition.

The aggregator (platform) collects all agents' mutation lists and resolves conflicts (see future spec: platform aggregation design).

---

## 4. Example: Full Agent Output

### Scenario

**Sprint goal:** "Improve platform security posture and API reliability"
**Capacity:** 34 SP total, 21 used, 13 remaining
**Backlog:** 15 items (B-001 through B-015)
**Sprint list:** `["B-001", "B-003", "B-007", "B-008", "B-012"]`

### BACKEND Agent Output

```json
{
  "agent_role": "BACKEND",
  "message": "Current list misses critical API reliability items. B-003 and B-008 duplicate effort — B-014 supersedes both with a unified approach. We should also rescope B-012 downward; it's a config change, not a new service.",
  "mutations": [
    {
      "type": "SWAP",
      "target_key": "B-003",
      "payload": {
        "add_key": "B-014",
        "position": null
      },
      "justification": "B-014 (Unified API Gateway) subsumes B-003 (Rate Limiter) and B-008 (Auth Middleware). 13 SP for one item vs 8+8=16 SP for two. Higher cohesion, lower SP cost."
    },
    {
      "type": "REMOVE",
      "target_key": "B-008",
      "payload": {},
      "justification": "Covered by B-014 (SWAP above). Keeping both is redundant."
    },
    {
      "type": "ADD",
      "target_key": "B-010",
      "payload": {
        "position": 3
      },
      "justification": "Database connection pooling (B-010) is a prerequisite for API Gateway. Must precede B-014 in execution order. HIGH priority, 5 SP, well within remaining capacity."
    },
    {
      "type": "RESCOPE",
      "target_key": "B-012",
      "payload": {
        "new_sp": 2
      },
      "justification": "B-012 (Environment Config) is a YAML change and CI variable update — not 8 SP. No code changes required."
    },
    {
      "type": "REORDER",
      "target_key": "B-010",
      "payload": {
        "new_position": 1
      },
      "justification": "B-010 (DB Pooling) is a hard dependency for B-001, B-014, and B-012. Must execute first."
    }
  ],
  "done": false
}
```

### Expected post-application sprint list:

```
["B-010", "B-001", "B-014", "B-012"]  (B-012 rescoped to 2 SP)
```

Net SP: 5 (B-010) + 8 (B-001) + 13 (B-014) + 2 (B-012) = 28 SP. Within 34 SP capacity.

---

## 5. Edge Cases

### 5.1 Empty Sprint List

The sprint list starts empty (no items selected). All agents' first mutations will be ADD operations.

- The aggregator must handle the cold-start: no items to remove, swap, reorder, or rescope.
- FRONTEND agent proposes ADD for UI-blocking items.
- BACKEND agent proposes ADD for infrastructure prerequisites.
- QA agent proposes ADD for high-risk items with many dependencies.

The aggregator resolves overlaps — two agents proposing the same ADD is a consensus signal.

### 5.2 Full Capacity

When `remaining_sp = 0`, only mutations that do NOT increase SP usage are valid:

| Mutation | Allowed? | Notes |
|----------|----------|-------|
| ADD | No — rejected unless rescoped to fit | Platform rejects ADD when no capacity remains. |
| REMOVE | Yes | Frees capacity for subsequent rounds. |
| SWAP | Yes — if `add_key` SP ≤ `target_key` SP | Net-zero or negative SP change. |
| REORDER | Yes | No SP impact. |
| RESCOPE | Yes — if `new_sp ≤ current_sp` | Can free capacity by downward re-estimation. |

Agents should prioritize REMOVE/SWAP when at full capacity. The aggregator may relax capacity for one round if all agents propose capacity-exceeding ADDs with strong justifications — flagged for PO review.

### 5.3 Conflicting Mutations

Multiple agents may propose incompatible mutations in the same round. The aggregator (future spec) resolves conflicts. Conflict types:

| Conflict | Example | Resolution Strategy |
|----------|---------|---------------------|
| ADD vs REMOVE (same key) | A adds B-010, B removes B-010 | Majority vote. Tie → PO tiebreak. |
| SWAP vs SWAP (overlapping keys) | A swaps B-003→B-014, B swaps B-003→B-009 | Both applied simultaneously if targets distinct. If `remove_key` conflicts (both remove B-003), only one SWAP can apply — preference goes to proposal with higher role-specific score improvement. |
| RESCOPE vs RESCOPE (same key) | A: B-012 = 2 SP, B: B-012 = 5 SP | Median or PO choice. |
| REORDER vs REORDER (same key) | A: B-010→1, B: B-010→4 | Average (rounded) or first-proposed-wins. |

The mutation algebra is designed so that **all conflicts are detectable structurally** — no semantic analysis required. The aggregator sees `(mutation_type, target_key)` pairs and detects overlaps.

### 5.4 Agent Proposes Zero Mutations

```json
{
  "agent_role": "FRONTEND",
  "message": "Current sprint list is well-balanced. No changes needed from frontend perspective.",
  "mutations": [],
  "done": true
}
```

This is valid and counts as a consensus signal (`done: true`). The aggregator treats empty mutation lists as an endorsement of the current state.

### 5.5 Dangling References

If an agent proposes a mutation referencing an item that was removed in a previous round (by another agent), the mutation fails validation. The platform applies the batch transactionally — if any mutation in the batch fails, the entire batch is rejected. The agent's message still appears in the transcript; only the structural actions are discarded.

### 5.6 Circular Dependencies from REORDER

An agent might propose: `[REORDER(B-001, 2), REORDER(B-002, 1)]` — swapping two items' positions. This is valid because mutations are applied sequentially. After the first REORDER, B-001 is at position 2; after the second, B-002 is at position 1. Net effect: the two items swapped positions.

Agents SHOULD NOT propose position cycles of length > 2 — these are silently supported but degrade readability.

---

## 6. Alignment with Existing Round-Robin Protocol

The mutation algebra extends the existing round-robin action model (from `phase_orchestrator.py:1494 _apply_turn_actions`).

| Existing Action | Mutation Equivalent | Notes |
|-----------------|---------------------|-------|
| `add_item` | `ADD` | Backward-compatible. Existing `add_item` is a subset of `ADD` (no `position`). |
| `remove_item` | `REMOVE` | Backward-compatible. |
| `modify_item` | `RESCOPE` | `modify_item` allowed arbitrary field changes. `RESCOPE` is narrower (SP only). Other modifications (title, description, priority) are out of scope for the sprint negotiation phase. |
| *(none)* | `SWAP` | New — no existing equivalent. |
| *(none)* | `REORDER` | New — no existing equivalent. |

**Migration path:** The existing `add_item` / `remove_item` / `modify_item` actions in the round-robin protocol remain functional. The mutation algebra is a superset. Platform can accept both formats during the transition period, normalizing to mutation algebra internally.

**Parsing rule:** If `payload` contains `add_key`, it's a SWAP. If `payload` contains `new_position` and no `add_key`, it's a REORDER. If `payload` contains `new_sp`, it's a RESCOPE. Otherwise, `ADD` or `REMOVE` based on `type`.

---

## 7. JSON Schema (Formal)

### Mutation Union

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$defs": {
    "Mutation": {
      "oneOf": [
        {"$ref": "#/$defs/AddMutation"},
        {"$ref": "#/$defs/RemoveMutation"},
        {"$ref": "#/$defs/SwapMutation"},
        {"$ref": "#/$defs/ReorderMutation"},
        {"$ref": "#/$defs/RescopeMutation"}
      ]
    },
    "AddMutation": {
      "type": "object",
      "required": ["type", "target_key", "justification"],
      "properties": {
        "type": {"const": "ADD"},
        "target_key": {"type": "string", "minLength": 1},
        "payload": {
          "type": "object",
          "properties": {
            "position": {"type": "integer", "minimum": 1}
          }
        },
        "justification": {"type": "string", "minLength": 1}
      }
    },
    "RemoveMutation": {
      "type": "object",
      "required": ["type", "target_key", "justification"],
      "properties": {
        "type": {"const": "REMOVE"},
        "target_key": {"type": "string", "minLength": 1},
        "payload": {"type": "object"},
        "justification": {"type": "string", "minLength": 1}
      }
    },
    "SwapMutation": {
      "type": "object",
      "required": ["type", "target_key", "payload", "justification"],
      "properties": {
        "type": {"const": "SWAP"},
        "target_key": {"type": "string", "minLength": 1},
        "payload": {
          "type": "object",
          "required": ["add_key"],
          "properties": {
            "add_key": {"type": "string", "minLength": 1},
            "position": {"type": ["integer", "null"], "minimum": 1}
          }
        },
        "justification": {"type": "string", "minLength": 1}
      }
    },
    "ReorderMutation": {
      "type": "object",
      "required": ["type", "target_key", "payload", "justification"],
      "properties": {
        "type": {"const": "REORDER"},
        "target_key": {"type": "string", "minLength": 1},
        "payload": {
          "type": "object",
          "required": ["new_position"],
          "properties": {
            "new_position": {"type": "integer", "minimum": 1}
          }
        },
        "justification": {"type": "string", "minLength": 1}
      }
    },
    "RescopeMutation": {
      "type": "object",
      "required": ["type", "target_key", "payload", "justification"],
      "properties": {
        "type": {"const": "RESCOPE"},
        "target_key": {"type": "string", "minLength": 1},
        "payload": {
          "type": "object",
          "required": ["new_sp"],
          "properties": {
            "new_sp": {"type": "integer", "minimum": 1}
          }
        },
        "justification": {"type": "string", "minLength": 1}
      }
    }
  }
}
```

### Agent Output Envelope

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["agent_role", "message", "mutations", "done"],
  "properties": {
    "agent_role": {"enum": ["FRONTEND", "BACKEND", "QA"]},
    "message": {"type": "string"},
    "mutations": {
      "type": "array",
      "items": {"$ref": "#/$defs/Mutation"}
    },
    "done": {"type": "boolean"}
  }
}
```

---

## 8. Design Decisions Log

| Decision | Rationale |
|----------|-----------|
| SWAP is atomic, not REMOVE+ADD | Prevents orphaned state if only one side applies. Simplifies aggregator conflict detection. |
| RESCOPE is a proposal, not a mutation | Story points are owned by the PO's backlog. Agents can propose but cannot unilaterally rewrite estimates. |
| REORDER is lowest priority | Ordering is a scheduling concern. Agents signal execution order preferences but the aggregator optimizes for dependencies first. |
| Transactional batch application | Agents propose interdependent mutations. Partial application would produce invalid intermediate states. |
| `done` flag per agent, not per round | Agents may reach consensus at different times. The aggregator advances the round when all agents are `done` or timeout. |
| Role-specific scoring functions use additive bonuses, not multiplicative weights | Additive makes it trivial to compare mutation impact across agent types. Multiplicative would make the aggregator's job harder. |

---

## 9. References

- Parent task: `t_fb56d5ec` — ABN + dual-optimization decomposition
- Existing round-robin protocol: `src/platform/app/phase_orchestrator.py` (lines 1494–1558)
- A2A task contracts: `src/platform/app/a2a/models.py` (lines 68–109)
- BacklogItem schema: `src/platform/app/phase_orchestrator.py` (lines 131–145)
- Plan doc: `docs/plans/new-workflow-implementation.md`
- Related US: US-36 (Agent Contract v2), US-41 (Round-Robin Consensus)
