# Unified Action Schema and API Signature Specification

**Version:** 1.0  
**Module:** `your_turn` — shared LLM prompt builder and response parser for round-robin sprint planning agents  
**Status:** Draft  
**Date:** 2026-06-10

---

## 1. Overview

This document defines the canonical output schema, prompt-builder, and response-parser for all agents participating in the round-robin `your_turn` discussion loop (US-41). Every agent that implements `your_turn` MUST produce output conforming to this schema and SHOULD use the shared `build_your_turn_prompt` / `parse_your_turn_response` functions.

The schema is the contract between the LLM and the platform.  The parser is the only validator — the platform trusts the parser's output after it passes the parsed struct back as `artifact`.

---

## 2. The Unified Action JSON Schema

### 2.1 Top-Level Object

```jsonc
{
  "message": "string, required, 1-3 sentence explanation of the agent's reasoning",
  "actions": "array of Action, required (can be empty)",
  "done":    "boolean, required, true when the agent has no further proposals"
}
```

| Field     | Type               | Required | Description |
|-----------|--------------------|----------|-------------|
| `message` | `string`           | yes      | Human-readable rationale, 1–3 sentences, in the agent's persona voice. |
| `actions` | `array of Action`  | yes      | Zero or more proposed actions. May be empty if the agent has nothing to propose. |
| `done`    | `boolean`          | yes      | `true` → agent has nothing more to contribute this discussion round. `false` → agent may have further ideas in a later invocation. Must default to `true` when `actions` is empty. |

---

### 2.2 Action Object

Every action has three **required** fields.  Additional fields are **action-type-specific** (see §2.3).

```jsonc
{
  "type":   "string, required — one of: add, remove, modify, volunteer, object",
  "target": "string, required — the item_id this action applies to",
  "justification": "string, required — 1-sentence natural-language reason for the action"
}
```

| Field            | Type     | Required | Description |
|------------------|----------|----------|-------------|
| `type`           | `string` | yes      | Action category. One of: `add`, `remove`, `modify`, `volunteer`, `object`. |
| `target`         | `string` | yes      | The `item_id` this action applies to. For `add` actions, this is the **proposed** item's id. |
| `justification`  | `string` | yes      | One sentence explaining **why** the action is proposed. |

---

### 2.3 Action-Type-Specific Fields

#### `add`

Propose a new backlog item that should exist but is missing.

```jsonc
{
  "type": "add",
  "target": "LLM-AGENT-ADD-1",
  "justification": "We need a cache invalidation story to avoid stale reads in production.",
  "item": {
    "item_id":      "LLM-AGENT-ADD-1",  // string, required, must match target
    "title":        "string, required",
    "description":  "string, required, 1-2 sentences",
    "priority":     "HIGH | MEDIUM | LOW, required",
    "story_points": "integer 1..13 required (Fibonacci preferred: 1,2,3,5,8,13)",
    "labels":       "array of string, required (can be empty [])",
    "dependencies": "array of string (item_ids), required (can be empty [])"
  }
}
```

_Constraints on `item`:_
- `item_id` must equal `target`.
- `priority` must be uppercase: `HIGH`, `MEDIUM`, or `LOW`.
- `story_points` must be an integer 1–13.
- No field inside `item` may be `null`.

#### `remove`

Remove an existing item from the sprint.

```jsonc
{
  "type": "remove",
  "target": "ITEM-4",
  "justification": "This item duplicates ITEM-7 and doesn't advance the sprint goal."
}
```

No additional fields.

#### `modify`

Change a field on an existing item.

```jsonc
{
  "type": "modify",
  "target": "ITEM-3",
  "justification": "This story needs more points — it's really an 8, not a 3.",
  "field":     "story_points",  // string, required
  "new_value": 8                // any, required — type must match the field
}
```

_Allowed `field` names:_ `title`, `description`, `priority`, `story_points`, `labels`, `dependencies`, `assignee`.

