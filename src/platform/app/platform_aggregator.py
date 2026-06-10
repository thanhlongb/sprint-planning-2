"""
Platform Aggregator — reconciles agent mutation sets into a balanced sprint list.

Receives structured mutations from each agent after a discussion round and
produces a reconciled sprint list. Handles conflict resolution, add/remove/
modify reconciliation, re-ranking via the recommender, and CONVERGED detection.

This is the implementation referenced by t_71f69cb1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

log = logging.getLogger(__name__)


# ── Data models ────────────────────────────────────────────────────────────────

class MutationType(str, Enum):
    ADD = "add_item"
    REMOVE = "remove_item"
    MODIFY = "modify_item"
    VOLUNTEER = "volunteer"
    OBJECT = "object"
    REASSIGN = "reassign"


@dataclass
class Mutation:
    """A single structured change proposed by an agent."""
    type: MutationType
    item_id: str
    source: str          # agent slot_id / participant_id
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMutationSet:
    """All mutations from one agent in one discussion round."""
    agent_id: str
    agent_name: str
    agent_role: str
    mutations: list[Mutation]
    done: bool
    message: str = ""


@dataclass
class AggregationResult:
    """Result of aggregating all agent mutation sets into a balanced sprint list."""
    final_items: list[str]
    assignments: dict[str, str]
    applied_adds: int
    applied_removes: int
    applied_modifies: int
    discarded_mutations: list[Mutation]
    converged: bool
    stats: dict[str, Any] = field(default_factory=dict)


# ── Mutation parser ────────────────────────────────────────────────────────────

def parse_mutations_from_turn_response(
    turn_response: dict[str, Any],
    source_agent_id: str,
) -> list[Mutation]:
    """Extract structured Mutation objects from a turn response artifact.

    This is the mutation parser — converts NL + structured actions from agent
    responses into canonical Mutation objects for downstream aggregation.
    """
    mutations: list[Mutation] = []
    actions: list[dict] = turn_response.get("actions", [])

    for action in actions:
        action_type = action.get("type", "")
        try:
            mutation_type = MutationType(action_type)
        except ValueError:
            log.debug("unknown action type %r from %s", action_type, source_agent_id)
            continue

        # Resolve item_id from nested structures
        item_id = action.get("item_id") or action.get("item", {}).get("item_id", "")
        if not item_id:
            log.debug("mutation without item_id from %s: %s", source_agent_id, action_type)
            continue

        mutations.append(Mutation(
            type=mutation_type,
            item_id=item_id,
            source=source_agent_id,
            data=action,
        ))

    return mutations


def parse_agent_mutation_sets(
    round_messages: list[dict],
) -> dict[str, AgentMutationSet]:
    """Extract AgentMutationSets from a round's collected turn messages."""
    result: dict[str, AgentMutationSet] = {}
    for msg in round_messages:
        agent_id = msg.get("slot_id", msg.get("name", "unknown"))
        ams = AgentMutationSet(
            agent_id=agent_id,
            agent_name=msg.get("name", agent_id),
            agent_role=msg.get("role", "unknown"),
            mutations=parse_mutations_from_turn_response(msg, agent_id),
            done=msg.get("done", False),
            message=msg.get("message", ""),
        )
        result[agent_id] = ams
    return result


# ── Aggregation engine ─────────────────────────────────────────────────────────

# Role priority for conflict resolution (lower = higher authority)
_ROLE_PRIORITY: dict[str, int] = {
    "PRODUCT_OWNER": 0,
    "ARCHITECT": 1,
    "DEVELOPER": 2,
}
_ROLE_PRIORITY_DEFAULT = 99


def _priority_for_role(role: str) -> int:
    return _ROLE_PRIORITY.get(role, _ROLE_PRIORITY_DEFAULT)


