"""
Tests for agent_objectives.py — verify acceptance criteria:

AC1: Each agent type produces different mutation priorities for the same input
AC2: Mutations are valid (keys exist in backlog/current list)
AC3: NL justifications are domain-appropriate
"""

import sys
from pathlib import Path

# Add app package to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "platform" / "app"))

from agent_objectives import (
    AgentContext,
    AgentPersona,
    Mutation,
    MutationType,
    _score_frontend,
    _score_backend,
    _score_qa,
    _build_justification,
    agent_objective,
    score_items,
)

# ── Shared test fixtures ───────────────────────────────────────────────────────

SAMPLE_BACKLOG = [
    {
        "item_id": "T-001",
        "title": "Add rate limiting to login endpoint",
        "description": "Implement token-bucket rate limiting on POST /auth/login.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["auth", "security"],
    },
    {
        "item_id": "T-002",
        "title": "Build responsive user dashboard",
        "description": "Landing page with real-time metrics and mobile-responsive layout.",
        "priority": "HIGH",
        "story_points": 8,
        "labels": ["ui", "frontend"],
    },
    {
        "item_id": "T-003",
        "title": "Write API integration tests with pytest",
        "description": "Comprehensive integration tests for all /api/v1 endpoints.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["testing", "api"],
    },
    {
        "item_id": "T-004",
        "title": "Fix XSS vulnerability in comment rendering",
        "description": "Apply DOMPurify and Content-Security-Policy headers.",
        "priority": "HIGH",
        "story_points": 2,
        "labels": ["bug", "security"],
    },
    {
        "item_id": "T-005",
        "title": "Implement database migration framework",
        "description": "Set up Alembic with auto-generation from SQLAlchemy models.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["infra", "backend"],
    },
    {
        "item_id": "T-006",
        "title": "Create dark mode theme toggle",
        "description": "System-preference-aware dark mode with CSS custom properties.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["ui", "frontend", "style"],
    },
    {
        "item_id": "T-007",
        "title": "Add database query optimization",
        "description": "Analyze slow queries with EXPLAIN, add missing indexes.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["performance", "backend", "tech-debt"],
    },
    {
        "item_id": "T-008",
        "title": "Set up end-to-end testing with Playwright",
        "description": "Cross-browser E2E tests on critical user flows.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["testing", "ui"],
    },
    {
        "item_id": "T-009",
        "title": "Refactor monolithic API router into modules",
        "description": "Split router into domain-specific modules with shared middleware.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["tech-debt", "backend"],
    },
    {
        "item_id": "T-010",
        "title": "Add request logging and structured error responses",
        "description": "Middleware to log requests with correlation IDs and JSON error bodies.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["api", "backend"],
    },
]

SPRINT_GOAL = "Improve platform security, user experience, and code quality for v2 launch"

CURRENT_SPRINT_IDS = ["T-001", "T-002", "T-003", "T-004", "T-005"]


def make_ctx(persona: AgentPersona) -> AgentContext:
    return AgentContext(
        agent_id="test-agent-1",
        agent_name=f"test-{persona.value}-agent",
        agent_role="DEVELOPER",
        discussion="We need to focus on what matters most for the sprint.",
        backlog_items=SAMPLE_BACKLOG,
        current_sprint=CURRENT_SPRINT_IDS,
        sprint_goal=SPRINT_GOAL,
        persona=persona,
    )


# ── AC1: Different agent types → different priorities ──────────────────────────