`new_value` must be compatible:
- `priority` → string: `HIGH` | `MEDIUM` | `LOW`
- `story_points` → integer 1–13
- `labels` / `dependencies` → array of strings
- `title` / `description` / `assignee` → string

#### `volunteer`

Signal willingness to be assigned to an item.

```jsonc
{
  "type": "volunteer",
  "target": "ITEM-2",
  "justification": "This involves data pipeline work which is my main expertise."
}
```

No additional fields.

#### `object`

Object to an existing assignment on fairness, expertise, or workload grounds.

```jsonc
{
  "type": "object",
  "target": "ITEM-5",
  "justification": "This item requires front-end work which is outside my skill set."
}
```

No additional fields.

---

### 2.4 Validation Constraints (parser-level)

When the parser processes the LLM output (§4), it applies these rules:

| Rule | Description |
|------|-------------|
| R1   | `type` must be one of the `allowed_actions` set the caller passes in. Unknown types are silently dropped with a log warning. |
| R2   | `target` must be a non-empty string. Actions with missing `target` are dropped. |
| R3   | For `add` actions: `item` must be a dict with all required fields; `item.item_id` must equal `target`. Invalid `add` actions are dropped. |
| R4   | For `modify` actions: `field` and `new_value` must both be present. Invalid `modify` actions are dropped. |
| R5   | If `done` is absent or not a boolean, default to `true` when `actions` is empty, `false` otherwise. |
| R6   | The entire JSON parse failure gracefully returns `{message: "", actions: [], done: true}` — the agent takes no action that round. |

---

### 2.5 Full Example

An invocation during the *assignment* phase where a developer volunteers for one item, objects to another, and proposes a new story-point estimate:

```json
{
  "message": "I'm a good fit for the batch-pipeline story since I built last quarter's ETL. I'm less comfortable with the admin UI which is better suited to a front-end dev. Also, ITEM-3 feels bigger than 3 points — more like 8.",
  "actions": [
    {
      "type": "volunteer",
      "target": "ITEM-2",
      "justification": "I built the existing ETL pipeline and can own this end-to-end."
    },
    {
      "type": "object",
      "target": "ITEM-5",
      "justification": "Admin UI requires React expertise which isn't in my skill set."
    },
    {
      "type": "modify",
      "target": "ITEM-3",
      "justification": "This involves three services and cross-cutting auth — realistically an 8.",
      "field": "story_points",
      "new_value": 8
    }
  ],
  "done": false
}
```

---

## 3. Function: `build_your_turn_prompt`

### 3.1 Signature

```python
def build_your_turn_prompt(
    sprint_context: SprintContext,
    board_items: BoardItems,
    persona: AgentPersona,
) -> str:
    ...
```

### 3.2 Input Types

#### `SprintContext` (TypedDict)

```python
class SprintContext(TypedDict):
    sprint_goal:      str                        # e.g. "Ship real-time dashboard v2"
    round:            int                        # 0-based discussion round number
    phase:            Literal["recommendation", "assignment"]
    allowed_actions:  list[str]                  # e.g. ["add","remove","modify","volunteer","object"]
    participants:     list[Participant]           # all session participants (name, role)
    discussion_so_far: list[DiscussionMessage]    # last N messages from current round
    human_messages:   list[HumanMessage]          # recent human participant notes
```

#### `BoardItems` (TypedDict)

```python
class BoardItems(TypedDict):
    working_items:  list[BacklogItem]       # items currently in the sprint
    backlog_items:  list[BacklogItem]       # full backlog (first 20 for reference)
    assignments:    dict[str, str]          # item_id → participant_id (or "" for unassigned)
```

#### `AgentPersona` (TypedDict)

```python
class AgentPersona(TypedDict):
    name:                str               # e.g. "llm-dev-agent"
    role:                Literal["PRODUCT_OWNER", "DEVELOPER"]
    specialties:         list[str]         # e.g. ["backend", "API", "Python"]
    seniority:           str               # e.g. "senior", "mid", "junior"
    max_assignments:     int               # workload cap
    current_assignments: int               # items already assigned to this agent
```

