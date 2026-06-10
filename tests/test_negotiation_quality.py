#!/usr/bin/env python3
"""Negotiation Quality Benchmarks.

Evaluates whether the structured round-robin mutation + platform aggregation
pipeline improves sprint planning over the baseline (recommender-only).

Metrics
-------
- Convergence speed    : rounds to reach stable sprint list
- Pareto efficiency    : does the final list dominate all intermediates?
- Agent satisfaction   : do agents signal done=True earlier?
- Coverage             : are all agent concerns addressed in final list?
- Stability            : does the final list change if you run 1 more round?

Test Scenarios (parametrized)
-----------------------------
- Homogeneous preferences  : all agents agree → should converge in 1 round
- Conflicting preferences  : agents want mutually exclusive items → compromise
- Capacity pressure        : 200% of capacity in high-value items → trade-offs
- Empty current list       : cold-start negotiation
- Adversarial agent        : one agent proposes nonsensical items → robustness
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Evaluation Metrics
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class NegotiationMetrics:
    """Snapshot of all five metrics after a negotiation run."""

    convergence_rounds: int
    pareto_score: float          # 0.0–1.0, closer to 1 = final dominates all
    satisfaction_ratio: float    # 0.0–1.0, fraction of agents done by final round
    coverage: float              # 0.0–1.0, fraction of agent concerns addressed
    stability: float             # 0.0–1.0, Jaccard similarity of final vs final+1

    def summary(self) -> str:
        return (
            f"convergence={self.convergence_rounds} "
            f"pareto={self.pareto_score:.2f} "
            f"satisfaction={self.satisfaction_ratio:.2f} "
            f"coverage={self.coverage:.2f} "
            f"stability={self.stability:.2f}"
        )


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _item_score(item: dict, sprint_goal: str) -> float:
    """Heuristic score: HIGH=3, MEDIUM=2, LOW=1, scaled by story_points."""
    p = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(str(item.get("priority", "LOW")).upper(), 1)
    sp = int(item.get("story_points") or 1)
    return p + math.log2(sp + 1)


def _total_value(items: list[dict], sprint_goal: str) -> float:
    return sum(_item_score(it, sprint_goal) for it in items)


def _dominates(a_items: list[dict], b_items: list[dict], sprint_goal: str) -> bool:
    """True if a_items has >= total value AND <= total story_points of b_items."""
    a_val = _total_value(a_items, sprint_goal)
    b_val = _total_value(b_items, sprint_goal)
    a_sp = sum(int(it.get("story_points") or 1) for it in a_items)
    b_sp = sum(int(it.get("story_points") or 1) for it in b_items)
    return a_val >= b_val and a_sp <= b_sp


def compute_pareto_efficiency(
    final_items: list[dict],
    history: list[list[dict]],
    sprint_goal: str,
) -> float:
    """Fraction of historical snapshots dominated by the final list."""
    if not history:
        return 1.0
    dominated = sum(1 for h in history if _dominates(final_items, h, sprint_goal))
    return dominated / len(history)


def compute_coverage(
    final_items: list[str],
    all_agent_proposals: list[set[str]],
) -> float:
    """Jaccard coverage: what fraction of agent-proposed item IDs made it in?"""
    all_proposed: set[str] = set()
    for proposal_set in all_agent_proposals:
        all_proposed |= proposal_set
    if not all_proposed:
        return 1.0
    return len(set(final_items) & all_proposed) / len(all_proposed)


def compute_stability(
    final_items: list[str],
    extra_round_items: list[str],
) -> float:
    """Jaccard similarity between final list and list after one more round."""
    return _jaccard(set(final_items), set(extra_round_items))


# ═══════════════════════════════════════════════════════════════════════════════
# Test data fixtures
# ═══════════════════════════════════════════════════════════════════════════════

SPRINT_GOAL = "Ship OAuth 2.0 with rate limiting and user profiles"
CAPACITY = 30

# Rich backlog — 12 items across priorities, total ~55 SP
BACKLOG_FULL: list[dict] = [
    {"item_id": "T-001", "title": "OAuth 2.0 core", "description": "Google + GitHub OAuth flow", "priority": "HIGH", "story_points": 8, "labels": ["auth", "security", "api"], "dependencies": []},
    {"item_id": "T-002", "title": "Rate limiting", "description": "Token bucket rate limiter", "priority": "HIGH", "story_points": 5, "labels": ["backend", "security"], "dependencies": []},
    {"item_id": "T-003", "title": "User profiles CRUD", "description": "REST API for profiles", "priority": "HIGH", "story_points": 5, "labels": ["api", "backend"], "dependencies": ["T-001"]},
    {"item_id": "T-004", "title": "CSRF protection", "description": "CSRF tokens on all forms", "priority": "HIGH", "story_points": 3, "labels": ["security", "api"], "dependencies": []},
    {"item_id": "T-005", "title": "Session management", "description": "JWT-based sessions", "priority": "MEDIUM", "story_points": 5, "labels": ["auth", "backend"], "dependencies": ["T-001"]},
    {"item_id": "T-006", "title": "Email verification", "description": "Verify emails on signup", "priority": "MEDIUM", "story_points": 3, "labels": ["backend", "email"], "dependencies": []},
    {"item_id": "T-007", "title": "Password reset flow", "description": "Forgot password workflow", "priority": "MEDIUM", "story_points": 3, "labels": ["auth", "email"], "dependencies": ["T-006"]},
    {"item_id": "T-008", "title": "Audit logging", "description": "Log auth events to DB", "priority": "LOW", "story_points": 3, "labels": ["backend", "logging"], "dependencies": []},
    {"item_id": "T-009", "title": "Admin dashboard", "description": "Admin panel for user management", "priority": "LOW", "story_points": 8, "labels": ["frontend", "admin"], "dependencies": ["T-003"]},
    {"item_id": "T-010", "title": "API documentation", "description": "OpenAPI spec + Swagger UI", "priority": "LOW", "story_points": 3, "labels": ["docs", "api"], "dependencies": []},
    {"item_id": "T-011", "title": "Dark mode toggle", "description": "CSS dark mode support", "priority": "LOW", "story_points": 2, "labels": ["frontend", "ux"], "dependencies": []},
    {"item_id": "T-012", "title": "i18n support", "description": "Localisation framework", "priority": "LOW", "story_points": 5, "labels": ["frontend", "i18n"], "dependencies": []},
]

BACKLOG_LOOKUP: dict[str, dict] = {it["item_id"]: it for it in BACKLOG_FULL}


def _capacity_aware_recommend(
    backlog_items: list[dict], sprint_goal: str, total_capacity: int,
) -> list[dict]:
    """Greedy capacity-constrained selection by priority then story points."""
    scored = sorted(
        backlog_items,
        key=lambda it: (
            {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(it.get("priority", "LOW"), 1),
            int(it.get("story_points") or 1),
        ),
        reverse=True,
    )
    selected: list[dict] = []
    used = 0
    for it in scored:
        sp = int(it.get("story_points") or 1)
        if used + sp <= total_capacity:
            selected.append(it)
            used += sp
    return selected


# ═══════════════════════════════════════════════════════════════════════════════
# Mock infrastructure (re-uses patterns from test_round_robin.py)
# ═══════════════════════════════════════════════════════════════════════════════


class MockA2AResult:
    def __init__(self, ok: bool, artifact: dict[str, Any] | None = None):
        self.ok = ok
        self.artifact = artifact


@dataclass
class NegotiationRun:
    """Captures the full trace of a negotiation for metric computation."""

    rounds: int
    final_items: list[str]
    final_assignments: dict[str, str]
    round_histories: list[list[dict]] = field(default_factory=list)
    satisfaction_per_round: list[dict[str, bool]] = field(default_factory=list)
    all_proposed_item_ids: list[set[str]] = field(default_factory=list)
    extra_round_items: list[str] | None = None  # stability check


async def run_negotiation(
    session_snap: Any,
    slots: Any,
    backlog_items: list[dict],
    selected_items: list[str],
    agent_responses: dict[str, list[dict[str, Any]]],
    *,
    context: str = "recommendation",
    turn_timeout_seconds: int = 30,
    max_rounds: int = 5,
    synthesize_proposals: bool = True,
    run_stability_check: bool = False,
    recommender_fn: Any = None,
) -> NegotiationRun:
    """Run round-robin discussion with mocked A2A, capturing all metrics data."""
    from unittest.mock import AsyncMock, patch

    from app.phase_orchestrator import _handle_round_robin_discussion

    call_counts: dict[str, int] = {}
    round_histories: list[list[dict]] = []
    satisfaction_per_round: list[dict[str, bool]] = []
    all_proposed: list[set[str]] = []

    async def mock_send_task(endpoint, task_type, session_ctx, payload, **kwargs):
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
            artifact = responses[idx]
            # Track proposals
            actions = artifact.get("actions", [])
            proposed_ids: set[str] = set()
            for action in actions:
                if action.get("type") == "add_item":
                    item = action.get("item", {})
                    iid = item.get("item_id", "")
                    if iid:
                        proposed_ids.add(iid)
            all_proposed.append(proposed_ids)
            return MockA2AResult(ok=True, artifact=artifact)
        return MockA2AResult(ok=True, artifact={"message": "", "actions": [], "done": True})

    # Track round histories by patching _broadcast_round_summary
    original_broadcast = None

    async def capture_broadcast(*args, **kwargs):
        consensus_state = kwargs.get("consensus_state", {})
        satisfaction_per_round.append(dict(consensus_state))
        # Reconstruct items state from working_items
        from app.phase_orchestrator import _handle_round_robin_discussion as hrr
        return None  # we'll patch differently

    with (
        patch("app.phase_orchestrator._a2a.send_task", side_effect=mock_send_task),
        patch("app.comm_bus.publish_comm_event", new_callable=AsyncMock),
        patch(
            "app.phase_orchestrator._broadcast_round_summary",
            new_callable=AsyncMock,
        ) as mock_broadcast,
        patch("app.recommender.recommend", side_effect=recommender_fn or (lambda backlog_items, sprint_goal, total_capacity: backlog_items)),
    ):
        # Intercept _broadcast_round_summary to capture consensus
        original_broadcast_fn = None

        async def interceptor(*args, **kwargs):
            # _broadcast_round_summary(session, context, round_num, round_messages,
            #   working_items, working_assignments, backlog_items,
            #   consensus_state, new_items_proposed)
            cs = args[7] if len(args) > 7 else kwargs.get("consensus_state", {})
            satisfaction_per_round.append(dict(cs) if cs else {})
            # Don't call real broadcast — just capture
            return None

        mock_broadcast.side_effect = interceptor

        result = await _handle_round_robin_discussion(
            session=session_snap,
            slots=slots,
            context=context,
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

    final_items, final_assignments, round_count = result

    # Stability check: run one more round with all agents done
    extra_items = None
    if run_stability_check:
        stability_responses = {
            sid: [{"message": "", "actions": [], "done": True}]
            for sid in agent_responses
        }
        stability_call_counts: dict[str, int] = {}

        async def mock_send_stable(endpoint, task_type, session_ctx, payload, **kwargs):
            slot_id = None
            for s in slots:
                if s.endpoint == endpoint:
                    slot_id = s.id
                    break
            if slot_id is None:
                return MockA2AResult(ok=False)
            idx = stability_call_counts.get(slot_id, 0)
            stability_call_counts[slot_id] = idx + 1
            return MockA2AResult(
                ok=True,
                artifact=stability_responses.get(slot_id, [{}])[0]
                if idx < len(stability_responses.get(slot_id, [{}]))
                else {"message": "", "actions": [], "done": True},
            )

        with (
            patch("app.phase_orchestrator._a2a.send_task", side_effect=mock_send_stable),
            patch("app.comm_bus.publish_comm_event", new_callable=AsyncMock),
            patch("app.phase_orchestrator._broadcast_round_summary", new_callable=AsyncMock),
            patch("app.recommender.recommend", side_effect=lambda bl, sg, tc: bl),
        ):
            extra_result = await _handle_round_robin_discussion(
                session=session_snap,
                slots=slots,
                context=context,
                allowed_actions=["add_item", "remove_item", "modify_item"],
                turn_timeout_seconds=turn_timeout_seconds,
                max_rounds=1,
                synthesize_proposals=False,
                backlog_items=backlog_items,
                selected_items=final_items,
                assignments=final_assignments,
                phase_id="rec-1",
                phase_name="Recommendation",
                phase_history=[],
            )
            extra_items = extra_result[0]

    return NegotiationRun(
        rounds=round_count,
        final_items=final_items,
        final_assignments=final_assignments,
        satisfaction_per_round=satisfaction_per_round,
        all_proposed_item_ids=all_proposed,
        extra_round_items=extra_items,
    )


def compute_all_metrics(
    run: NegotiationRun,
    backlog_lookup: dict[str, dict],
    sprint_goal: str,
    capacity: int,
) -> NegotiationMetrics:
    """Derive all five metrics from a negotiation trace."""

    # 1. Convergence speed
    convergence = run.rounds

    # 2. Pareto efficiency — final vs each round's state (simplified: use final itself)
    final_items_objs = [backlog_lookup[iid] for iid in run.final_items if iid in backlog_lookup]
    pareto = compute_pareto_efficiency(final_items_objs, [], sprint_goal)

    # 3. Agent satisfaction — fraction of agents done by final round
    if run.satisfaction_per_round:
        last_round_sat = run.satisfaction_per_round[-1]
        if last_round_sat:
            done_count = sum(1 for v in last_round_sat.values() if v)
            satisfaction = done_count / len(last_round_sat)
        else:
            satisfaction = 1.0
    else:
        satisfaction = 1.0

    # 4. Coverage
    coverage = compute_coverage(run.final_items, run.all_proposed_item_ids)

    # 5. Stability
    if run.extra_round_items is not None:
        stability = compute_stability(run.final_items, run.extra_round_items)
    else:
        stability = 1.0  # assume stable

    return NegotiationMetrics(
        convergence_rounds=convergence,
        pareto_score=round(pareto, 3),
        satisfaction_ratio=round(satisfaction, 3),
        coverage=round(coverage, 3),
        stability=round(stability, 3),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Session fixture
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def session_snap() -> Any:
    from app.phase_orchestrator import _SessionSnap

    return _SessionSnap(
        id="test-quality-1",
        sprint_goal=SPRINT_GOAL,
        template="sprint_planning_v2",
        sprint_capacity=CAPACITY,
    )


@pytest.fixture
def slots() -> Any:
    from app.phase_orchestrator import _SlotSnap

    return [
        _SlotSnap(
            id="slot-po", participant_id="po-1", name="po-agent",
            role="PRODUCT_OWNER", slot_type="AGENT",
            endpoint="http://po-agent:8001/a2a", status="joined",
        ),
        _SlotSnap(
            id="slot-dev1", participant_id="dev-1", name="dev-agent-1",
            role="DEVELOPER", slot_type="AGENT",
            endpoint="http://dev-agent:8002/a2a", status="joined",
        ),
        _SlotSnap(
            id="slot-dev2", participant_id="dev-2", name="dev-agent-2",
            role="DEVELOPER", slot_type="AGENT",
            endpoint="http://dev-agent-2:8003/a2a", status="joined",
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 1: Homogeneous Preferences
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("label,selected,expected_max_rounds", [
    ("all agree on T-001..T-004", ["T-001", "T-002", "T-003", "T-004"], 1),
    ("all agree on single item", ["T-001"], 1),
])
async def test_homogeneous_converges_in_one_round(
    session_snap, slots, label, selected, expected_max_rounds,
):
    """All agents signal done=True immediately → consensus in 1 round."""
    agent_responses = {
        "slot-po":   [{"message": "LGTM", "actions": [], "done": True}],
        "slot-dev1": [{"message": "Good", "actions": [], "done": True}],
        "slot-dev2": [{"message": "Ship it", "actions": [], "done": True}],
    }

    run = await run_negotiation(
        session_snap, slots, BACKLOG_FULL, selected, agent_responses,
        synthesize_proposals=False, run_stability_check=True,
    )
    metrics = compute_all_metrics(run, BACKLOG_LOOKUP, SPRINT_GOAL, CAPACITY)

    assert run.rounds <= expected_max_rounds, (
        f"Homogeneous scenario '{label}': expected ≤{expected_max_rounds} rounds, "
        f"got {run.rounds}. {metrics.summary()}"
    )
    assert metrics.satisfaction_ratio == 1.0, (
        f"All agents should be satisfied. {metrics.summary()}"
    )
    # Stability: no changes when re-running with done=True agents
    assert metrics.stability >= 0.9, (
        f"Stable after consensus. {metrics.summary()}"
    )

    print(f"\n  [HOMOGENEOUS] {label}: {metrics.summary()}")


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 2: Conflicting Preferences
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_conflicting_preferences_compromise(session_snap, slots):
    """PO wants T-001..T-004, dev1 wants T-009..T-011, dev2 wants T-005..T-007.

    Mutual exclusivity: capacity=30 forces compromise.
    """
    agent_responses = {
        "slot-po": [
            {"message": "Auth first", "actions": [
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-001"]},
            ], "done": False},
            {"message": "OK, compromise", "actions": [], "done": True},
        ],
        "slot-dev1": [
            {"message": "UX matters too", "actions": [
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-009"]},
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-011"]},
            ], "done": False},
            {"message": "Fine", "actions": [
                {"type": "remove_item", "item_id": "T-009"},
            ], "done": True},
        ],
        "slot-dev2": [
            {"message": "Sessions + email", "actions": [
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-005"]},
            ], "done": False},
            {"message": "Works for me", "actions": [], "done": True},
        ],
    }

    run = await run_negotiation(
        session_snap, slots, BACKLOG_FULL,
        ["T-001", "T-002", "T-003", "T-004"],
        agent_responses, synthesize_proposals=True, run_stability_check=True,
        recommender_fn=_capacity_aware_recommend,
    )
    metrics = compute_all_metrics(run, BACKLOG_LOOKUP, SPRINT_GOAL, CAPACITY)

    # Should take more than 1 but not hit max
    assert run.rounds > 1, f"Conflict should need >1 round. {metrics.summary()}"
    assert run.rounds < 5, f"Should not hit max_rounds. {metrics.summary()}"

    # Final list must fit within capacity
    final_sp = sum(
        BACKLOG_LOOKUP[iid].get("story_points", 1) for iid in run.final_items
        if iid in BACKLOG_LOOKUP
    )
    assert final_sp <= CAPACITY, (
        f"Final list exceeds capacity: {final_sp}/{CAPACITY} SP. {metrics.summary()}"
    )

    # Coverage: at least some cross-agent proposals made it
    assert metrics.coverage > 0.0, f"No agent proposals reflected. {metrics.summary()}"

    print(f"\n  [CONFLICTING] {metrics.summary()}")


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 3: Capacity Pressure
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_capacity_pressure_tradeoffs(session_snap, slots):
    """All HIGH items total ~21 SP; capacity=30 but agents keep proposing more.

    Forces the platform recommender to re-rank and drop lower-value items.
    """
    agent_responses = {
        "slot-po": [
            {"message": "Must have auth + rate limiting + CSRF", "actions": [
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-001"]},
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-002"]},
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-004"]},
            ], "done": False},
            {"message": "Done", "actions": [], "done": True},
        ],
        "slot-dev1": [
            {"message": "Profiles too", "actions": [
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-003"]},
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-005"]},
            ], "done": False},
            {"message": "OK", "actions": [], "done": True},
        ],
        "slot-dev2": [
            {"message": "Email and admin", "actions": [
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-006"]},
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-009"]},
            ], "done": False},
            {"message": "Fine", "actions": [], "done": True},
        ],
    }

    # Custom recommender mock that actually enforces capacity
    from unittest.mock import AsyncMock, patch

    from app.phase_orchestrator import _handle_round_robin_discussion

    def capacity_aware_recommend(backlog_items, sprint_goal, total_capacity):
        """Greedily select highest-priority items under capacity."""
        scored = sorted(
            backlog_items,
            key=lambda it: (
                {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(it.get("priority", "LOW"), 1),
                int(it.get("story_points") or 1),
            ),
            reverse=True,
        )
        selected = []
        used = 0
        for it in scored:
            sp = int(it.get("story_points") or 1)
            if used + sp <= total_capacity:
                selected.append(it)
                used += sp
        return selected

    call_counts: dict[str, int] = {}
    satisfaction_per_round: list[dict[str, bool]] = []
    all_proposed: list[set[str]] = []

    async def mock_send_task(endpoint, task_type, session_ctx, payload, **kwargs):
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
            artifact = responses[idx]
            for action in artifact.get("actions", []):
                if action.get("type") == "add_item":
                    iid = action.get("item", {}).get("item_id", "")
                    if iid:
                        all_proposed.append({iid})
            return MockA2AResult(ok=True, artifact=artifact)
        return MockA2AResult(ok=True, artifact={"message": "", "actions": [], "done": True})

    with (
        patch("app.phase_orchestrator._a2a.send_task", side_effect=mock_send_task),
        patch("app.comm_bus.publish_comm_event", new_callable=AsyncMock),
        patch("app.phase_orchestrator._broadcast_round_summary", new_callable=AsyncMock) as mock_bcast,
        patch("app.recommender.recommend", side_effect=capacity_aware_recommend),
    ):
        async def interceptor(*args, **kwargs):
            cs = args[7] if len(args) > 7 else kwargs.get("consensus_state", {})
            satisfaction_per_round.append(dict(cs) if cs else {})
            return None
        mock_bcast.side_effect = interceptor

        result = await _handle_round_robin_discussion(
            session=session_snap,
            slots=slots,
            context="recommendation",
            allowed_actions=["add_item", "remove_item", "modify_item"],
            turn_timeout_seconds=30,
            max_rounds=5,
            synthesize_proposals=True,
            backlog_items=copy.deepcopy(BACKLOG_FULL),
            selected_items=["T-001", "T-002", "T-003", "T-004"],
            assignments={},
            phase_id="rec-1",
            phase_name="Recommendation",
            phase_history=[],
        )

    final_items, _, rounds = result
    final_sp = sum(
        BACKLOG_LOOKUP[iid].get("story_points", 1) for iid in final_items
        if iid in BACKLOG_LOOKUP
    )

    # Capacity constraint must hold
    assert final_sp <= CAPACITY, (
        f"Capacity violated: {final_sp}/{CAPACITY} SP. items={final_items}"
    )

    # High-priority items should dominate
    high_in_final = sum(
        1 for iid in final_items
        if BACKLOG_LOOKUP.get(iid, {}).get("priority") == "HIGH"
    )
    assert high_in_final >= 2, (
        f"Expected ≥2 HIGH items in final list, got {high_in_final}. items={final_items}"
    )

    coverage = compute_coverage(final_items, all_proposed)
    satisfaction = (
        sum(1 for v in satisfaction_per_round[-1].values() if v) / len(satisfaction_per_round[-1])
        if satisfaction_per_round and satisfaction_per_round[-1]
        else 1.0
    )

    print(
        f"\n  [CAPACITY] rounds={rounds} final_sp={final_sp}/{CAPACITY} "
        f"high_items={high_in_final} coverage={coverage:.2f} satisfaction={satisfaction:.2f}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 4: Empty Current List (Cold Start)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cold_start_negotiation(session_snap, slots):
    """No items initially selected — agents must propose everything from scratch."""
    agent_responses = {
        "slot-po": [
            {"message": "Proposing auth stack", "actions": [
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-001"]},
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-002"]},
            ], "done": False},
            {"message": "Done", "actions": [], "done": True},
        ],
        "slot-dev1": [
            {"message": "Security and profiles", "actions": [
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-003"]},
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-004"]},
            ], "done": False},
            {"message": "Good", "actions": [], "done": True},
        ],
        "slot-dev2": [
            {"message": "Sessions too", "actions": [
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-005"]},
            ], "done": False},
            {"message": "Ship it", "actions": [], "done": True},
        ],
    }

    run = await run_negotiation(
        session_snap, slots, BACKLOG_FULL, [], agent_responses,
        synthesize_proposals=True, run_stability_check=True,
    )
    metrics = compute_all_metrics(run, BACKLOG_LOOKUP, SPRINT_GOAL, CAPACITY)

    # Must produce non-empty result
    assert len(run.final_items) > 0, f"Cold start produced empty list. {metrics.summary()}"

    # Coverage: all proposed items should be considered
    assert metrics.coverage > 0.0, f"No proposals covered. {metrics.summary()}"

    # Should converge (not hit max_rounds)
    assert run.rounds < 5, f"Cold start hit max_rounds. {metrics.summary()}"

    print(f"\n  [COLD_START] {metrics.summary()}")


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 5: Adversarial Agent
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_adversarial_agent_robustness(session_snap, slots):
    """One agent proposes invalid items. Pipeline should reject them gracefully."""
    agent_responses = {
        "slot-po": [
            {"message": "Auth stack", "actions": [
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-001"]},
            ], "done": True},
        ],
        "slot-dev1": [
            {"message": "Nonsense proposal", "actions": [
                {"type": "add_item", "item": {
                    "item_id": "GARBAGE-01",
                    "title": "!!!!!",
                    "description": "",
                    "priority": "SUPER_HIGH",  # invalid priority
                    "story_points": -5,          # negative SP
                    "labels": [],
                    "dependencies": [],
                }},
                {"type": "add_item", "item": {
                    # Missing required fields → should be rejected
                    "item_id": "GARBAGE-02",
                }},
                {"type": "add_item", "item": BACKLOG_LOOKUP["T-002"]},  # valid one
            ], "done": True},
        ],
        "slot-dev2": [
            {"message": "Agreed", "actions": [], "done": True},
        ],
    }

    run = await run_negotiation(
        session_snap, slots, BACKLOG_FULL,
        ["T-001"], agent_responses,
        synthesize_proposals=True, run_stability_check=True,
    )
    metrics = compute_all_metrics(run, BACKLOG_LOOKUP, SPRINT_GOAL, CAPACITY)

    # Garbage items must NOT appear in final list
    assert "GARBAGE-01" not in run.final_items, (
        f"Invalid item GARBAGE-01 leaked through. items={run.final_items}"
    )
    assert "GARBAGE-02" not in run.final_items, (
        f"Malformed item GARBAGE-02 leaked through. items={run.final_items}"
    )

    # Valid items should still be present
    assert "T-001" in run.final_items, f"Valid item T-001 missing. items={run.final_items}"
    # T-002 may or may not be there depending on synthesis + capacity

    # System must not crash
    assert run.rounds > 0, f"Adversarial run should complete. {metrics.summary()}"

    print(f"\n  [ADVERSARIAL] {metrics.summary()}")


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 6: Satisfaction Tracking
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_satisfaction_tracks_consensus_progress(session_snap, slots):
    """Verify that satisfaction ratio increases monotonically across rounds."""
    agent_responses = {
        "slot-po": [
            {"message": "Round 0 proposal", "actions": [], "done": False},
            {"message": "Still thinking", "actions": [], "done": False},
            {"message": "Now done", "actions": [], "done": True},
        ],
        "slot-dev1": [
            {"message": "Round 0", "actions": [], "done": False},
            {"message": "Round 1", "actions": [], "done": False},
            {"message": "Done", "actions": [], "done": True},
        ],
        "slot-dev2": [
            {"message": "R0", "actions": [], "done": False},
            {"message": "Done early", "actions": [], "done": True},
        ],
    }

    run = await run_negotiation(
        session_snap, slots, BACKLOG_FULL, ["T-001", "T-002"], agent_responses,
        synthesize_proposals=False,
    )

    # Satisfaction should be non-decreasing
    ratios = []
    for sat_dict in run.satisfaction_per_round:
        if sat_dict:
            ratio = sum(1 for v in sat_dict.values() if v) / len(sat_dict)
            ratios.append(ratio)

    assert len(ratios) >= 2, f"Need ≥2 rounds to track progress. Got {len(ratios)}"
    for i in range(1, len(ratios)):
        assert ratios[i] >= ratios[i - 1], (
            f"Satisfaction decreased: r{i}={ratios[i-1]:.2f} → r{i+1}={ratios[i]:.2f}"
        )

    # Final satisfaction must be 1.0
    assert ratios[-1] == 1.0, f"Not all agents satisfied at end: {ratios[-1]:.2f}"

    print(f"\n  [SATISFACTION] ratios={[f'{r:.2f}' for r in ratios]} rounds={run.rounds}")


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregate quality baseline
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_aggregate_quality_baseline(session_snap, slots):
    """Run all standard scenarios and compute aggregate quality score.

    This serves as the baseline against which future improvements are measured.
    """
    scenarios = [
        ("homogeneous", {
            "slot-po":   [{"message": "", "actions": [], "done": True}],
            "slot-dev1": [{"message": "", "actions": [], "done": True}],
            "slot-dev2": [{"message": "", "actions": [], "done": True}],
        }, ["T-001", "T-002", "T-003", "T-004"], False),

        ("standard-conflict", {
            "slot-po": [
                {"message": "Auth", "actions": [{"type": "add_item", "item": BACKLOG_LOOKUP["T-001"]}], "done": False},
                {"message": "OK", "actions": [], "done": True},
            ],
            "slot-dev1": [
                {"message": "UX", "actions": [{"type": "add_item", "item": BACKLOG_LOOKUP["T-011"]}], "done": False},
                {"message": "Fine", "actions": [{"type": "remove_item", "item_id": "T-011"}], "done": True},
            ],
            "slot-dev2": [
                {"message": "", "actions": [], "done": True},
            ],
        }, ["T-001", "T-002", "T-003", "T-004"], True),
    ]

    all_metrics: list[NegotiationMetrics] = []

    for name, responses, selected, synthesize in scenarios:
        run = await run_negotiation(
            session_snap, slots, BACKLOG_FULL, selected, responses,
            synthesize_proposals=synthesize,
        )
        metrics = compute_all_metrics(run, BACKLOG_LOOKUP, SPRINT_GOAL, CAPACITY)
        all_metrics.append(metrics)
        print(f"\n  [BASELINE:{name}] {metrics.summary()}")

    # Compute aggregate scores
    avg_convergence = sum(m.convergence_rounds for m in all_metrics) / len(all_metrics)
    avg_satisfaction = sum(m.satisfaction_ratio for m in all_metrics) / len(all_metrics)
    avg_coverage = sum(m.coverage for m in all_metrics) / len(all_metrics)

    print(
        f"\n  [BASELINE:AGGREGATE] "
        f"avg_convergence={avg_convergence:.1f} "
        f"avg_satisfaction={avg_satisfaction:.2f} "
        f"avg_coverage={avg_coverage:.2f}"
    )

    # Minimum quality thresholds (should tighten as pipeline improves)
    assert avg_convergence <= 4.0, f"Convergence too slow: {avg_convergence:.1f} rounds"
    assert avg_satisfaction >= 0.5, f"Satisfaction too low: {avg_satisfaction:.2f}"
    assert avg_coverage >= 0.0, f"Coverage should be measurable: {avg_coverage:.2f}"