def test_frontend_vs_backend_different_scores():
    """Frontend and Backend agents score the same item differently."""
    ui_item = SAMPLE_BACKLOG[1]  # T-002: dashboard, labels=['ui', 'frontend']
    be_item = SAMPLE_BACKLOG[4]  # T-005: migration, labels=['infra', 'backend']

    fe_score_ui = _score_frontend(ui_item, SPRINT_GOAL)
    be_score_ui = _score_backend(ui_item, SPRINT_GOAL)
    fe_score_be = _score_frontend(be_item, SPRINT_GOAL)
    be_score_be = _score_backend(be_item, SPRINT_GOAL)

    # Frontend should prefer UI item over backend item
    assert fe_score_ui > fe_score_be, (
        f"Frontend should score UI item ({fe_score_ui:.3f}) "
        f"higher than backend item ({fe_score_be:.3f})"
    )
    # Backend should prefer backend item over UI item
    assert be_score_be > be_score_ui, (
        f"Backend should score backend item ({be_score_be:.3f}) "
        f"higher than UI item ({be_score_ui:.3f})"
    )


def test_qa_prioritizes_bugs():
    """QA agent should score bug/tech-debt items highest."""
    bug_item = SAMPLE_BACKLOG[3]   # T-004: XSS fix, labels=['bug', 'security']
    test_item = SAMPLE_BACKLOG[2]  # T-003: API tests, labels=['testing', 'api']
    ui_item = SAMPLE_BACKLOG[1]    # T-002: dashboard, labels=['ui', 'frontend']

    qa_bug = _score_qa(bug_item, SPRINT_GOAL)
    qa_test = _score_qa(test_item, SPRINT_GOAL)
    qa_ui = _score_qa(ui_item, SPRINT_GOAL)

    # Bug item should score highest
    assert qa_bug > qa_ui, f"QA should score bug ({qa_bug:.3f}) > UI ({qa_ui:.3f})"
    # Test-covered item should score lower than bug
    assert qa_bug > qa_test, f"QA should score bug ({qa_bug:.3f}) > tested ({qa_test:.3f})"


def test_different_mutation_sets_same_input():
    """Same input → different agent types produce different mutation lists."""
    ctx_fe = make_ctx(AgentPersona.FRONTEND)
    ctx_be = make_ctx(AgentPersona.BACKEND)
    ctx_qa = make_ctx(AgentPersona.QA)

    muts_fe = agent_objective("a1", ctx_fe)
    muts_be = agent_objective("a1", ctx_be)
    muts_qa = agent_objective("a1", ctx_qa)

    fe_ids = {m.item_id for m in muts_fe}
    be_ids = {m.item_id for m in muts_be}
    qa_ids = {m.item_id for m in muts_qa}

    # The mutation sets should differ (they look at different things)
    all_same = fe_ids == be_ids == qa_ids
    assert not all_same, (
        f"Mutation sets should differ by persona.\n"
        f"  FE: {sorted(fe_ids)}\n"
        f"  BE: {sorted(be_ids)}\n"
        f"  QA: {sorted(qa_ids)}"
    )

    # Frontend should have ADD for UI items not in sprint
    ui_not_in_sprint = {"T-006"}  # dark mode, not in current sprint
    assert ui_not_in_sprint & fe_ids, (
        f"Frontend should propose adding UI item T-006. Got: {sorted(fe_ids)}"
    )

    # QA should suggest adding bug item T-004 if not already, or remove well-tested items
    # T-004 is already in sprint, so QA might flag it for MODIFY instead of ADD
    qa_item_ids = {m.item_id for m in muts_qa}
    assert qa_item_ids, "QA should produce at least one mutation"


def test_score_ordering_consistent():
    """Score ordering within a persona should be deterministic."""
    for persona in AgentPersona:
        ctx = make_ctx(persona)
        scored1 = score_items(ctx)
        scored2 = score_items(ctx)

        ids1 = [it["item_id"] for it in scored1]
        ids2 = [it["item_id"] for it in scored2]
        assert ids1 == ids2, f"{persona.value}: score ordering not deterministic"


# ── AC2: Mutations are valid ───────────────────────────────────────────────────


