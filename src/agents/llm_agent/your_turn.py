"""Shared your_turn prompt builder and response parser for round-robin agents.

Provides a canonical implementation of the unified action schema defined in
docs/your-turn-unified-action-schema.md.  All agents that implement `your_turn`
MUST use these functions to produce output conforming to the schema.

Usage:
    from llm_agent.your_turn import (
        build_your_turn_prompt,
        parse_your_turn_response,
        SprintContext,
        BoardItems,
        AgentPersona,
        YourTurnOutput,
        Action,
    )

    prompt = build_your_turn_prompt(sprint_ctx, board_items, persona)
    raw = await complete_async(prompt, system_prompt=prompt.split("\n\n")[0])
    result = parse_your_turn_response(raw, allowed_actions)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

log = logging.getLogger(__name__)

# ── Type aliases ──────────────────────────────────────────────────────────────

# Short-form action types are canonical.  Long-form aliases accepted during
# transition (see _ACTION_TYPE_ALIASES).
_ACTION_TYPES = ("add", "remove", "modify", "volunteer", "object")
_ACTION_TYPE_ALIASES: dict[str, str] = {
    "add_item": "add",
    "remove_item": "remove",
    "modify_item": "modify",
}

Role = Literal["PRODUCT_OWNER", "DEVELOPER"]
Phase = Literal["recommendation", "assignment"]


class SprintContext(dict):
    """Context about the sprint and discussion round."""

    sprint_goal: str
    round: int
    phase: Phase
    allowed_actions: list[str]
    participants: list[dict]
    discussion_so_far: list[dict]
    human_messages: list[dict]


class BoardItems(dict):
    """Current board state."""

    working_items: list[dict]
    backlog_items: list[dict]
    assignments: dict[str, str]


class AgentPersona(dict):
    """The agent's persona specification."""

    name: str
    role: Role
    specialties: list[str]
    seniority: str
    max_assignments: int
    current_assignments: int


class Action(dict):
    """A single proposed action."""

    type: str
    target: str
    justification: str


class YourTurnOutput(dict):
    """Validated output from parse_your_turn_response."""

    message: str
    actions: list[Action]
    done: bool


# ── System prompt templates ───────────────────────────────────────────────────

_PO_SYSTEM_PROMPT = """\
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
  - "message": a brief human-readable explanation of your reasoning (1-2 sentences,
    in character as Product Owner)
  - "actions": a list of action objects. Each action has:
      - "type": one of the allowed action types listed above
      - "target": the item ID this action applies to (string)
      - "justification": a natural-language justification (1 sentence explaining why)
      For "add" actions, also include "item" with:
        - "item_id": unique ID string (e.g. "LLM-PO-ADD-1" — must match target)
        - "title": concise title
        - "description": 1-2 sentence description
        - "priority": "HIGH", "MEDIUM", or "LOW"
        - "story_points": integer 1-13 (use Fibonacci: 1,2,3,5,8,13)
        - "labels": list of strings
        - "dependencies": list of item_id strings (or empty list)
      For "modify" actions, also include:
        - "field": the field name to modify (e.g. "priority", "story_points", "title")
        - "new_value": the new value
  - "done": true if you have no more proposals, false if you might have more ideas
    in a later round

Do NOT output markdown fences or commentary — only valid JSON.
Do not include null values."""

_DEV_SYSTEM_PROMPT = """\
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
  - "message": a brief human-readable explanation of your reasoning (1-2 sentences,
    in character as a developer)
  - "actions": a list of action objects. Each action has:
      - "type": one of the allowed action types listed above
      - "target": the item ID this action applies to (string)
      - "justification": a natural-language justification (1 sentence explaining why)
      For "add" actions, also include "item" with:
        - "item_id": unique ID string (must match target)
        - "title": concise title
        - "description": 1-2 sentence description
        - "priority": "HIGH", "MEDIUM", or "LOW"
        - "story_points": integer 1-13 (use Fibonacci: 1,2,3,5,8,13)
        - "labels": list of strings
        - "dependencies": list of item_id strings (or empty list)
      For "modify" actions, also include:
        - "field": the field name to modify
        - "new_value": the new value
  - "done": true if you have no more proposals, false if you might have more ideas
    in a later round

Do NOT output markdown fences or commentary — only valid JSON.
Do not include null values."""

# ── Public API ────────────────────────────────────────────────────────────────