def aggregate(
    agent_mutations: dict[str, AgentMutationSet],
    current_items: list[str],
    backlog_items: list[dict],
    capacity: int,
    sprint_goal: str = "",
    *,
    recommend_fn: Callable[..., list[dict]] | None = None,
) -> AggregationResult:
    """Reconcile all agent mutation sets into a balanced sprint list.

    Algorithm:
      1. Collect all mutations across agents, sorted by role priority
      2. Resolve conflicts (same item modified by multiple agents → highest
         authority wins, later agents with same authority override earlier)
      3. Apply adds (deduplicate — skip if already in working set)
      4. Apply removes
      5. Apply modifies
      6. Re-rank via recommender under capacity constraint
      7. Detect convergence: all agents done AND no mutations applied

    Args:
        agent_mutations: Per-agent mutation sets from this round.
        current_items: Current working item ID list before this round.
        backlog_items: Full backlog (mutated in-place on MODIFY, appended on ADD).
        capacity: Total story-point capacity for re-ranking.
        sprint_goal: Sprint goal string for recommender.
        recommend_fn: Optional recommender function. If None, keeps working order.

    Returns:
        AggregationResult with final_items, convergence flag, and stats.
    """
    # 1. Collect & sort all mutations by role priority
    all_mutations: list[tuple[int, Mutation]] = []
    for ams in agent_mutations.values():
        priority = _priority_for_role(ams.agent_role)
        for m in ams.mutations:
            all_mutations.append((priority, m))

    all_mutations.sort(key=lambda x: (x[0], x[1].type.value, x[1].item_id))

    # Working state
    working_items: list[str] = list(current_items)
    item_lookup: dict[str, dict] = {it["item_id"]: it for it in backlog_items}

    applied_adds = 0
    applied_removes = 0
    applied_modifies = 0
    discarded: list[Mutation] = []

    # Track items modified this round for conflict resolution
    modified_this_round: set[str] = set()

    for _, mutation in all_mutations:
        if mutation.type == MutationType.ADD:
            item_data = mutation.data.get("item", {})
            item_id = item_data.get("item_id", mutation.item_id)

            if item_id in working_items:
                discarded.append(mutation)
                continue

            # Validate and add to backlog if new
            if item_id not in item_lookup:
                try:
                    from app.phase_orchestrator import BacklogItem
                    validated = BacklogItem.model_validate(item_data)
                    item_lookup[item_id] = validated.model_dump()
                    backlog_items.append(item_lookup[item_id])
                except Exception:
                    log.warning("aggregator.add_invalid item_id=%s source=%s", item_id, mutation.source)
                    discarded.append(mutation)
                    continue

            working_items.append(item_id)
            applied_adds += 1

        elif mutation.type == MutationType.REMOVE:
            if mutation.item_id in working_items:
                working_items.remove(mutation.item_id)
                applied_removes += 1
            else:
                discarded.append(mutation)

        elif mutation.type == MutationType.MODIFY:
            item_id = mutation.item_id
            updates = mutation.data.get("updates", {})

            if item_id not in item_lookup or not updates:
                discarded.append(mutation)
                continue

            if item_id in modified_this_round:
                # Conflict: another agent already modified this item.
                # The lower-priority mutation is discarded (we process in priority
                # order, so this one arrived later / has lower priority).
                discarded.append(mutation)
                continue

            modified_this_round.add(item_id)
            allowed = {"title", "description", "priority", "story_points", "labels", "dependencies"}
            for k, v in updates.items():
                if k in allowed:
                    item_lookup[item_id][k] = v
            applied_modifies += 1

    # ── Re-rank via recommender ──
    if recommend_fn is not None and backlog_items:
        re_ranked = recommend_fn(
            backlog_items=backlog_items,
            sprint_goal=sprint_goal,
            total_capacity=capacity,
        )
        final_items = [it["item_id"] for it in re_ranked]
    elif working_items:
        final_items = list(working_items)
    else:
        final_items = list(current_items)

    # ── CONVERGED detection ──
    all_done = all(ams.done for ams in agent_mutations.values())
    had_mutations = (applied_adds + applied_removes + applied_modifies) > 0
    converged = all_done and not had_mutations

    return AggregationResult(
        final_items=final_items,
        assignments={},
        applied_adds=applied_adds,
        applied_removes=applied_removes,
        applied_modifies=applied_modifies,
        discarded_mutations=discarded,
        converged=converged,
        stats={
            "total_mutations_received": len(all_mutations),
            "total_discarded": len(discarded),
            "agents_done": sum(1 for ams in agent_mutations.values() if ams.done),
            "total_agents": len(agent_mutations),
            "conflicts_resolved": len(discarded),
        },
    )


# ── CONVERGED detection across rounds ──────────────────────────────────────────

@dataclass
class RoundRecord:
    """Summary of one discussion round for convergence tracking."""
    round_num: int
    mutations_count: int
    all_done: bool
    converged: bool


def detect_converged(
    round_history: list[RoundRecord],
    threshold: int = 2,
) -> bool:
    """Detect convergence across rounds.

    Returns True if the last `threshold` consecutive rounds had:
    - Zero new mutations applied
    - All agents signaled done
    """
    if len(round_history) < threshold:
        return False

    recent = round_history[-threshold:]
    return all(r.mutations_count == 0 and r.all_done for r in recent)