def test_mutations_reference_valid_keys():
    """Every mutation's item_id must exist in the backlog."""
    for persona in AgentPersona:
        ctx = make_ctx(persona)
        mutations = agent_objective(f"agent-{persona.value}", ctx)
        backlog_ids = {item["item_id"] for item in SAMPLE_BACKLOG}

        for m in mutations:
            assert m.item_id in backlog_ids, (
                f"{persona.value}: mutation {m.mutation_type.value} references "
                f"unknown item_id '{m.item_id}'. Known: {sorted(backlog_ids)}"
            )


def test_remove_mutations_target_sprint_items():
    """Remove mutations should only target items currently in the sprint."""
    for persona in AgentPersona:
        ctx = make_ctx(persona)
        mutations = agent_objective(f"agent-{persona.value}", ctx)

        for m in mutations:
            if m.mutation_type == MutationType.REMOVE:
                assert m.item_id in CURRENT_SPRINT_IDS, (
                    f"{persona.value}: REMOVE mutation targets '{m.item_id}' "
                    f"which is NOT in current sprint {CURRENT_SPRINT_IDS}"
                )


def test_add_mutations_target_items_not_in_sprint():
    """Add mutations should only target items NOT currently in the sprint."""
    for persona in AgentPersona:
        ctx = make_ctx(persona)
        mutations = agent_objective(f"agent-{persona.value}", ctx)

        for m in mutations:
            if m.mutation_type == MutationType.ADD:
                assert m.item_id not in CURRENT_SPRINT_IDS, (
                    f"{persona.value}: ADD mutation targets '{m.item_id}' "
                    f"which IS already in sprint {CURRENT_SPRINT_IDS}"
                )


def test_scores_in_valid_range():
    """All scores should be in [0.0, 1.0]."""
    for persona in AgentPersona:
        ctx = make_ctx(persona)
        mutations = agent_objective(f"agent-{persona.value}", ctx)
        for m in mutations:
            assert 0.0 <= m.score <= 1.0, (
                f"{persona.value}: score {m.score} out of range for {m.item_id}"
            )


def test_priority_ranks_sequential():
    """Priority ranks should be sequential starting from 0."""
    for persona in AgentPersona:
        ctx = make_ctx(persona)
        mutations = agent_objective(f"agent-{persona.value}", ctx)
        ranks = [m.priority_rank for m in mutations]
        # Ranks should be in ascending order (they reflect position in scored list)
        assert ranks == sorted(ranks), (
            f"{persona.value}: ranks not sorted: {ranks}"
        )


# ── AC3: NL justifications are domain-appropriate ──────────────────────────────


def test_justifications_contain_persona_tag():
    """Justifications should include the persona's domain tag."""
    for persona in AgentPersona:
        ctx = make_ctx(persona)
        mutations = agent_objective(f"agent-{persona.value}", ctx)
        for m in mutations:
            tag = f"[{persona.value.capitalize()}]"
            # Frontend → [Frontend], Backend → [Backend], Qa → [Qa]
            if persona == AgentPersona.QA:
                assert "[QA]" in m.justification, (
                    f"QA justification missing [QA] tag: {m.justification[:80]}"
                )
            else:
                assert tag in m.justification, (
                    f"{persona.value} justification missing {tag}: {m.justification[:80]}"
                )


def test_justifications_mention_item_title():
    """Justifications should reference the item's title."""
    for persona in AgentPersona:
        ctx = make_ctx(persona)
        mutations = agent_objective(f"agent-{persona.value}", ctx)
        for m in mutations:
            assert m.item_id in m.justification or any(
                m.item_id == it["item_id"] and it["title"] in m.justification
                for it in SAMPLE_BACKLOG
            ), (
                f"{persona.value}: justification for {m.item_id} "
                f"doesn't reference item: {m.justification[:80]}"
            )


def test_justifications_non_empty():
    """All mutations must have non-empty justifications."""
    for persona in AgentPersona:
        ctx = make_ctx(persona)
        mutations = agent_objective(f"agent-{persona.value}", ctx)
        for m in mutations:
            assert m.justification.strip(), (
                f"{persona.value}: empty justification for {m.item_id}"
            )