def build_your_turn_prompt(
    sprint_context: SprintContext,
    board_items: BoardItems,
    persona: AgentPersona,
) -> str:
    """Build a complete LLM prompt for the your_turn round-robin discussion.

    Args:
        sprint_context: Sprint goal, round, phase, participants, discussion, human notes.
        board_items: Working items, backlog items, and assignments.
        persona: Agent name, role, specialties, seniority, workload bounds.

    Returns:
        A fully rendered prompt string combining a persona-specific system prompt
        with a context-rich user message.  The prompt instructs the LLM to output
        ONLY valid JSON conforming to the unified action schema.
    """
    # 1. Select and render the system prompt template.
    role = persona.get("role", "DEVELOPER")
    phase = sprint_context.get("phase", "recommendation")
    allowed_actions = sprint_context.get("allowed_actions", list(_ACTION_TYPES))
    allowed_str = ", ".join(allowed_actions)

    if role == "PRODUCT_OWNER":
        system_prompt = _PO_SYSTEM_PROMPT.format(
            phase=phase,
            allowed_actions=allowed_str,
        )
    else:
        specialties = persona.get("specialties", [])
        system_prompt = _DEV_SYSTEM_PROMPT.format(
            seniority=persona.get("seniority", "mid"),
            specialties=", ".join(specialties) if specialties else "general software engineering",
            phase=phase,
            max_assignments=persona.get("max_assignments", 3),
            current_assignments=persona.get("current_assignments", 0),
            allowed_actions=allowed_str,
        )

    # 2. Build the user message with context.
    round_num = sprint_context.get("round", 0)
    sprint_goal = sprint_context.get("sprint_goal", "")
    participants = sprint_context.get("participants", [])

    # ── Board items ───────────────────────────────────────────────────────
    working_items = board_items.get("working_items", [])
    backlog_items = board_items.get("backlog_items", [])
    assignments = board_items.get("assignments", {})

    working_summary = _format_items(working_items).rstrip() or "(no items)"
    backlog_summary = (
        _format_items(backlog_items[:20]).rstrip() or "(no backlog items)"
    )

    assignment_lines = []
    for iid, pid in assignments.items():
        assignment_lines.append(f"  - {iid} → {pid or 'unassigned'}")
    assignments_summary = "\n".join(assignment_lines) or "(no assignments)"

    # ── Participants ──────────────────────────────────────────────────────
    participant_summary = ", ".join(
        f"{p.get('name', '?')} ({p.get('role', '?')})"
        for p in participants
    )

    # ── Discussion so far ─────────────────────────────────────────────────
    discussion = sprint_context.get("discussion_so_far", [])
    discussion_text = "\n".join(
        f"  [{d.get('sender_name', '?')}]: {d.get('content', str(d))}"
        for d in discussion[-10:]
    ) or "(no discussion yet)"

    # ── Human participant messages ────────────────────────────────────────
    human_msgs = sprint_context.get("human_messages", [])
    human_notes = "\n".join(
        f"  - {m.get('sender_name', 'participant')}: {m.get('content', '')}"
        for m in human_msgs[-5:]
    ) or "(none)"

    # ── Persona-specific extras ───────────────────────────────────────────
    persona_extras = ""
    if role == "DEVELOPER":
        specialties = persona.get("specialties", [])
        persona_extras = (
            f"My specialties: {', '.join(specialties) if specialties else 'general software engineering'}.\n"
            f"My current assignments ({persona.get('current_assignments', 0)}/{persona.get('max_assignments', 3)}): "
            f"{_my_items_text(persona.get('name', ''), assignments) or 'none'}.\n\n"
        )

    user_prompt = (
        f"Round {round_num} of the {phase} discussion.\n\n"
        f"Sprint goal: {sprint_goal}\n\n"
        f"Participants: {participant_summary}\n\n"
        f"Backlog (first 20 items):\n{backlog_summary}\n\n"
        f"Current working items:\n{working_summary}\n\n"
        f"Current assignments:\n{assignments_summary}\n\n"
        f"{persona_extras}"
        f"Discussion so far this round:\n{discussion_text}\n\n"
        f"Human participant messages:\n{human_notes}\n\n"
        f"As a {persona.get('role', 'DEVELOPER').replace('_', ' ').title()}, "
        f"what actions do you propose? "
        f"Allowed actions: {allowed_str}.\n"
        "Return ONLY valid JSON with message, actions, and done fields."
    )

    # Return system prompt + separator + user message so the caller can pass
    # system_prompt to complete_async() and the user_prompt as the user message.
    return system_prompt + "\n\n---\n\n" + user_prompt


