"""Unit tests for llm_agent.your_turn — prompt builder and response parser.

Tests:
  - System prompt format for both PO and DEV personas
  - User prompt format with correct context injection
  - Response parser: valid JSON, legacy action types, R1-R6 validation rules
  - Edge cases: empty actions, malformed JSON, missing fields
"""

from __future__ import annotations

import json
import sys
import os

# Ensure llm_agent is importable (it lives under src/agents, not src/platform)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "agents"))

import pytest
from llm_agent.your_turn import (
    build_your_turn_system_prompt,
    build_your_turn_user_prompt,
    build_your_turn_prompt,
    parse_your_turn_response,
    _ALLOWED_ACTIONS,
    _ALLOWED_LEGACY,
    _LEGACY_TO_SHORT,
    _normalise_action_type,
)
from llm_agent.your_turn import (
    SprintContext,
    BoardItems,
    AgentPersona,
    YourTurnOutput,
)


# ── Test fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def po_persona() -> AgentPersona:
    return {
        "name": "test-po",
        "role": "PRODUCT_OWNER",
        "specialties": [],
        "seniority": "senior",
        "max_assignments": 0,
        "current_assignments": 0,
    }


@pytest.fixture
def dev_persona() -> AgentPersona:
    return {
        "name": "test-dev",
        "role": "DEVELOPER",
        "specialties": ["backend", "Python"],
        "seniority": "senior",
        "max_assignments": 3,
        "current_assignments": 1,
    }


@pytest.fixture
def sprint_ctx() -> SprintContext:
    return {
        "sprint_goal": "Ship OAuth + user profiles",
        "round": 0,
        "phase": "recommendation",
        "allowed_actions": ["add", "remove", "modify", "volunteer", "object"],
        "participants": [
            {"name": "po-agent", "role": "PRODUCT_OWNER"},
            {"name": "dev-agent", "role": "DEVELOPER"},
        ],
        "discussion_so_far": [],
        "human_messages": [],
    }


@pytest.fixture
def board_items() -> BoardItems:
    return {
        "working_items": [
            {
                "item_id": "T-001",
                "title": "Add rate limiting",
                "description": "Rate limit login endpoint.",
                "priority": "HIGH",
                "story_points": 3,
                "labels": ["auth", "security"],
                "dependencies": [],
            },
        ],
        "backlog_items": [
            {
                "item_id": "T-001",
                "title": "Add rate limiting",
                "description": "Rate limit login endpoint.",
                "priority": "HIGH",
                "story_points": 3,
                "labels": ["auth", "security"],
                "dependencies": [],
            },
            {
                "item_id": "T-002",
                "title": "OAuth 2.0 social login",
                "description": "Google and GitHub OAuth.",
                "priority": "HIGH",
                "story_points": 8,
                "labels": ["auth", "api"],
                "dependencies": [],
            },
        ],
        "assignments": {},
    }


# ── Action normalisation tests ─────────────────────────────────────────────────

def test_normalise_short_form():
    """Short-form types pass through unchanged."""
    assert _normalise_action_type("add") == "add"
    assert _normalise_action_type("remove") == "remove"
    assert _normalise_action_type("modify") == "modify"
    assert _normalise_action_type("volunteer") == "volunteer"
    assert _normalise_action_type("object") == "object"


def test_normalise_legacy_form():
    """Legacy long-form types are converted to short-form."""
    assert _normalise_action_type("add_item") == "add"
    assert _normalise_action_type("remove_item") == "remove"
    assert _normalise_action_type("modify_item") == "modify"


def test_normalise_unknown():
    """Unknown types return None."""
    assert _normalise_action_type("bogus") is None
    assert _normalise_action_type("") is None


def test_allowed_actions_complete():
    """All allowed action types are covered."""
    assert _ALLOWED_ACTIONS == frozenset({"add", "remove", "modify", "volunteer", "object"})
    assert _ALLOWED_LEGACY == frozenset({"add_item", "remove_item", "modify_item"})


# ── System prompt tests ────────────────────────────────────────────────────────

def test_po_system_prompt_contains_phase(po_persona, sprint_ctx):
    prompt = build_your_turn_system_prompt(po_persona, sprint_ctx)
    assert "recommendation" in prompt
    assert "Product Owner" in prompt
    assert "allowed action types" in prompt.lower()


def test_dev_system_prompt_contains_specialties(dev_persona, sprint_ctx):
    prompt = build_your_turn_system_prompt(dev_persona, sprint_ctx)
    assert "backend, Python" in prompt
    assert "senior" in prompt
    assert "max_assignments" in prompt or "3" in prompt


def test_system_prompt_assignment_phase(po_persona, sprint_ctx):
    sprint_ctx["phase"] = "assignment"
    prompt = build_your_turn_system_prompt(po_persona, sprint_ctx)
    assert "assignment" in prompt


# ── User prompt tests ──────────────────────────────────────────────────────────

def test_user_prompt_contains_sprint_goal(po_persona, sprint_ctx, board_items):
    prompt = build_your_turn_user_prompt(sprint_ctx, board_items, po_persona)
    assert "Ship OAuth + user profiles" in prompt


