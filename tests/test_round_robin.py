#!/usr/bin/env python3
"""US-41: Unit tests for round-robin discussion handler.

Tests the _handle_round_robin_discussion function in isolation using
mocked A2A client and comm bus.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Test data ─────────────────────────────────────────────────────────────────

@pytest.fixture
def session_snap() -> Any:
    """Fixture: a _SessionSnap for testing."""
    from app.phase_orchestrator import _SessionSnap
    return _SessionSnap(
        id="test-session-1",
        sprint_goal="Ship OAuth + user profiles",
        template="sprint_planning_v2",
        sprint_capacity=50,
    )


@pytest.fixture
def slots() -> Any:
    """Fixture: list of _SlotSnap ordered by join time."""
    from app.phase_orchestrator import _SlotSnap
    return [
        _SlotSnap(
            id="slot-2", participant_id="dev-1", name="dev-agent",
            role="DEVELOPER", slot_type="AGENT",
            endpoint="http://dev-agent:8002/a2a", status="joined",
        ),
        _SlotSnap(
            id="slot-1", participant_id="po-1", name="po-agent",
            role="PRODUCT_OWNER", slot_type="AGENT",
            endpoint="http://po-agent:8001/a2a", status="joined",
        ),
    ]


@pytest.fixture
def backlog_items() -> list[dict]:
    return [
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
            "labels": ["auth", "security", "api"],
            "dependencies": [],
        },
        {
            "item_id": "T-003",
            "title": "CSRF protection",
            "description": "CSRF tokens on all endpoints.",
            "priority": "HIGH",
            "story_points": 3,
            "labels": ["security", "api"],
            "dependencies": [],
        },
    ]


# ── Test helpers ──────────────────────────────────────────────────────────────


class MockA2AResult:
    """Simulates A2AClient.send_task return value."""
    def __init__(self, ok: bool, artifact: dict[str, Any] | None = None):
        self.ok = ok
        self.artifact = artifact


async def run_round_robin(
    session_snap,
    slots,
    backlog_items,
    selected_items,
    agent_responses: dict[str, list[dict[str, Any]]],
    *,
    turn_timeout_seconds: int = 30,
    max_rounds: int = 5,
    synthesize_proposals: bool = True,
) -> tuple[list[str], dict[str, str], int]:
    """Run _handle_round_robin_discussion with mocked A2A responses.

    agent_responses maps slot.id → ordered list of response dicts.
    Each response dict has: message, actions, done.
    Returns (final_items, final_assignments, round_count).
    """
    from app.phase_orchestrator import _handle_round_robin_discussion

    # Track call count per slot for response sequencing
    call_counts: dict[str, int] = {}

    async def mock_send_task(endpoint, task_type, session_ctx, payload, **kwargs):
        # Find which slot this endpoint belongs to
        slot_id = None
        for s in slots:
            if s.endpoint == endpoint:
                slot_id = s.id
                break

        if slot_id is None:
            return MockA2AResult(ok=False)

        responses = agent_responses.get(slot_id, [])
        idx = call_counts.get(slot_id, 0)
        call_counts[slot_id] = idx + 1

        if idx < len(responses):
            return MockA2AResult(ok=True, artifact=responses[idx])
        # Default: done, empty
        return MockA2AResult(ok=True, artifact={"message": "", "actions": [], "done": True})

    with (
        patch("app.phase_orchestrator._a2a.send_task", side_effect=mock_send_task),
        patch("app.comm_bus.publish_comm_event", new_callable=AsyncMock),
        patch("app.recommender.recommend", side_effect=lambda backlog_items, sprint_goal, total_capacity: backlog_items),
    ):
        result = await _handle_round_robin_discussion(
            session=session_snap,
            slots=slots,
            context="recommendation",
            allowed_actions=["add_item", "remove_item", "modify_item"],
            turn_timeout_seconds=turn_timeout_seconds,
            max_rounds=max_rounds,
            synthesize_proposals=synthesize_proposals,
            backlog_items=backlog_items,
            selected_items=selected_items,
            assignments={},
            phase_id="rec-1",
            phase_name="Recommendation",
            phase_history=[],
        )
        return result


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consensus_round_zero(session_snap, slots, backlog_items):
    """Both agents say done=True in round 0 → 1 round, immediate consensus."""
    agent_responses = {
        "slot-1": [{"message": "LGTM", "actions": [], "done": True}],
        "slot-2": [{"message": "Good", "actions": [], "done": True}],
    }

    items, _, rounds = await run_round_robin(
        session_snap, slots, backlog_items,
        selected_items=["T-001", "T-002"],
        agent_responses=agent_responses,
    )

    assert rounds == 1, f"Expected 1 round, got {rounds}"
    assert "T-001" in items
    assert "T-002" in items


@pytest.mark.asyncio
async def test_consensus_after_two_rounds(session_snap, slots, backlog_items):
    """Round 0: one agent not done. Round 1: both done → 2 rounds."""
    agent_responses = {
        "slot-1": [
            {"message": "Proposal", "actions": [], "done": False},
            {"message": "Now done", "actions": [], "done": True},
        ],
        "slot-2": [
            {"message": "Thinking...", "actions": [], "done": False},
            {"message": "OK done", "actions": [], "done": True},
        ],
    }

    _, _, rounds = await run_round_robin(
        session_snap, slots, backlog_items,
        selected_items=["T-001"],
        agent_responses=agent_responses,
    )

    assert rounds == 2, f"Expected 2 rounds, got {rounds}"


@pytest.mark.asyncio
async def test_max_rounds_enforced(session_snap, slots, backlog_items):
    """Agents never say done → forced consensus at max_rounds."""
    agent_responses = {
        "slot-1": [
            {"message": "more!", "actions": [], "done": False},
            {"message": "still more", "actions": [], "done": False},
            {"message": "and more", "actions": [], "done": False},
        ],
        "slot-2": [
            {"message": "keep going", "actions": [], "done": False},
            {"message": "dont stop", "actions": [], "done": False},
            {"message": "believe", "actions": [], "done": False},
        ],
    }

    _, _, rounds = await run_round_robin(
        session_snap, slots, backlog_items,
        selected_items=["T-001"],
        agent_responses=agent_responses,
        max_rounds=3,
    )

    assert rounds == 3, f"Expected 3 rounds (max_rounds), got {rounds}"


@pytest.mark.asyncio
async def test_role_ordering(session_snap, slots, backlog_items):
    """PO speaks before DEVELOPER (sorted by _ROLE_PRIORITY)."""
    call_order: list[str] = []
    original_send = None

    # We'll verify call order by capturing slot IDs
    async def mock_send_task(endpoint, task_type, session_ctx, payload, **kwargs):
        for s in slots:
            if s.endpoint == endpoint:
                call_order.append(s.id)
                break
        return MockA2AResult(ok=True, artifact={"message": "", "actions": [], "done": True})

    with (
        patch("app.phase_orchestrator._a2a.send_task", side_effect=mock_send_task),
        patch("app.comm_bus.publish_comm_event", new_callable=AsyncMock),
        patch("app.recommender.recommend", side_effect=lambda bl, sg, tc: bl),
    ):
        from app.phase_orchestrator import _handle_round_robin_discussion
        await _handle_round_robin_discussion(
            session=session_snap,
            slots=slots,
            context="recommendation",
            allowed_actions=["add_item"],
            turn_timeout_seconds=30,
            max_rounds=1,
            synthesize_proposals=False,
            backlog_items=backlog_items,
            selected_items=["T-001"],
            assignments={},
            phase_id="rec-1",
            phase_name="Recommendation",
            phase_history=[],
        )

    # PO (slot-1) should come before DEV (slot-2) in role ordering
    # But note: slots fixture has DEV first, PO second in list order.
    # The function sorts by _role_sort_key, so PO should be first.
    assert call_order[0] == "slot-1", f"Expected PO (slot-1) first, got {call_order[0]}"
    assert call_order[1] == "slot-2", f"Expected DEV (slot-2) second, got {call_order[1]}"


@pytest.mark.asyncio
async def test_platform_synthesis_adds_items(session_snap, slots, backlog_items):
    """When agents propose add_item actions, platform synthesizes them."""
    new_item = {
        "type": "add_item",
        "item": {
            "item_id": "NEW-01",
            "title": "Two-factor auth",
            "description": "Add TOTP-based 2FA.",
            "priority": "HIGH",
            "story_points": 5,
            "labels": ["auth", "security"],
            "dependencies": [],
        },
    }

    agent_responses = {
        "slot-1": [{"message": "Add 2FA", "actions": [new_item], "done": True}],
        "slot-2": [{"message": "", "actions": [], "done": True}],
    }

    items, _, rounds = await run_round_robin(
        session_snap, slots, backlog_items,
        selected_items=["T-001"],
        agent_responses=agent_responses,
    )

    assert rounds == 1
    assert "NEW-01" in items, f"Platform should have added NEW-01 from agent proposal. Items: {items}"


@pytest.mark.asyncio
async def test_done_skips_in_round_two(session_snap, slots, backlog_items):
    """Participant who says done in round 0 is skipped in round 1."""
    agent_responses = {
        "slot-1": [{"message": "Done", "actions": [], "done": True}],
        "slot-2": [
            {"message": "Still thinking", "actions": [], "done": False},
            {"message": "Now done", "actions": [], "done": True},
        ],
    }

    _, _, rounds = await run_round_robin(
        session_snap, slots, backlog_items,
        selected_items=["T-001"],
        agent_responses=agent_responses,
    )

    # Round 0: PO done, DEV not done → 1 round
    # Round 1: PO skipped (already done), DEV says done → consensus after 2 rounds
    assert rounds == 2, f"Expected 2 rounds, got {rounds}"