### 3.3 Return Value

A fully rendered LLM prompt string combining a persona-specific system prompt with a context-rich user message. The prompt instructs the LLM to output ONLY valid JSON conforming to the schema in §2.

### 3.4 Behaviour

1. Select the system prompt template based on `persona.role` (`PRODUCT_OWNER` or `DEVELOPER`).
2. Render the template, substituting persona fields (specialties, seniority, workload, allowed actions, phase description).
3. Bullet-format the board items and assignments into a human-readable markdown section.
4. Append the discussion transcript and human messages as "Additional context".
5. Append the closing instruction: `"Return ONLY valid JSON with message, actions, and done fields."`
6. Return the full prompt string.

### 3.5 System Prompt Templates

#### PRODUCT_OWNER template

```
You are an experienced Product Owner participating in an Agile sprint planning
round-robin discussion.

Your job is to reason about the current sprint backlog and propose concrete
actions to improve it.

You are in the {phase} phase.
- If phase is "recommendation": focus on what items should be in the sprint —
  add missing items that advance the sprint goal, remove items that don't
  align, or modify existing items (adjust story points, priority, or scope).
- If phase is "assignment": focus on who should work on what — object to
  mismatched assignments where an item is assigned to someone without the
  right expertise.

Allowed action types: {allowed_actions}

Return ONLY a valid JSON object with these fields:
  - "message": brief human-readable explanation (1-2 sentences, in character
    as Product Owner)
  - "actions": list of action objects. Each has "type", "target", "justification".
    See the schema for type-specific fields.
  - "done": true if you have no more proposals, false if you might have more
    ideas later

Do NOT output markdown fences or commentary — only valid JSON.
Do not include null values.
```

#### DEVELOPER template

```
You are a {seniority} software developer with specialties in {specialties}.
You are participating in an Agile sprint planning round-robin discussion.

Your job is to reason about the sprint backlog from your developer perspective
and propose concrete actions.

You are in the {phase} phase.
- If phase is "recommendation": focus on what items should be in the sprint —
  do items match your expertise? Are any items missing?
- If phase is "assignment": focus on who should work on what — volunteer for
  items that match your specialties and workload capacity, object to items
  assigned to you that don't align with your expertise.

Your workload limit: {max_assignments} items.
Your current assignments: {current_assignments}.

Allowed action types: {allowed_actions}

Return ONLY a valid JSON object with these fields:
  - "message": brief human-readable explanation (1-2 sentences, in character
    as a developer)
  - "actions": list of action objects. Each has "type", "target", "justification".
    See the schema for type-specific fields.
  - "done": true if you have no more proposals, false if you might have more
    ideas later

Do NOT output markdown fences or commentary — only valid JSON.
Do not include null values.
```

---

## 4. Function: `parse_your_turn_response`

### 4.1 Signature

```python
def parse_your_turn_response(
    raw_response: str,
    allowed_actions: list[str] | None = None,
) -> YourTurnOutput:
    ...
```

### 4.2 Return Type

```python
class Action(TypedDict):
    type:          str
    target:        str
    justification: str
    # type-specific optional fields:
    item:          NotRequired[BacklogItem]       # only for "add"
    field:         NotRequired[str]               # only for "modify"
    new_value:     NotRequired[Any]               # only for "modify"

class YourTurnOutput(TypedDict):
    message: str          # always a string, empty string on parse failure
    actions: list[Action] # always a list, empty list on parse failure
    done:    bool         # always a bool
```

### 4.3 Behaviour

1. **Extract JSON** from the raw LLM response:
   - Strip markdown fences (` ```json ` / ` ``` `).
   - Find the first `{` and matching `}` by bracket-depth counting.
   - Parse with `json.loads`.
   - If extraction or parsing fails → return `{"message": "", "actions": [], "done": True}` (R6).