def test_user_prompt_contains_items(po_persona, sprint_ctx, board_items):
    prompt = build_your_turn_user_prompt(sprint_ctx, board_items, po_persona)
    assert "T-001" in prompt
    assert "Add rate limiting" in prompt


def test_user_prompt_contains_round(po_persona, sprint_ctx, board_items):
    prompt = build_your_turn_user_prompt(sprint_ctx, board_items, po_persona)
    assert "Round 0" in prompt


def test_combined_prompt_includes_system_and_user(po_persona, sprint_ctx, board_items):
    prompt = build_your_turn_prompt(sprint_ctx, board_items, po_persona)
    assert "Product Owner" in prompt
    assert "T-001" in prompt
    assert "---" in prompt


# ── Response parser: happy path ────────────────────────────────────────────────

def test_parse_valid_response():
    raw = json.dumps({
        "message": "LGTM",
        "actions": [
            {"type": "add", "target": "NEW-1",
             "justification": "Critical for sprint goal",
             "item": {"item_id": "NEW-1", "title": "2FA", "description": "Add 2FA",
                      "priority": "HIGH", "story_points": 5, "labels": ["auth"],
                      "dependencies": []}},
        ],
        "done": False,
    })
    result = parse_your_turn_response(raw)
    assert result["message"] == "LGTM"
    assert len(result["actions"]) == 1
    assert result["actions"][0]["type"] == "add"
    assert result["actions"][0]["target"] == "NEW-1"
    assert result["done"] is False


def test_parse_empty_actions():
    raw = json.dumps({"message": "Nothing to add", "actions": [], "done": True})
    result = parse_your_turn_response(raw)
    assert result["message"] == "Nothing to add"
    assert result["actions"] == []
    assert result["done"] is True


# ── Response parser: legacy action types ───────────────────────────────────────

def test_parse_legacy_add_item():
    raw = json.dumps({
        "message": "Add this",
        "actions": [{
            "type": "add_item",
            "item_id": "OLD-1",
            "reason": "needed",
            "item": {"item_id": "OLD-1", "title": "X", "description": "Y",
                     "priority": "MEDIUM", "story_points": 3, "labels": [],
                     "dependencies": []},
        }],
        "done": True,
    })
    result = parse_your_turn_response(raw)
    assert len(result["actions"]) == 1
    assert result["actions"][0]["type"] == "add"
    assert result["actions"][0]["target"] == "OLD-1"


def test_parse_legacy_remove_item():
    raw = json.dumps({
        "message": "Remove",
        "actions": [{"type": "remove_item", "item_id": "T-099", "reason": "not needed"}],
        "done": True,
    })
    result = parse_your_turn_response(raw)
    assert len(result["actions"]) == 1
    assert result["actions"][0]["type"] == "remove"
    assert result["actions"][0]["target"] == "T-099"


# ── Response parser: R1 — unknown action types dropped ─────────────────────────

def test_r1_unknown_action_type_dropped():
    raw = json.dumps({
        "message": "test",
        "actions": [
            {"type": "bogus", "target": "X", "justification": "?"},
            {"type": "add", "target": "Y", "justification": "ok",
             "item": {"item_id": "Y", "title": "Y", "description": "Y",
                      "priority": "LOW", "story_points": 1, "labels": [],
                      "dependencies": []}},
        ],
        "done": False,
    })
    result = parse_your_turn_response(raw)
    assert len(result["actions"]) == 1
    assert result["actions"][0]["type"] == "add"


# ── Response parser: R2 — empty target dropped ─────────────────────────────────

def test_r2_empty_target_dropped():
    raw = json.dumps({
        "message": "test",
        "actions": [
            {"type": "remove", "target": "", "justification": "bad"},
            {"type": "remove", "target": "T-001", "justification": "good"},
        ],
        "done": True,
    })
    result = parse_your_turn_response(raw)
    assert len(result["actions"]) == 1
    assert result["actions"][0]["target"] == "T-001"


def test_r2_missing_target_key_dropped():
    raw = json.dumps({
        "message": "test",
        "actions": [
            {"type": "remove", "justification": "no target key"},
        ],
        "done": True,
    })
    result = parse_your_turn_response(raw)
    assert result["actions"] == []


# ── Response parser: R3 — add must have valid item ────────────────────────────

def test_r3_add_without_item_dropped():
    raw = json.dumps({
        "message": "test",
        "actions": [
            {"type": "add", "target": "X", "justification": "missing item"},
        ],
        "done": True,
    })
    result = parse_your_turn_response(raw)
    assert result["actions"] == []


def test_r3_add_item_id_mismatch_dropped():
    raw = json.dumps({
        "message": "test",
        "actions": [{
            "type": "add", "target": "X",
            "justification": "mismatch",
            "item": {"item_id": "Y", "title": "Y", "description": "Y",
                     "priority": "LOW", "story_points": 1, "labels": [],
                     "dependencies": []},
        }],
        "done": True,
    })
    result = parse_your_turn_response(raw)
    assert result["actions"] == []


