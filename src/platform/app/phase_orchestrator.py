"""Phase Orchestrator for sprint_planning_v1 (US-04).

Now refactored to be a generic action executor based on YAML process templates (US-09).
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy import select

from app.a2a.client import A2AClient
from app.db import SessionLocal
from app.models import Session, SessionParticipant, Template

log = logging.getLogger(__name__)

_a2a = A2AClient(default_timeout_seconds=30.0)

ASSIGNMENT_TIMEOUT_SECONDS = 5.0


# ── US-26: Communication feed helper ─────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


async def _send_task_with_comm(
    session_id: str,
    receiver: "_SlotSnap",
    task_type: str,
    session_ctx: dict[str, Any],
    payload: dict[str, Any] | None = None,
    duration_limit_seconds: float | None = None,
) -> "TaskResult":
    """Wraps _a2a.send_task and emits CommEvents to the session comm feed."""
    from app.a2a.models import CommEvent
    from app.comm_bus import publish_comm_event

    receiver_id = receiver.participant_id or receiver.id

    await publish_comm_event(CommEvent(
        comm_id=str(uuid4()),
        session_id=session_id,
        timestamp=_now_iso(),
        sender_id="platform",
        sender_name="Platform",
        receiver_id=receiver_id,
        receiver_name=receiver.name,
        task_type=task_type,
        message_kind="task_request",
        content=payload or {},
    ))

    async def _on_progress(thought: str) -> None:
        await publish_comm_event(CommEvent(
            comm_id=str(uuid4()),
            session_id=session_id,
            timestamp=_now_iso(),
            sender_id=receiver_id,
            sender_name=receiver.name,
            receiver_id=None,
            receiver_name=None,
            task_type=task_type,
            message_kind="thought",
            content=thought,
        ))

    result = await _a2a.send_task(
        endpoint=receiver.endpoint,
        task_type=task_type,
        session_ctx=session_ctx,
        payload=payload,
        duration_limit_seconds=duration_limit_seconds,
        on_progress=_on_progress,
    )

    await publish_comm_event(CommEvent(
        comm_id=str(uuid4()),
        session_id=session_id,
        timestamp=_now_iso(),
        sender_id=receiver_id,
        sender_name=receiver.name,
        receiver_id="platform",
        receiver_name="Platform",
        task_type=task_type,
        message_kind="task_response",
        content=(
            result.artifact
            if result.artifact is not None
            else {"status": result.status.value, **({"error": result.error} if result.error else {})}
        ),
    ))

    return result

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

        template_result = await db.execute(select(Template).where(Template.id == row.template))
        template_row = template_result.scalar_one_or_none()
        if not template_row:
            log.error("orchestrator.missing_template session_id=%s template=%s", session_id, row.template)
            return

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

    # Mutable orchestration state
    backlog_items: list[dict] | None = (row.context or {}).get("backlog_items", None)
    selected_items: list[str] | None = (row.context or {}).get("selected_items", None)
    assignments: dict[str, str] = (row.context or {}).get("assignments", {})
    phase_history: list[dict] = (row.context or {}).get("phase_history", [])

    for phase in template_row.phases:
        phase_id = phase["phase_id"]
        phase_name = phase["name"]
        log.info("orchestrator.phase.start session_id=%s phase_id=%s", session_id, phase_id)

        action_context = {}
        outcome = ""

        for action in phase.get("actions", []):
            action_type = action.get("type")
            log.info("orchestrator.action.start session_id=%s phase_id=%s action=%s", session_id, phase_id, action_type)

            if action_type == "PRESENT_ITEMS":
                backlog_items = await _handle_present_items(session, slots, phase_id, phase_name, assignments, phase_history)
                outcome = f"{len(backlog_items)} items received"
            elif action_type == "VOTE":
                vote_scores = await _handle_vote(session, slots, backlog_items or [], phase_id, phase_name, assignments, phase_history)
                action_context["vote_scores"] = vote_scores
            elif action_type == "SELECT":
                selected_items = await _handle_select(session, backlog_items or [], action_context.get("vote_scores", {}))
                outcome = f"{len(selected_items)} items selected"
            elif action_type == "ASSIGN":
                assignments = await _handle_assign(session, slots, backlog_items or [], selected_items or [], assignments, phase_id, phase_name, phase_history)
                outcome = f"{len(assignments)} items assigned"
            elif action_type == "CONFIRM":
                quorum = await _handle_confirm(session, slots, backlog_items or [], selected_items or [], assignments, phase_id, phase_name, phase_history)
                outcome = f"quorum {quorum:.0%}"

        phase_history.append({
            "phase_id": phase_id,
            "completed_at": datetime.now(tz=timezone.utc).isoformat(),
            "outcome": outcome,
        })

        updates = {"phase_history": phase_history}
        if backlog_items is not None:
            updates["backlog_items"] = backlog_items
        if selected_items is not None:
            updates["selected_items"] = selected_items
        if assignments:
            updates["assignments"] = assignments
        await _commit_ctx(session_id, updates)
        log.info("orchestrator.phase.done session_id=%s phase_id=%s outcome=%s", session_id, phase_id, outcome)

    # ── Transition to COMPLETED ───────────────────
    async with SessionLocal() as db:
        result = await db.execute(select(Session).where(Session.id == session_id))
        session_row = result.scalar_one()
        _guard_transition(session_row, "COMPLETED")
        session_row.status = "COMPLETED"
        await db.commit()

    log.info("orchestrator.completed session_id=%s", session_id)

    # ── US-08: Build and broadcast the final sprint backlog ───────────────────
    sprint_backlog = _build_sprint_backlog(
        session=session,
        slots=slots,
        backlog_items=backlog_items or [],
        selected_items=selected_items or [],
        assignments=assignments,
    )
    await _broadcast_sprint_backlog(sprint_backlog, slots)


def _guard_transition(session: Session, target: str) -> None:
    _ALLOWED: dict[str, set[str]] = {
        "PENDING": {"ACTIVE", "ABORTED"},
        "ACTIVE": {"COMPLETED"},
        "COMPLETED": set(),
        "ABORTED": set(),
    }
    if target not in _ALLOWED.get(session.status, set()):
        raise ValueError(f"Illegal transition {session.status!r} → {target!r}")


# ── US-08: Sprint Backlog Output ──────────────────────────────────────────────


def _build_sprint_backlog(
    *,
    session: _SessionSnap,
    slots: list[_SlotSnap],
    backlog_items: list[dict],
    selected_items: list[str],
    assignments: dict[str, str],
) -> dict[str, Any]:
    # Build lookup maps
    item_lookup: dict[str, dict] = {item["item_id"]: item for item in backlog_items}
    name_lookup: dict[str, str] = {
        s.participant_id: s.name for s in slots if s.participant_id
    }

    selected_item_entries: list[dict] = []
    for item_id in selected_items:
        item = item_lookup.get(item_id, {"item_id": item_id})
        assignee_id = assignments.get(item_id)
        assignee_name = name_lookup.get(assignee_id, assignee_id) if assignee_id else None
        selected_item_entries.append({
            "item_id": item.get("item_id", item_id),
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "priority": item.get("priority", "LOW"),
            "story_points": item.get("story_points"),
            "labels": item.get("labels", []),
            "dependencies": item.get("dependencies", []),
            "assignee_id": assignee_id,
            "assignee_name": assignee_name,
        })

    capacity_by_assignee: dict[str, int] = {}
    for entry in selected_item_entries:
        aid = entry["assignee_id"]
        if aid:
            sp = entry["story_points"] or 0
            capacity_by_assignee[aid] = capacity_by_assignee.get(aid, 0) + sp

    capacity_plan: list[dict] = [
        {
            "assignee_id": aid,
            "assignee_name": name_lookup.get(aid, aid),
            "item_count": sum(
                1 for e in selected_item_entries if e["assignee_id"] == aid
            ),
            "total_story_points": sp,
        }
        for aid, sp in capacity_by_assignee.items()
    ]

    return {
        "session_id": session.id,
        "sprint_goal": session.sprint_goal,
        "selected_items": selected_item_entries,
        "capacity_plan": capacity_plan,
    }


async def _broadcast_sprint_backlog(
    sprint_backlog: dict[str, Any],
    slots: list[_SlotSnap],
) -> None:
    all_joined = _reachable_slots(slots)

    async def deliver(slot: _SlotSnap) -> None:
        try:
            session_ctx = {
                "session_id": sprint_backlog["session_id"],
                "sprint_goal": sprint_backlog["sprint_goal"],
            }
            await _send_task_with_comm(
                sprint_backlog["session_id"], slot, "sprint_backlog",
                session_ctx, sprint_backlog,
            )
            log.info(
                "sprint_backlog.delivered session_id=%s slot=%s",
                sprint_backlog["session_id"], slot.id,
            )
        except Exception as exc:
            log.warning(
                "sprint_backlog.delivery_failed session_id=%s slot=%s exc=%s",
                sprint_backlog["session_id"], slot.id, exc,
            )

    await asyncio.gather(*[deliver(s) for s in all_joined], return_exceptions=True)


# ── Action Handlers ─────────────────────────────────────────────────────────────


async def _handle_present_items(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    phase_id: str,
    phase_name: str,
    assignments: dict[str, str],
    phase_history: list[dict],
) -> list[dict]:
    po_slots = _reachable_slots(slots, roles={"PRODUCT_OWNER"})
    if not po_slots:
        raise RuntimeError("No reachable PRODUCT_OWNER slot for PRESENT_ITEMS")

    ctx = _build_ctx(
        session, slots, phase_id, phase_name, 1,
        None, None, assignments, phase_history,
    )
    po = po_slots[0]
    result = await _send_task_with_comm(
        session.id, po, "present_backlog", ctx, {},
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
                "orchestrator.present_items.invalid_item item_id=%s err=%s",
                raw.get("item_id"), exc,
            )

    if not validated:
        raise RuntimeError("No valid backlog items returned by PRODUCT_OWNER")

    return validated


async def _handle_vote(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    backlog_items: list[dict],
    phase_id: str,
    phase_name: str,
    assignments: dict[str, str],
    phase_history: list[dict],
) -> dict[str, int]:
    all_reachable = _reachable_slots(slots)
    item_ids = [item["item_id"] for item in backlog_items]

    ctx = _build_ctx(
        session, slots, phase_id, phase_name, 1,
        backlog_items, None, assignments, phase_history,
    )

    async def get_votes(slot: _SlotSnap) -> dict[str, str]:
        r = await _send_task_with_comm(
            session.id, slot, "vote", ctx, {"items": item_ids},
        )
        if not r.ok:
            log.warning(
                "orchestrator.vote_failed slot=%s err=%s", slot.id, r.error
            )
            return {}
        return (r.artifact or {}).get("votes", {})

    vote_results = await asyncio.gather(
        *[get_votes(s) for s in all_reachable], return_exceptions=True
    )

    scores: dict[str, int] = {iid: 0 for iid in item_ids}
    for v in vote_results:
        if isinstance(v, dict):
            for iid, priority in v.items():
                if iid in scores:
                    scores[iid] += _PRIORITY_SCORE.get(str(priority), 0)

    return scores


async def _handle_select(
    session: _SessionSnap,
    backlog_items: list[dict],
    vote_scores: dict[str, int],
) -> list[str]:
    item_ids = [item["item_id"] for item in backlog_items]
    ranked = sorted(item_ids, key=lambda iid: vote_scores.get(iid, 0), reverse=True)

    if session.sprint_capacity is None:
        return ranked

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
    return selected or ranked[:1]


async def _handle_assign(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    backlog_items: list[dict],
    selected_items: list[str],
    initial_assignments: dict[str, str],
    phase_id: str,
    phase_name: str,
    phase_history: list[dict],
) -> dict[str, str]:
    assignments = dict(initial_assignments)
    eligible = _reachable_slots(slots, roles={"DEVELOPER", "ARCHITECT"})
    all_reachable = _reachable_slots(slots)

    if not eligible:
        log.warning("orchestrator.assign.no_eligible session_id=%s", session.id)
        return assignments

    item_lookup = {item["item_id"]: item for item in backlog_items}

    for item_id in selected_items:
        item = item_lookup.get(item_id, {"item_id": item_id, "title": item_id, "description": ""})
        assignee_id, reason = await _assign_item(
            session, slots, eligible, backlog_items, selected_items, item, assignments, phase_id, phase_name, phase_history
        )
        if assignee_id:
            assignments[item_id] = assignee_id
            await _broadcast_acknowledge(
                session, slots, all_reachable,
                item_id, assignee_id, reason,
                backlog_items, selected_items, assignments, phase_id, phase_name, phase_history,
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
    phase_id: str,
    phase_name: str,
    phase_history: list[dict],
) -> tuple[str | None, str]:
    ctx = _build_ctx(
        session, slots, phase_id, phase_name, 1,
        backlog_items, selected_items, assignments, phase_history,
    )

    async def request_volunteer(slot: _SlotSnap) -> _SlotSnap | None:
        r = await _send_task_with_comm(
            session.id, slot, "assign_opportunity", ctx,
            {"item_id": item["item_id"], "title": item.get("title", "")},
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
        winner = _pick_lowest_load(eligible, assignments)
        return (winner.participant_id if winner else None, "AUTO_BALANCE")

    if len(volunteers) == 1:
        return (volunteers[0].participant_id, "VOLUNTEERED")

    winner = _pick_lowest_load(volunteers, assignments)
    return (winner.participant_id if winner else volunteers[0].participant_id, "CONFLICT_RESOLVED")


def _pick_lowest_load(slots: list[_SlotSnap], assignments: dict[str, str]) -> _SlotSnap | None:
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
    phase_id: str,
    phase_name: str,
    phase_history: list[dict],
) -> None:
    assignee_name = next(
        (s.name for s in slots if s.participant_id == assignee_id), assignee_id
    )
    ctx = _build_ctx(
        session, slots, phase_id, phase_name, 1,
        backlog_items, selected_items, assignments, phase_history,
    )

    async def notify(slot: _SlotSnap) -> None:
        try:
            await _send_task_with_comm(
                session.id, slot, "acknowledge_assignment", ctx,
                {
                    "item_id": item_id,
                    "assignee_id": assignee_id,
                    "assignee_name": assignee_name,
                    "reason": reason,
                },
            )
        except Exception as exc:
            log.warning("orchestrator.assign.ack_failed slot=%s exc=%s", slot.id, exc)

    await asyncio.gather(*[notify(s) for s in all_reachable], return_exceptions=True)


async def _handle_confirm(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    backlog_items: list[dict],
    selected_items: list[str],
    assignments: dict[str, str],
    phase_id: str,
    phase_name: str,
    phase_history: list[dict],
) -> float:
    reachable = _reachable_slots(slots)
    total = len(reachable)
    if total == 0:
        return 1.0

    ctx = _build_ctx(
        session, slots, phase_id, phase_name, 1,
        backlog_items, selected_items, assignments, phase_history,
    )

    async def get_confirm(slot: _SlotSnap) -> bool:
        r = await _send_task_with_comm(
            session.id, slot, "confirm", ctx,
            {
                "sprint_goal": session.sprint_goal,
                "selected_items": selected_items,
                "assignments": assignments,
            },
        )
        if not r.ok:
            log.warning(
                "orchestrator.confirm_failed slot=%s err=%s", slot.id, r.error
            )
            return False
        artifact = r.artifact or {}
        return bool(artifact.get("confirmed", artifact.get("ack", False)))

    results = await asyncio.gather(*[get_confirm(s) for s in reachable], return_exceptions=True)
    confirmed_count = sum(1 for r in results if r is True)
    quorum = confirmed_count / total
    log.info(
        "orchestrator.confirm confirmed=%d total=%d quorum=%.2f",
        confirmed_count, total, quorum,
    )
    return quorum