# ── Edge cases ─────────────────────────────────────────────────────────────────


def test_empty_backlog():
    """Empty backlog should produce no mutations."""
    ctx = AgentContext(
        agent_id="a1",
        agent_name="test",
        backlog_items=[],
        current_sprint=[],
        sprint_goal="test",
        persona=AgentPersona.FRONTEND,
    )
    assert agent_objective("a1", ctx) == []


def test_empty_sprint_goal():
    """Empty sprint goal should not crash scoring."""
    ctx = make_ctx(AgentPersona.BACKEND)
    ctx.sprint_goal = ""
    mutations = agent_objective("a1", ctx)
    assert len(mutations) >= 0  # shouldn't crash


def test_top_n_limit():
    """top_n parameter should cap mutations."""
    ctx = make_ctx(AgentPersona.FRONTEND)
    mutations = agent_objective("a1", ctx, top_n=3)
    assert len(mutations) <= 3


def test_persona_inference_from_role():
    """AgentPersona.from_role_and_name should infer correctly."""
    assert AgentPersona.from_role_and_name("DEVELOPER", "frontend-dev") == AgentPersona.FRONTEND
    assert AgentPersona.from_role_and_name("DEVELOPER", "backend-api") == AgentPersona.BACKEND
    assert AgentPersona.from_role_and_name("DEVELOPER", "qa-engineer") == AgentPersona.QA
    assert AgentPersona.from_role_and_name("PRODUCT_OWNER", "po-agent") == AgentPersona.FRONTEND
    assert AgentPersona.from_role_and_name("DEVELOPER", "generic-dev") == AgentPersona.BACKEND
    assert AgentPersona.from_role_and_name("DEVELOPER", "test-automation") == AgentPersona.QA
    assert AgentPersona.from_role_and_name("DEVELOPER", "fe-specialist") == AgentPersona.FRONTEND
    assert AgentPersona.from_role_and_name("DEVELOPER", "data-engineer") == AgentPersona.BACKEND


def test_q_inverse_risk_logic():
    """QA scores untested items higher than well-tested items."""
    untested = {"item_id": "NEW-1", "title": "New feature X",
                "description": "No tests.", "priority": "HIGH",
                "story_points": 3, "labels": []}
    well_tested = {"item_id": "NEW-2", "title": "Feature Y",
                   "description": "Has tests.", "priority": "HIGH",
                   "story_points": 3, "labels": ["testing", "qa"]}
    bug_item = {"item_id": "BUG-1", "title": "Critical bug",
                "description": "Crashes.", "priority": "HIGH",
                "story_points": 2, "labels": ["bug", "security"]}

    score_untested = _score_qa(untested, "")
    score_tested = _score_qa(well_tested, "")
    score_bug = _score_qa(bug_item, "")

    assert score_bug > score_untested, (
        f"Bug ({score_bug:.3f}) should outrank untested ({score_untested:.3f})"
    )
    assert score_untested > score_tested, (
        f"Untested ({score_untested:.3f}) should outrank well-tested ({score_tested:.3f})"
    )


# ── Integration: persona routing ───────────────────────────────────────────────


def test_persona_routing_respected():
    """Explicit persona overrides role-based inference."""
    ctx = AgentContext(
        agent_id="a1",
        agent_name="frontend-dev",
        agent_role="DEVELOPER",
        backlog_items=SAMPLE_BACKLOG,
        current_sprint=CURRENT_SPRINT_IDS,
        sprint_goal=SPRINT_GOAL,
        persona=AgentPersona.QA,  # override — "frontend-dev" name would infer FRONTEND
    )
    mutations = agent_objective("a1", ctx)
    assert len(mutations) > 0
    # Check justifications use QA perspective
    qa_justifications = [m.justification for m in mutations if "[QA]" in m.justification]
    assert len(qa_justifications) > 0, (
        f"Explicit QA persona should produce QA justifications. "
        f"Got: {[m.justification[:60] for m in mutations]}"
    )