# ── Response parser: R4 — modify must have field and new_value ─────────────────

def test_r4_modify_without_field_dropped():
    raw = json.dumps({
        "message": "test",
        "actions": [{
            "type": "modify", "target": "T-001",
            "justification": "change priority",
            "new_value": "LOW",
        }],
        "done": True,
    })
    result = parse_your_turn_response(raw)
    assert result["actions"] == []


def test_r4_modify_without_new_value_dropped():
    raw = json.dumps({
        "message": "test",
        "actions": [{
            "type": "modify", "target": "T-001",
            "justification": "change priority",
            "field": "priority",
        }],
        "done": True,
    })
    result = parse_your_turn_response(raw)
    assert result["actions"] == []


def test_r4_valid_modify_accepted():
    raw = json.dumps({
        "message": "test",
        "actions": [{
            "type": "modify", "target": "T-001",
            "justification": "lower priority",
            "field": "priority",
            "new_value": "LOW",
        }],
        "done": True,
    })
    result = parse_your_turn_response(raw)
    assert len(result["actions"]) == 1
    assert result["actions"][0]["field"] == "priority"
    assert result["actions"][0]["new_value"] == "LOW"


# ── Response parser: R5 — done default inference ──────────────────────────────

def test_r5_done_defaults_true_when_no_actions():
    raw = json.dumps({"message": "x", "actions": []})
    result = parse_your_turn_response(raw)
    assert result["done"] is True


def test_r5_done_defaults_false_when_actions_present():
    raw = json.dumps({
        "message": "x",
        "actions": [{
            "type": "remove", "target": "T-001", "justification": "x"
        }],
    })
    result = parse_your_turn_response(raw)
    assert result["done"] is False  # default: len(actions) > 0 → False


def test_r5_done_explicit_value_respected():
    raw = json.dumps({
        "message": "x",
        "actions": [{"type": "remove", "target": "T-001", "justification": "x"}],
        "done": True,
    })
    result = parse_your_turn_response(raw)
    assert result["done"] is True  # explicit True overrides default


# ── Response parser: R6 — total parse failure returns safe default ─────────────

def test_r6_malformed_json_returns_safe_default():
    result = parse_your_turn_response("not json at all {{{")
    assert result["message"] == ""
    assert result["actions"] == []
    assert result["done"] is True


def test_r6_wrong_type_returns_safe_default():
    result = parse_your_turn_response("[1, 2, 3]")
    assert result["message"] == ""
    assert result["actions"] == []
    assert result["done"] is True


def test_r6_empty_string_returns_safe_default():
    result = parse_your_turn_response("")
    assert result["message"] == ""
    assert result["actions"] == []
    assert result["done"] is True


# ── Response parser: markdown-wrapped JSON ─────────────────────────────────────

def test_parse_json_in_markdown_fence():
    raw = '```json\n{"message": "hi", "actions": [], "done": true}\n```'
    result = parse_your_turn_response(raw)
    assert result["message"] == "hi"
    assert result["done"] is True


def test_parse_json_with_text_before_and_after():
    raw = 'Here is my response: {"message": "ok", "actions": [], "done": true} Hope that helps!'
    result = parse_your_turn_response(raw)
    assert result["message"] == "ok"


# ── Integration-style test ─────────────────────────────────────────────────────

def test_full_round_trip_po():
    """Build a prompt, simulate an LLM response, parse it — end to end."""
    persona: AgentPersona = {
        "name": "po", "role": "PRODUCT_OWNER",
        "specialties": [], "seniority": "senior",
        "max_assignments": 0, "current_assignments": 0,
    }
    ctx: SprintContext = {
        "sprint_goal": "Ship auth features",
        "round": 1, "phase": "recommendation",
        "allowed_actions": ["add", "remove", "modify"],
        "participants": [{"name": "po", "role": "PRODUCT_OWNER"}],
        "discussion_so_far": [],
        "human_messages": [],
    }
    board: BoardItems = {
        "working_items": [],
        "backlog_items": [
            {"item_id": "A-1", "title": "MFA", "description": "Add MFA",
             "priority": "HIGH", "story_points": 5, "labels": ["auth"],
             "dependencies": []},
        ],
        "assignments": {},
    }

    system = build_your_turn_system_prompt(persona, ctx)
    user = build_your_turn_user_prompt(ctx, board, persona)

    assert "Product Owner" in system
    assert "Ship auth features" in user
    assert "A-1" in user

    # Simulate a plausible LLM response
    llm_response = json.dumps({
        "message": "I recommend adding MFA as it aligns with our auth sprint goal.",
        "actions": [
            {"type": "add", "target": "A-1", "justification": "Critical auth feature",
             "item": {
                 "item_id": "A-1", "title": "MFA", "description": "Add MFA",
                 "priority": "HIGH", "story_points": 5, "labels": ["auth"],
                 "dependencies": [],
             }},
        ],
        "done": False,
    })

    parsed = parse_your_turn_response(llm_response)
    assert parsed["message"] != ""
    assert len(parsed["actions"]) == 1
    assert parsed["actions"][0]["type"] == "add"
    assert parsed["done"] is False