2. **Validate top-level**:
   - The parsed value must be a `dict`. If not → return empty safe default.
   - Read `message` (coerce to `str`, default `""`).
   - Read `actions` (coerce to `list`, default `[]`).
   - Read `done` (coerce to `bool`, default `True` if actions is empty else `False`, per R5).

3. **Filter and validate each action**:
   - Skip non-dict elements in the actions list.
   - Skip actions whose `type` is not in `allowed_actions` (R1), log a warning.
   - Skip actions with empty or missing `target` (R2).
   - For `add` actions: check that `item` is a dict with `item_id == target`; drop if invalid (R3).
   - For `modify` actions: check that `field` and `new_value` are present; drop if invalid (R4).

4. **Return** the validated `YourTurnOutput`.

### 4.4 Graceful Degradation

Every failure path returns a safe default: `{message: "", actions: [], done: True}`. The caller never sees an uncaught exception and the agent simply "passes" that round.

---

## 5. Implementation Notes

### 5.1 Shared Module Location

Both agents should import from a single shared module to avoid drift:

```
src/agents/llm_agent/your_turn.py
```

Signature of the shared public API:

```
from llm_agent.your_turn import (
    build_your_turn_prompt,
    parse_your_turn_response,
    SprintContext,
    BoardItems,
    AgentPersona,
    YourTurnOutput,
    Action,
)
```

### 5.2 Migration Path from Current Code

The current `_handle_your_turn` in both `llm-po-agent/app/main.py` and `llm-dev-agent/app/main.py` manually constructs prompts and parses responses. The migration:

1. Move the system-prompt templates and parsing logic into `llm_agent/your_turn.py`.
2. Replace the inline `system_prompt = _YOUR_TURN_*_SYSTEM_PROMPT.format(...)` with `build_your_turn_prompt(...)`.
3. Replace the inline `_parse_your_turn_response(raw, allowed_actions)` with the shared `parse_your_turn_response(...)`.
4. Normalise action-type strings from `add_item`/`remove_item`/`modify_item` → `add`/`remove`/`modify` in both the LLM prompts and the allowed-actions lists.

### 5.3 Backward Compatibility

The `allowed_actions` parameter controls what types the parser accepts. If existing platform code still supplies `["add_item", "remove_item", "modify_item", "volunteer", "object"]`, the parser will simply reject the new short-form actions unless both lists are passed. Transition by updating the platform to send the short-form list first, then deprecating the long-form variants in a follow-up release.

---

## 6. Test Vectors

### 6.1 Valid parse

Input:
```
{"message": "Looks good.", "actions": [{"type": "add", "target": "IT-1", "justification": "Needed for compliance.", "item": {"item_id": "IT-1", "title": "Audit log", "description": "Add audit log", "priority": "HIGH", "story_points": 5, "labels": ["backend"], "dependencies": []}}], "done": true}
```

Expected output shape:
```python
{
    "message": "Looks good.",
    "actions": [
        {
            "type": "add",
            "target": "IT-1",
            "justification": "Needed for compliance.",
            "item": {
                "item_id": "IT-1",
                "title": "Audit log",
                "description": "Add audit log",
                "priority": "HIGH",
                "story_points": 5,
                "labels": ["backend"],
                "dependencies": [],
            },
        }
    ],
    "done": True,
}
```

### 6.2 Invalid action type (filtered out)

Input: `{"message":"ok","actions":[{"type":"delete","target":"X","justification":"bad"}],"done":true}`

Expected (with `allowed_actions=["add","remove","modify","volunteer","object"]`):
```python
{"message": "ok", "actions": [], "done": True}
```

### 6.3 Missing `done` (default infer)

Input: `{"message":"ok","actions":[]}`

Expected:
```python
{"message": "ok", "actions": [], "done": True}
```

### 6.4 Completely unparseable

Input: `"Sorry, I can't help with that."`

Expected:
```python
{"message": "", "actions": [], "done": True}
```