def build_system_and_user_prompts(
    sprint_context: SprintContext,
    board_items: BoardItems,
    persona: AgentPersona,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) as separate strings.

    This is the preferred pair for callers that pass system_prompt and
    user_prompt separately to the LLM client (complete_async).
    """
    full = build_your_turn_prompt(sprint_context, board_items, persona)
    parts = full.split("\n\n---\n\n", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], full


def parse_your_turn_response(
    raw_response: str,
    allowed_actions: list[str] | None = None,
) -> YourTurnOutput:
    """Parse and validate LLM output into the standard {message, actions, done} format.

    Every failure path returns a safe default — the caller never sees an
    uncaught exception and the agent simply "passes" that round.

    Args:
        raw_response: Raw LLM output (may contain markdown fences, commentary).
        allowed_actions: If set, only actions whose type is in this set are
            kept.  Both short-form (``add``) and long-form (``add_item``)
            types are accepted and normalised.

    Returns:
        A ``YourTurnOutput`` dict with ``message``, ``actions``, and ``done``.
    """
    allowed = _normalise_allowed_actions(allowed_actions)

    try:
        extracted = _extract_json(raw_response)
        parsed = json.loads(extracted)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("your_turn.json_parse_failed exc=%s raw=%r", exc, raw_response[:200])
        return YourTurnOutput(message="", actions=[], done=True)

    if not isinstance(parsed, dict):
        log.warning("your_turn.not_a_dict type=%s", type(parsed).__name__)
        return YourTurnOutput(message="", actions=[], done=True)

    # ── Extract top-level fields ──────────────────────────────────────────
    message = str(parsed.get("message", ""))
    raw_actions = parsed.get("actions", [])
    if not isinstance(raw_actions, list):
        raw_actions = []

    # ── Filter and validate each action ───────────────────────────────────
    valid_actions: list[Action] = []
    for a in raw_actions:
        if not isinstance(a, dict):
            continue

        a_type = _normalise_action_type(a.get("type", ""))
        if a_type not in allowed:
            log.warning("your_turn.skipped_action type=%r not in allowed=%s", a_type, allowed)
            continue

        target = a.get("target", "")
        if not target or not isinstance(target, str):
            log.warning("your_turn.missing_target action=%r", a.get("type"))
            continue

        justification = str(a.get("justification", "")) or str(a.get("reason", ""))

        action: Action = Action(
            type=a_type,
            target=target,
            justification=justification,
        )

        # ── Type-specific validation ──────────────────────────────────
        if a_type == "add":
            item = a.get("item")
            if not isinstance(item, dict):
                log.warning("your_turn.add_missing_item target=%s", target)
                continue
            if item.get("item_id") != target:
                log.warning(
                    "your_turn.add_item_id_mismatch expected=%s got=%s",
                    target, item.get("item_id"),
                )
                continue
            action["item"] = item

        elif a_type == "modify":
            if "field" not in a:
                log.warning("your_turn.modify_missing_field target=%s", target)
                continue
            if "new_value" not in a:
                log.warning("your_turn.modify_missing_new_value target=%s", target)
                continue
            action["field"] = a["field"]
            action["new_value"] = a["new_value"]

        valid_actions.append(action)

    # ── Infer 'done' ─────────────────────────────────────────────────────
    # R5: if done is absent or not a boolean, default to true when actions
    # is empty, false otherwise.
    raw_done = parsed.get("done")
    if isinstance(raw_done, bool):
        done = raw_done
    else:
        done = len(valid_actions) == 0

    return YourTurnOutput(message=message, actions=valid_actions, done=done)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _extract_json(text: str) -> str:
    """Extract the JSON portion from possibly-markdown-fenced LLM output."""
    # Strip markdown fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()

    if text.startswith(("{", "[")):
        return text

    # Find first { or [ and matching closing bracket by depth counting
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start != -1:
            depth = 0
            for i, ch in enumerate(text[start:], start=start):
                if ch == start_char:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                    if depth == 0:
                        return text[start : i + 1]
    return text


def _normalise_action_type(raw_type: str) -> str:
    """Normalise action type to canonical short form.

    Accepts both ``add_item`` → ``add`` and ``add`` → ``add``.
    """
    t = raw_type.strip().lower()
    return _ACTION_TYPE_ALIASES.get(t, t)


def _normalise_allowed_actions(allowed: list[str] | None) -> set[str]:
    """Build the set of canonical action types, including both forms during transition."""
    if allowed is None:
        # Default to all canonical types
        return set(_ACTION_TYPES)

    normalised: set[str] = set()
    for a in allowed:
        normalised.add(_normalise_action_type(a))
    return normalised


def _format_items(items: list[dict]) -> str:
    """Format a list of item dicts into a human-readable bullet list."""
    lines = []
    for it in items:
        lines.append(
            f"  - {it.get('item_id', '?')}: {it.get('title', '?')} "
            f"[priority={it.get('priority', '?')}, sp={it.get('story_points', '?')}, "
            f"labels={it.get('labels', [])}]"
        )
    return "\n".join(lines)


def _my_items_text(agent_name: str, assignments: dict[str, str]) -> str:
    """Return a comma-separated list of item_ids assigned to agent_name."""
    my_items = [iid for iid, pid in assignments.items() if pid == agent_name]
    return ", ".join(my_items) if my_items else "none"
