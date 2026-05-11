"""Phase Orchestrator for sprint_planning_v1 (US-04).

Hard-coded four-phase execution for the baseline template:
  1. Backlog Presentation  – present_backlog → PRODUCT_OWNER
  2. Prioritisation        – vote (parallel, all joined) → tally dot votes → greedy select
  3. Assignment            – assign_opportunity per item (5 s timeout) → VOLUNTEER_FIRST / AUTO_BALANCE
  4. Confirmation          – confirm (parallel, all joined) → quorum ≥ 0.75 → COMPLETED

Design invariants:
  AC5: Every outbound A2A task carries the full session_ctx (late-populated fields are None).
  AC6: phase_history appended with phase_id, completed_at, outcome at each transition.
  AC7: Load for tie-breaking counted from session_ctx.assignments only.
  AC8: Context is committed to DB only at phase boundaries; partial phase state is never persisted.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy import select

from app.a2a.client import A2AClient
from app.db import SessionLocal
from app.models import Session, SessionParticipant

log = logging.getLogger(__name__)

_a2a = A2AClient(default_timeout_seconds=30.0)

ASSIGNMENT_TIMEOUT_SECONDS = 5.0

# ── Immutable snapshots (avoid detached-ORM-instance issues) ──────────────────


@dataclass(frozen=True)
class _SessionSnap:
    id: str
    sprint_goal: str
    template: str
    sprint_capacity: int | None  # story points; None = no capacity limit


@dataclass(frozen=True)
class _SlotSnap:
    id: str
    participant_id: str | None
    name: str
    role: str
    slot_type: str   # "AGENT" | "HUMAN"
    endpoint: str | None
    status: str      # "declared" | "joined" | "absent"


# ── Backlog Item schema (AC1) ─────────────────────────────────────────────────


class BacklogItem(BaseModel):
    item_id: str
    title: str
    description: str
    priority: str
    story_points: int | None = None
    labels: list[str] = []
    dependencies: list[str] = []

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v: str) -> str:
        if v not in ("HIGH", "MEDIUM", "LOW"):
            raise ValueError(f"invalid priority: {v!r}")
        return v


# ── Vote scoring ──────────────────────────────────────────────────────────────

_PRIORITY_SCORE: dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _reachable_slots(slots: list[_SlotSnap], *, roles: set[str] | None = None) -> list[_SlotSnap]:
    """Joined slots that have an A2A endpoint, optionally filtered by role."""
    return [
        s for s in slots
        if s.status == "joined" and s.endpoint
        and (roles is None or s.role in roles)
    ]


def _build_ctx(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    phase_id: str,
    phase_name: str,
    turn: int,
    backlog_items: list[dict] | None,
    selected_items: list[str] | None,
    assignments: dict[str, str],
    phase_history: list[dict],
) -> dict[str, Any]:
    """Construct the full session_ctx payload (AC5)."""
    return {
        "session_id": session.id,
        "sprint_goal": session.sprint_goal,
        "template_id": session.template,
        "current_phase": {"phase_id": phase_id, "name": phase_name, "turn": turn},
        "participants": [
            {
                "participant_id": s.participant_id,
                "name": s.name,
                "role": s.role,
                "type": "AI_AGENT" if s.slot_type == "AGENT" else "HUMAN",
            }
            for s in slots
        ],
        "backlog_items": backlog_items,
        "selected_items": selected_items,
        "assignments": assignments,
        "phase_history": phase_history,
    }


async def _commit_ctx(session_id: str, updates: dict[str, Any]) -> None:
    """Atomically merge updates into session.context (AC8: only called at phase boundaries)."""
    async with SessionLocal() as db:
        result = await db.execute(select(Session).where(Session.id == session_id))
        row = result.scalar_one()
        ctx = dict(row.context or {})
        ctx.update(updates)
        row.context = ctx
        await db.commit()


# ── Entry point ───────────────────────────────────────────────────────────────


async def run_orchestrator(session_id: str) -> None:
    log.info("orchestrator.start session_id=%s", session_id)
    try:
        await _orchestrate(session_id)
    except Exception as exc:
        log.exception("orchestrator.fatal session_id=%s exc=%s", session_id, exc)


async def _orchestrate(session_id: str) -> None:
    async with SessionLocal() as db:
        result = await db.execute(select(Session).where(Session.id == session_id))
        row = result.scalar_one_or_none()
        if row is None or row.status != "ACTIVE":
            log.warning(
                "orchestrator.skip session_id=%s status=%s",
                session_id, getattr(row, "status", "missing"),
            )
            return

        slots_result = await db.execute(
            select(SessionParticipant).where(SessionParticipant.session_id == session_id)
        )
        slot_rows = list(slots_result.scalars())

        session = _SessionSnap(
            id=row.id,
            sprint_goal=row.sprint_goal,
            template=row.template,
            sprint_capacity=(row.context or {}).get("sprint_capacity"),
        )
        slots = [
            _SlotSnap(
                id=s.id,
                participant_id=s.participant_id,
                name=s.name,
                role=s.role,
                slot_type=s.slot_type,
                endpoint=s.endpoint,
                status=s.status,
            )
            for s in slot_rows
        ]

    # Mutable orchestration state (never written to DB mid-phase — AC8)
    backlog_items: list[dict] | None = None
    selected_items: list[str] | None = None
    assignments: dict[str, str] = {}
    phase_history: list[dict] = []

    # ── Phase 1: Backlog Presentation ─────────────────────────────────────────
    log.info("orchestrator.phase1.start session_id=%s", session_id)
    backlog_items = await _phase1_backlog_presentation(session, slots, phase_history, assignments)
    phase_history.append({
        "phase_id": "backlog_presentation",
        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
        "outcome": f"{len(backlog_items)} items received from PRODUCT_OWNER",
    })
    await _commit_ctx(session_id, {"backlog_items": backlog_items, "phase_history": phase_history})
    log.info("orchestrator.phase1.done session_id=%s items=%d", session_id, len(backlog_items))

    # ── Phase 2: Prioritisation ───────────────────────────────────────────────
    log.info("orchestrator.phase2.start session_id=%s", session_id)
    selected_items = await _phase2_prioritisation(
        session, slots, backlog_items, phase_history, assignments
    )
    phase_history.append({
        "phase_id": "prioritization",
        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
        "outcome": f"{len(selected_items)} of {len(backlog_items)} items selected",
    })
    await _commit_ctx(session_id, {"selected_items": selected_items, "phase_history": phase_history})
    log.info("orchestrator.phase2.done session_id=%s selected=%d", session_id, len(selected_items))

    # ── Phase 3: Assignment ───────────────────────────────────────────────────
    log.info("orchestrator.phase3.start session_id=%s", session_id)
    assignments = await _phase3_assignment(
        session, slots, backlog_items, selected_items, phase_history, assignments
    )
    phase_history.append({
        "phase_id": "assignment",
        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
        "outcome": f"{len(assignments)} of {len(selected_items)} items assigned",
    })
    await _commit_ctx(session_id, {"assignments": assignments, "phase_history": phase_history})
    log.info("orchestrator.phase3.done session_id=%s assigned=%d", session_id, len(assignments))

    # ── Phase 4: Confirmation ─────────────────────────────────────────────────
    log.info("orchestrator.phase4.start session_id=%s", session_id)
    quorum = await _phase4_confirmation(
        session, slots, backlog_items, selected_items, assignments, phase_history
    )
    phase_history.append({
        "phase_id": "confirmation",
        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
        "outcome": f"quorum {quorum:.0%} ({'reached' if quorum >= 0.75 else 'below threshold'})",
    })
    log.info("orchestrator.phase4.done session_id=%s quorum=%.2f", session_id, quorum)

    # ── Transition to COMPLETED (AC8: single atomic commit) ───────────────────
    async with SessionLocal() as db:
        result = await db.execute(select(Session).where(Session.id == session_id))
        session_row = result.scalar_one()
        _guard_transition(session_row, "COMPLETED")
        session_row.status = "COMPLETED"
        ctx = dict(session_row.context or {})
        ctx["phase_history"] = phase_history
        session_row.context = ctx
        await db.commit()

    log.info("orchestrator.completed session_id=%s", session_id)


def _guard_transition(session: Session, target: str) -> None:
    _ALLOWED: dict[str, set[str]] = {
        "PENDING": {"ACTIVE", "ABORTED"},
        "ACTIVE": {"COMPLETED"},
        "COMPLETED": set(),
        "ABORTED": set(),
    }
    if target not in _ALLOWED.get(session.status, set()):
        raise ValueError(f"Illegal transition {session.status!r} → {target!r}")


# ── Phase 1: Backlog Presentation ─────────────────────────────────────────────


async def _phase1_backlog_presentation(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    phase_history: list[dict],
    assignments: dict[str, str],
) -> list[dict]:
    po_slots = _reachable_slots(slots, roles={"PRODUCT_OWNER"})
    if not po_slots:
        raise RuntimeError("No reachable PRODUCT_OWNER slot for phase 1")

    ctx = _build_ctx(
        session, slots, "backlog_presentation", "Backlog Presentation", 1,
        None, None, assignments, phase_history,
    )
    po = po_slots[0]
    result = await _a2a.send_task(
        endpoint=po.endpoint,
        task_type="present_backlog",
        session_ctx=ctx,
        payload={},
    )
    if not result.ok:
        raise RuntimeError(f"present_backlog failed for slot {po.id}: {result.error}")

    raw_items: list[dict] = (result.artifact or {}).get("backlog", [])

    validated: list[dict] = []
    for raw in raw_items:
        try:
            item = BacklogItem.model_validate(raw)
            validated.append(item.model_dump())
        except ValidationError as exc:
            log.warning(
                "orchestrator.phase1.invalid_item item_id=%s err=%s",
                raw.get("item_id"), exc,
            )

    if not validated:
        raise RuntimeError("No valid backlog items returned by PRODUCT_OWNER")

    return validated


# ── Phase 2: Prioritisation ───────────────────────────────────────────────────


async def _phase2_prioritisation(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    backlog_items: list[dict],
    phase_history: list[dict],
    assignments: dict[str, str],
) -> list[str]:
    all_reachable = _reachable_slots(slots)
    item_ids = [item["item_id"] for item in backlog_items]

    ctx = _build_ctx(
        session, slots, "prioritization", "Prioritisation", 1,
        backlog_items, None, assignments, phase_history,
    )

    async def get_votes(slot: _SlotSnap) -> dict[str, str]:
        r = await _a2a.send_task(
            endpoint=slot.endpoint,
            task_type="vote",
            session_ctx=ctx,
            payload={"items": item_ids},
        )
        if not r.ok:
            log.warning(
                "orchestrator.phase2.vote_failed slot=%s err=%s", slot.id, r.error
            )
            return {}
        return (r.artifact or {}).get("votes", {})

    vote_results = await asyncio.gather(
        *[get_votes(s) for s in all_reachable], return_exceptions=True
    )

    # Tally dot votes (AC2)
    scores: dict[str, int] = {iid: 0 for iid in item_ids}
    for v in vote_results:
        if isinstance(v, dict):
            for iid, priority in v.items():
                if iid in scores:
                    scores[iid] += _PRIORITY_SCORE.get(str(priority), 0)

    ranked = sorted(item_ids, key=lambda iid: scores[iid], reverse=True)

    if session.sprint_capacity is None:
        return ranked  # no capacity limit → select all ranked items

    # Greedy selection by story points (AC2)
    sp_lookup: dict[str, int] = {
        item["item_id"]: (item.get("story_points") or 1) for item in backlog_items
    }
    selected: list[str] = []
    used = 0
    for iid in ranked:
        sp = sp_lookup[iid]
        if used + sp <= session.sprint_capacity:
            selected.append(iid)
            used += sp
    return selected or ranked[:1]   # always select at least one item


# ── Phase 3: Assignment ───────────────────────────────────────────────────────


async def _phase3_assignment(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    backlog_items: list[dict],
    selected_items: list[str],
    phase_history: list[dict],
    initial_assignments: dict[str, str],
) -> dict[str, str]:
    assignments = dict(initial_assignments)
    eligible = _reachable_slots(slots, roles={"DEVELOPER", "ARCHITECT"})
    all_reachable = _reachable_slots(slots)

    if not eligible:
        log.warning("orchestrator.phase3.no_eligible session_id=%s", session.id)
        return assignments

    item_lookup = {item["item_id"]: item for item in backlog_items}

    for item_id in selected_items:
        item = item_lookup.get(item_id, {"item_id": item_id, "title": item_id, "description": ""})
        assignee_id, reason = await _assign_item(
            session, slots, eligible, backlog_items, selected_items, item, assignments, phase_history
        )
        if assignee_id:
            assignments[item_id] = assignee_id
            # Broadcast assignment with the updated assignments map (AC3)
            await _broadcast_acknowledge(
                session, slots, all_reachable,
                item_id, assignee_id, reason,
                backlog_items, selected_items, assignments, phase_history,
            )

    return assignments


async def _assign_item(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    eligible: list[_SlotSnap],
    backlog_items: list[dict],
    selected_items: list[str],
    item: dict,
    assignments: dict[str, str],
    phase_history: list[dict],
) -> tuple[str | None, str]:
    """VOLUNTEER_FIRST → AUTO_BALANCE decision tree (AC3). Returns (assignee_id, reason)."""
    ctx = _build_ctx(
        session, slots, "assignment", "Assignment", 1,
        backlog_items, selected_items, assignments, phase_history,
    )

    async def request_volunteer(slot: _SlotSnap) -> _SlotSnap | None:
        r = await _a2a.send_task(
            endpoint=slot.endpoint,
            task_type="assign_opportunity",
            session_ctx=ctx,
            payload={"item_id": item["item_id"], "title": item.get("title", "")},
            duration_limit_seconds=ASSIGNMENT_TIMEOUT_SECONDS,
        )
        if not r.ok:
            return None
        if (r.artifact or {}).get("volunteer"):
            return slot
        return None

    raw = await asyncio.gather(
        *[request_volunteer(s) for s in eligible], return_exceptions=True
    )
    volunteers: list[_SlotSnap] = [v for v in raw if isinstance(v, _SlotSnap)]

    if not volunteers:
        # AUTO_BALANCE: lowest-load participant (AC3, AC7)
        winner = _pick_lowest_load(eligible, assignments)
        return (winner.participant_id if winner else None, "AUTO_BALANCE")

    if len(volunteers) == 1:
        return (volunteers[0].participant_id, "VOLUNTEERED")

    # Multiple volunteers → CONFLICT_RESOLVED: pick by lowest load (AC3, AC7)
    winner = _pick_lowest_load(volunteers, assignments)
    return (winner.participant_id if winner else volunteers[0].participant_id, "CONFLICT_RESOLVED")


def _pick_lowest_load(slots: list[_SlotSnap], assignments: dict[str, str]) -> _SlotSnap | None:
    """Pick the slot with the fewest current-session assignments (AC7: no external queries)."""
    if not slots:
        return None
    load: dict[str | None, int] = {s.participant_id: 0 for s in slots}
    for pid in assignments.values():
        if pid in load:
            load[pid] += 1
    min_load = min(load.values())
    candidates = [s for s in slots if load.get(s.participant_id, 0) == min_load]
    return random.choice(candidates)


async def _broadcast_acknowledge(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    all_reachable: list[_SlotSnap],
    item_id: str,
    assignee_id: str,
    reason: str,
    backlog_items: list[dict],
    selected_items: list[str],
    assignments: dict[str, str],
    phase_history: list[dict],
) -> None:
    assignee_name = next(
        (s.name for s in slots if s.participant_id == assignee_id), assignee_id
    )
    ctx = _build_ctx(
        session, slots, "assignment", "Assignment", 1,
        backlog_items, selected_items, assignments, phase_history,
    )

    async def notify(slot: _SlotSnap) -> None:
        try:
            await _a2a.send_task(
                endpoint=slot.endpoint,
                task_type="acknowledge_assignment",
                session_ctx=ctx,
                payload={
                    "item_id": item_id,
                    "assignee_id": assignee_id,
                    "assignee_name": assignee_name,
                    "reason": reason,
                },
            )
        except Exception as exc:
            log.warning("orchestrator.phase3.ack_failed slot=%s exc=%s", slot.id, exc)

    await asyncio.gather(*[notify(s) for s in all_reachable], return_exceptions=True)


# ── Phase 4: Confirmation ─────────────────────────────────────────────────────


async def _phase4_confirmation(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    backlog_items: list[dict],
    selected_items: list[str],
    assignments: dict[str, str],
    phase_history: list[dict],
) -> float:
    """Send confirm to all reachable slots; return quorum fraction (AC4)."""
    reachable = _reachable_slots(slots)
    total = len(reachable)
    if total == 0:
        return 1.0

    ctx = _build_ctx(
        session, slots, "confirmation", "Confirmation", 1,
        backlog_items, selected_items, assignments, phase_history,
    )

    async def get_confirm(slot: _SlotSnap) -> bool:
        r = await _a2a.send_task(
            endpoint=slot.endpoint,
            task_type="confirm",
            session_ctx=ctx,
            payload={
                "sprint_goal": session.sprint_goal,
                "selected_items": selected_items,
                "assignments": assignments,
            },
        )
        if not r.ok:
            log.warning(
                "orchestrator.phase4.confirm_failed slot=%s err=%s", slot.id, r.error
            )
            return False
        artifact = r.artifact or {}
        # Accept both {confirmed: true} and legacy {ack: true} responses
        return bool(artifact.get("confirmed", artifact.get("ack", False)))

    results = await asyncio.gather(*[get_confirm(s) for s in reachable], return_exceptions=True)
    confirmed_count = sum(1 for r in results if r is True)
    quorum = confirmed_count / total
    log.info(
        "orchestrator.phase4 confirmed=%d total=%d quorum=%.2f",
        confirmed_count, total, quorum,
    )
    return quorum
