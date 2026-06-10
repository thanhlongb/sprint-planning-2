"""
Agent-Specific Objective Functions for Mutation Proposal Generation.

Each agent persona (Frontend, Backend, QA) has a domain-specific scoring
function over backlog items. The scores drive structured mutation proposals
(add, remove, modify) with NL justifications reflecting the agent's perspective.

Schema references:
  - Mutation:   type, item_id, updates, justification
  - AgentContext: discussion, backlog_items, current_sprint, agent_persona

Integration point: called after an agent produces its NL response during
/discuss. The NL response becomes the justification; mutations are extracted
and structured.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Domain models ──────────────────────────────────────────────────────────────


class MutationType(str, Enum):
    ADD = "add_item"
    REMOVE = "remove_item"
    MODIFY = "modify_item"


class AgentPersona(str, Enum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    QA = "qa"

    @classmethod
    def from_role_and_name(cls, role: str, name: str) -> "AgentPersona":
        """Infer persona from agent role and name (heuristic).

        Maps:
          - names containing 'frontend', 'fe', 'ui' → FRONTEND
          - names containing 'backend', 'be', 'api' → BACKEND
          - names containing 'qa', 'test', 'quality' → QA
          - roles: PRODUCT_OWNER defaults to FRONTEND (UI/UX focus)
          - roles: DEVELOPER defaults to BACKEND
          - ARCHITECT defaults to BACKEND
          - fallback → BACKEND
        """
        name_lower = name.lower()
        if any(kw in name_lower for kw in ("frontend", "fe", "ui", "ux")):
            return cls.FRONTEND
        if any(kw in name_lower for kw in ("qa", "test", "quality")):
            return cls.QA
        if any(kw in name_lower for kw in ("backend", "be", "api", "data")):
            return cls.BACKEND
        # Role-based fallback
        if role == "PRODUCT_OWNER":
            return cls.FRONTEND
        return cls.BACKEND


@dataclass
class AgentContext:
    """Input context for agent objective functions.

    Attributes:
        agent_id:   Unique agent identifier (participant_id or slot_id).
        agent_name: Display name of the agent.
        agent_role: Role string (e.g. 'DEVELOPER', 'PRODUCT_OWNER').
        discussion: Full discussion transcript as text.
        backlog_items: All backlog items (list of dicts with keys:
            item_id, title, description, priority, story_points, labels, dependencies).
        current_sprint: Current sprint items (list of item_ids or dicts).
        sprint_goal: Sprint goal text (for similarity scoring).
        persona:      Explicit persona override. If None, inferred from role+name.
    """
    agent_id: str
    agent_name: str = ""
    agent_role: str = "DEVELOPER"
    discussion: str = ""
    backlog_items: list[dict[str, Any]] = field(default_factory=list)
    current_sprint: list[str] = field(default_factory=list)
    sprint_goal: str = ""
    persona: AgentPersona | None = None

    @property
    def resolved_persona(self) -> AgentPersona:
        if self.persona is not None:
            return self.persona
        return AgentPersona.from_role_and_name(self.agent_role, self.agent_name)

    @property
    def current_sprint_ids(self) -> set[str]:
        """Normalised set of item IDs currently in the sprint."""
        ids: set[str] = set()
        for entry in self.current_sprint:
            if isinstance(entry, dict):
                iid = entry.get("item_id", "")
                if iid:
                    ids.add(iid)
            elif isinstance(entry, str):
                ids.add(entry)
        return ids

    @property
    def backlog_lookup(self) -> dict[str, dict[str, Any]]:
        return {item.get("item_id", ""): item for item in self.backlog_items}


@dataclass
class Mutation:
    """A structured mutation proposal with NL justification.

    Attributes:
        mutation_type: add_item | remove_item | modify_item.
        item_id:       Target backlog item ID.
        score:         Agent's score for this item (0.0–1.0, higher = more relevant).
        priority_rank: 0-indexed rank among all scored items.
        updates:       For modify_item: dict of field→new_value.
        justification: NL explanation from the agent's perspective.
        item_data:     Full item dict for add_item proposals (new items).
    """
    mutation_type: MutationType
    item_id: str
    score: float = 0.0
    priority_rank: int = 0
    updates: dict[str, Any] | None = None
    justification: str = ""
    item_data: dict[str, Any] | None = None


# ── Label sets per persona ─────────────────────────────────────────────────────

_FRONTEND_LABELS: set[str] = {
    "ui", "frontend", "ux", "design", "css", "component",
    "responsive", "accessibility", "animation", "style",
}
_BACKEND_LABELS: set[str] = {
    "backend", "api", "database", "data", "server", "auth",
    "security", "performance", "infra", "scaling", "integration",
}
_QA_LABELS: set[str] = {
    "testing", "qa", "e2e", "integration-test", "unit-test",
    "bug", "tech-debt", "regression", "coverage",
}

_PRIORITY_SCORE: dict[str, float] = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}

# ── Tag relevance helpers ──────────────────────────────────────────────────────


def _label_relevance(labels: list[str], persona_labels: set[str]) -> float:
    """Jaccard-like relevance: intersection / max(|labels|, 1).

    Returns 0.0–1.0 where 1.0 means every label matches persona.
    """
    if not labels:
        return 0.0
    label_set = {lbl.lower() for lbl in labels}
    intersection = label_set & persona_labels
    return len(intersection) / max(len(label_set), 1)


def _priority_value(item: dict[str, Any]) -> float:
    return _PRIORITY_SCORE.get(str(item.get("priority", "LOW")).upper(), 0.3)


def _story_points(item: dict[str, Any]) -> int:
    sp = item.get("story_points")
    return sp if isinstance(sp, int) and sp is not None else 1


# ── Persona-specific scoring functions ─────────────────────────────────────────


def _score_frontend(item: dict[str, Any], sprint_goal: str) -> float:
    """Frontend agent: weights UI-relevance tags × goal_similarity.

    Formula: label_relevance × 0.6 + priority × 0.15 + goal_similarity × 0.25
    """
    labels: list[str] = item.get("labels", []) or []
    relevance = _label_relevance(labels, _FRONTEND_LABELS)
    priority = _priority_value(item)

    # goal_similarity proxied by title overlap with sprint goal keywords
    title = str(item.get("title", "")).lower()
    description = str(item.get("description", "")).lower()
    goal_words = set(sprint_goal.lower().split())
    title_words = set(title.split()) | set(description.split())
    goal_sim = len(goal_words & title_words) / max(len(goal_words), 1) if goal_words else 0.0
    goal_sim = min(goal_sim, 1.0)

    return 0.60 * relevance + 0.15 * priority + 0.25 * goal_sim


def _score_backend(item: dict[str, Any], sprint_goal: str) -> float:
    """Backend agent: weights business_value (priority) × data-integrity tags.

    Formula: label_relevance × 0.45 + priority × 0.40 + goal_similarity × 0.15
    """
    labels: list[str] = item.get("labels", []) or []
    relevance = _label_relevance(labels, _BACKEND_LABELS)
    priority = _priority_value(item)

    title = str(item.get("title", "")).lower()
    description = str(item.get("description", "")).lower()
    goal_words = set(sprint_goal.lower().split())
    title_words = set(title.split()) | set(description.split())
    goal_sim = len(goal_words & title_words) / max(len(goal_words), 1) if goal_words else 0.0
    goal_sim = min(goal_sim, 1.0)

    # Bonus for data-integrity signals: "data", "validation", "integrity", "consistency"
    data_keywords = {"data", "validation", "integrity", "consistency", "migration", "schema"}
    data_bonus = 0.10 if (title_words & data_keywords) else 0.0

    return 0.45 * relevance + 0.40 * priority + 0.15 * goal_sim + data_bonus


def _score_qa(item: dict[str, Any], sprint_goal: str) -> float:
    """QA agent: weights test-coverage-risk (inverse of existing test coverage).

    Items WITHOUT test/QA labels score HIGHER (they're riskier).
    Items WITH "bug" or "tech-debt" labels score highest (known quality gaps).

    Formula: risk_score × 0.50 + priority × 0.30 + label_relevance × 0.20
    where risk_score = 1.0 if has bug/tech-debt, else inverse of testing label presence.
    """
    labels: list[str] = item.get("labels", []) or []
    label_set = {lbl.lower() for lbl in labels}
    priority = _priority_value(item)

    # QA relevance: testing, qa, bug, tech-debt labels
    qa_relevance = _label_relevance(labels, _QA_LABELS)

    # Risk: items with bugs/tech-debt → high risk; items with testing labels → lower risk
    has_bug_label = bool(label_set & {"bug", "tech-debt", "regression"})
    has_test_label = bool(label_set & {"testing", "qa", "e2e", "unit-test", "integration-test"})

    if has_bug_label:
        risk_score = 1.0  # maximum risk — known quality issue
    elif has_test_label:
        risk_score = 0.2  # well-tested — low risk
    else:
        risk_score = 0.7  # untested — moderate-high risk

    # goal_similarity (lower weight for QA)
    title = str(item.get("title", "")).lower()
    description = str(item.get("description", "")).lower()
    goal_words = set(sprint_goal.lower().split())
    title_words = set(title.split()) | set(description.split())
    goal_sim = len(goal_words & title_words) / max(len(goal_words), 1) if goal_words else 0.0
    goal_sim = min(goal_sim, 1.0)

    return 0.50 * risk_score + 0.30 * priority + 0.15 * qa_relevance + 0.05 * goal_sim


# ── Scoring dispatch ───────────────────────────────────────────────────────────

_SCORER: dict[AgentPersona, Any] = {
    AgentPersona.FRONTEND: _score_frontend,
    AgentPersona.BACKEND: _score_backend,
    AgentPersona.QA: _score_qa,
}


def _score_item(
    item: dict[str, Any], persona: AgentPersona, sprint_goal: str,
) -> float:
    scorer = _SCORER.get(persona, _score_backend)
    return scorer(item, sprint_goal)


# ── Justification generation (NL via template — LLM integration point) ─────────


def _build_justification(
    mutation_type: MutationType,
    item: dict[str, Any],
    persona: AgentPersona,
    score: float,
    sprint_goal: str,
    discussion: str,
) -> str:
    """Generate a domain-appropriate NL justification for the mutation.

    This is a template-based fallback. The task specifies LLM-driven
    justification; this function provides the integration point where
    an LLM call would be inserted.

    For now, produces structured justifications from the persona's viewpoint.
    """
    title = item.get("title", "Unknown item")
    labels = item.get("labels", [])
    priority = item.get("priority", "LOW")
    sp = item.get("story_points", "?")

    if persona == AgentPersona.FRONTEND:
        if mutation_type == MutationType.ADD:
            ui_labels = [l for l in labels if l.lower() in _FRONTEND_LABELS]
            label_str = ", ".join(ui_labels) if ui_labels else "UI impact"
            return (
                f"[Frontend] Adding '{title}' — addresses {label_str} needs. "
                f"Score: {score:.2f}, priority={priority}, {sp} SP. "
                f"Aligns with sprint goal: '{sprint_goal[:60]}'."
            )
        elif mutation_type == MutationType.REMOVE:
            return (
                f"[Frontend] Removing '{title}' — lacks UI/UX relevance "
                f"(labels: {labels}). Score: {score:.2f}. "
                f"Better to focus sprint capacity on user-facing features."
            )
        else:
            return (
                f"[Frontend] Modifying '{title}' — adjusting for UI/UX alignment. "
                f"Score: {score:.2f}."
            )
    elif persona == AgentPersona.BACKEND:
        if mutation_type == MutationType.ADD:
            be_labels = [l for l in labels if l.lower() in _BACKEND_LABELS]
            label_str = ", ".join(be_labels) if be_labels else "backend relevance"
            return (
                f"[Backend] Adding '{title}' — high business value via {label_str}. "
                f"Score: {score:.2f}, priority={priority}, {sp} SP."
            )
        elif mutation_type == MutationType.REMOVE:
            return (
                f"[Backend] Removing '{title}' — low data-integrity alignment "
                f"(labels: {labels}). Score: {score:.2f}. "
                f"Capacity should go to backend-critical items."
            )
        else:
            return (
                f"[Backend] Modifying '{title}' — data-integrity or integration concern. "
                f"Score: {score:.2f}."
            )
    else:  # QA
        if mutation_type == MutationType.ADD:
            bug_labels = [l for l in labels if l.lower() in {"bug", "tech-debt"}]
            if bug_labels:
                return (
                    f"[QA] Adding '{title}' — known quality gap ({', '.join(bug_labels)}). "
                    f"Score: {score:.2f}, priority={priority}, {sp} SP."
                )
            return (
                f"[QA] Adding '{title}' — untested area needs coverage. "
                f"Score: {score:.2f}, priority={priority}, {sp} SP."
            )
        elif mutation_type == MutationType.REMOVE:
            has_tests = any(l.lower() in {"testing", "qa", "e2e"} for l in labels)
            if has_tests:
                return (
                    f"[QA] Removing '{title}' — well-covered by tests, lower quality risk. "
                    f"Score: {score:.2f}."
                )
            return (
                f"[QA] Removing '{title}' — low test-coverage risk. "
                f"Score: {score:.2f}."
            )
        else:
            return (
                f"[QA] Modifying '{title}' — quality or coverage concern. "
                f"Score: {score:.2f}."
            )


# ── Main entry point ───────────────────────────────────────────────────────────


def agent_objective(
    agent_id: str,
    context: AgentContext,
    *,
    top_n: int = 10,
    add_threshold: float = 0.5,
    remove_threshold: float = 0.25,
) -> list[Mutation]:
    """Produce ordered mutation proposals from an agent's domain-specific objective.

    Args:
        agent_id:  Agent identifier (participant_id or slot_id).
        context:   Full agent context (discussion, backlog, sprint, persona).
        top_n:     Maximum number of mutations to return.
        add_threshold:  Minimum score for an item to be proposed as ADD (items not in sprint).
        remove_threshold: Maximum score for an item to be proposed as REMOVE (items in sprint).

    Returns:
        Ordered list of Mutation proposals (highest priority first).
    """
    if not context.backlog_items:
        return []

    persona = context.resolved_persona
    sprint_ids = context.current_sprint_ids
    sprint_goal = context.sprint_goal or ""

    # Score every backlog item against this agent's objective
    scored: list[tuple[str, dict[str, Any], float]] = []
    for item in context.backlog_items:
        item_id = item.get("item_id", "")
        if not item_id:
            continue
        score = _score_item(item, persona, sprint_goal)
        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))
        scored.append((item_id, item, score))

    # Sort by descending score
    scored.sort(key=lambda x: x[2], reverse=True)

    mutations: list[Mutation] = []
    for rank, (item_id, item, score) in enumerate(scored):
        if len(mutations) >= top_n:
            break

        in_sprint = item_id in sprint_ids

        if not in_sprint and score >= add_threshold:
            # Propose adding this item
            mutations.append(Mutation(
                mutation_type=MutationType.ADD,
                item_id=item_id,
                score=round(score, 4),
                priority_rank=rank,
                justification=_build_justification(
                    MutationType.ADD, item, persona, score,
                    sprint_goal, context.discussion,
                ),
                item_data=item,
            ))
        elif in_sprint and score < remove_threshold:
            # Propose removing this item from sprint
            mutations.append(Mutation(
                mutation_type=MutationType.REMOVE,
                item_id=item_id,
                score=round(score, 4),
                priority_rank=rank,
                justification=_build_justification(
                    MutationType.REMOVE, item, persona, score,
                    sprint_goal, context.discussion,
                ),
            ))
        elif in_sprint and add_threshold > score >= remove_threshold:
            # Borderline: propose modify (reprioritize or adjust)
            mutations.append(Mutation(
                mutation_type=MutationType.MODIFY,
                item_id=item_id,
                score=round(score, 4),
                priority_rank=rank,
                justification=_build_justification(
                    MutationType.MODIFY, item, persona, score,
                    sprint_goal, context.discussion,
                ),
            ))

    return mutations


# ── Convenience: score-only access (for use within discussion flows) ───────────


def score_items(
    context: AgentContext,
) -> list[dict[str, Any]]:
    """Score all backlog items for a given agent context.

    Returns the backlog items augmented with 'agent_score' field,
    sorted descending by score.
    """
    persona = context.resolved_persona
    sprint_goal = context.sprint_goal or ""

    scored: list[dict[str, Any]] = []
    for item in context.backlog_items:
        score = _score_item(item, persona, sprint_goal)
        score = max(0.0, min(1.0, score))
        scored.append({**item, "agent_score": round(score, 4)})

    scored.sort(key=lambda it: it["agent_score"], reverse=True)
    return scored
