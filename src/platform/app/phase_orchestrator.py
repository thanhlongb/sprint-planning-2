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
    human_messages: list[dict] | None = None,
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
        "human_messages": human_messages or [],
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


async def _refresh_human_messages(session_id: str) -> list[dict]:
    """Re-read human_messages from DB so agents see messages sent since last action."""
    async with SessionLocal() as db:
        result = await db.execute(select(Session).where(Session.id == session_id))
        row = result.scalar_one_or_none()
        if row is None:
            return []
        return (row.context or {}).get("human_messages", [])


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

    # US-33: Detect template version (v1 vs v2)
    is_v2 = "v2" in session.template.lower()
    log.info(
        "orchestrator.template_version session_id=%s template=%s is_v2=%s",
        session_id, session.template, is_v2,
    )

    # US-35: Convergence metrics tracking (nullable — v1 sessions don't populate)
    recommendation_rounds: int | None = None
    assignment_rounds: int | None = None
    initial_recommendation: list[str] | None = None
    retention_pct: float | None = None

    # ── v2: fetch backlog from PO before recommendation phase if needed ────────
    if is_v2 and backlog_items is None:
        human_messages_init = await _refresh_human_messages(session_id)
        try:
            backlog_items = await _handle_present_items(
                session, slots, "init", "Backlog Fetch", {}, [], human_messages_init,
            )
            log.info("orchestrator.v2.fetched_backlog session_id=%s count=%d", session_id, len(backlog_items))
        except Exception:
            log.warning("orchestrator.v2.no_backlog session_id=%s", session_id)
            backlog_items = []

    for phase in template_row.phases:
        phase_id = phase["phase_id"]
        phase_name = phase["name"]
        log.info("orchestrator.phase.start session_id=%s phase_id=%s", session_id, phase_id)

        action_context: dict[str, Any] = {}
        outcome = ""

        for action in phase.get("actions", []):
            action_type = action.get("type")
            log.info("orchestrator.action.start session_id=%s phase_id=%s action=%s", session_id, phase_id, action_type)

            # Refresh human messages from DB before each task dispatch (US-27 AC4)
            human_messages: list[dict] = await _refresh_human_messages(session_id)

            # ── v1 actions (retained for compatibility, US-33 AC6) ──────
            if action_type == "PRESENT_ITEMS":
                backlog_items = await _handle_present_items(session, slots, phase_id, phase_name, assignments, phase_history, human_messages)
                outcome = f"{len(backlog_items)} items received"
            elif action_type == "VOTE":
                vote_scores = await _handle_vote(session, slots, backlog_items or [], phase_id, phase_name, assignments, phase_history, human_messages)
                action_context["vote_scores"] = vote_scores
            elif action_type == "SELECT":
                selected_items = await _handle_select(session, backlog_items or [], action_context.get("vote_scores", {}))
                outcome = f"{len(selected_items)} items selected"
            elif action_type == "ASSIGN":
                assignments = await _handle_assign(session, slots, backlog_items or [], selected_items or [], assignments, phase_id, phase_name, phase_history, human_messages)
                outcome = f"{len(assignments)} items assigned"
            elif action_type == "CONFIRM":
                quorum = await _handle_confirm(
                    session, slots, backlog_items or [], selected_items or [],
                    assignments, phase_id, phase_name, phase_history, human_messages,
                    is_v2=is_v2,
                )
                if is_v2:
                    outcome = f"po_confirmed={quorum:.0%}"
                    # US-35 AC4: Calculate retention_pct at confirmation
                    if initial_recommendation:
                        final_set = set(selected_items or [])
                        initial_set = set(initial_recommendation)
                        if initial_set:
                            retention_pct = len(final_set & initial_set) / len(initial_set)
                else:
                    outcome = f"quorum {quorum:.0%}"

            # ── v2 actions (US-33 AC4) ──────────────────────────────────
            elif action_type == "GENERATE_RECOMMENDATION":
                if not is_v2:
                    log.warning("orchestrator.v2_action_in_v1 session_id=%s action=%s", session_id, action_type)
                    continue

                # Get discussion config from the next OPEN_DISCUSSION action if present
                disc_cfg: dict[str, Any] = {}
                actions_list = phase.get("actions", [])
                for i, a in enumerate(actions_list):
                    if a is action:
                        if i + 1 < len(actions_list) and actions_list[i + 1].get("type") == "OPEN_DISCUSSION":
                            next_a = actions_list[i + 1]
                            disc_cfg = {
                                "allowed_actions": next_a.get("allowed_actions", []),
                                "timeout_seconds": next_a.get("timeout_seconds", 60),
                            }
                        break

                rec_items, rec_rounds = await _handle_recommend(
                    session, slots, backlog_items or [],
                    phase_id, phase_name, phase_history, human_messages,
                    discussion_config=disc_cfg,
                )
                selected_items = rec_items
                # US-35 AC1: Snapshot initial recommendation
                initial_recommendation = list(rec_items)
                recommendation_rounds = rec_rounds
                outcome = f"{len(rec_items)} items recommended, {rec_rounds} rounds"

            elif action_type == "GENERATE_ASSIGNMENT":
                if not is_v2:
                    log.warning("orchestrator.v2_action_in_v1 session_id=%s action=%s", session_id, action_type)
                    continue

                # Run expertise-based assignment
                gen_assignments = await _handle_generate_assignment(
                    session, slots, backlog_items or [], selected_items or [],
                    phase_id, phase_name, phase_history, human_messages,
                )
                assignments = gen_assignments

                # Get discussion config from OPEN_DISCUSSION if it follows
                disc_cfg = {}
                actions_list = phase.get("actions", [])
                for i, a in enumerate(actions_list):
                    if a is action:
                        if i + 1 < len(actions_list) and actions_list[i + 1].get("type") == "OPEN_DISCUSSION":
                            next_a = actions_list[i + 1]
                            disc_cfg = {
                                "allowed_actions": next_a.get("allowed_actions", []),
                                "timeout_seconds": next_a.get("timeout_seconds", 60),
                            }
                        break

                # Enter discussion if configured
                if disc_cfg.get("allowed_actions"):
                    _, final_assignments, asgn_rounds = await _handle_discussion(
                        session=session,
                        slots=slots,
                        context="assignment",
                        allowed_actions=disc_cfg["allowed_actions"],
                        timeout_seconds=disc_cfg.get("timeout_seconds", 60),
                        backlog_items=backlog_items or [],
                        selected_items=selected_items or [],
                        assignments=assignments,
                        phase_id=phase_id,
                        phase_name=phase_name,
                        phase_history=phase_history,
                        human_messages=human_messages,
                    )
                    assignments = final_assignments
                    assignment_rounds = asgn_rounds
                outcome = f"{len(assignments)} items assigned, {assignment_rounds or 0} rounds"

            elif action_type == "OPEN_DISCUSSION":
                if not is_v2:
                    log.warning("orchestrator.v2_action_in_v1 session_id=%s action=%s", session_id, action_type)
                    continue
                # OPEN_DISCUSSION is handled inline by GENERATE_RECOMMENDATION / GENERATE_ASSIGNMENT
                # If reached standalone (shouldn't happen), log and skip
                log.info("orchestrator.open_discussion.standalone_skip session_id=%s phase_id=%s", session_id, phase_id)

        phase_history.append({
            "phase_id": phase_id,
            "completed_at": datetime.now(tz=timezone.utc).isoformat(),
            "outcome": outcome,
        })

        updates: dict[str, Any] = {"phase_history": phase_history}
        if backlog_items is not None:
            updates["backlog_items"] = backlog_items
        if selected_items is not None:
            updates["selected_items"] = selected_items
        if assignments:
            updates["assignments"] = assignments
        # US-35 AC5: Persist convergence metrics
        if is_v2:
            if initial_recommendation is not None:
                updates["initial_recommendation"] = initial_recommendation
            if recommendation_rounds is not None:
                updates["recommendation_rounds"] = recommendation_rounds
            if assignment_rounds is not None:
                updates["assignment_rounds"] = assignment_rounds
            if retention_pct is not None:
                updates["retention_pct"] = retention_pct
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

    # ── US-35: Read convergence metrics from context for sprint backlog ──────
    conv_metrics: dict[str, Any] | None = None
    if is_v2:
        async with SessionLocal() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            crow = result.scalar_one_or_none()
            if crow:
                ctx = crow.context or {}
                conv = {}
                for key in ("initial_recommendation", "recommendation_rounds",
                            "assignment_rounds", "retention_pct"):
                    if key in ctx:
                        conv[key] = ctx[key]
                if conv:
                    conv_metrics = conv

    # ── US-08: Build and broadcast the final sprint backlog ───────────────────
    sprint_backlog = _build_sprint_backlog(
        session=session,
        slots=slots,
        backlog_items=backlog_items or [],
        selected_items=selected_items or [],
        assignments=assignments,
        convergence_metrics=conv_metrics,
    )
    await _broadcast_sprint_backlog(sprint_backlog, slots)

    # ── US-28: Generate and persist session summary ───────────────────────────
    from app.summary_service import generate_summary  # noqa: PLC0415
    asyncio.create_task(generate_summary(session_id))


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
    convergence_metrics: dict[str, Any] | None = None,
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

    result: dict[str, Any] = {
        "session_id": session.id,
        "sprint_goal": session.sprint_goal,
        "selected_items": selected_item_entries,
        "capacity_plan": capacity_plan,
    }
    # US-35 AC6: Include convergence metrics in sprint backlog output
    if convergence_metrics:
        result["convergence_metrics"] = convergence_metrics
    return result


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
    human_messages: list[dict] | None = None,
) -> list[dict]:
    po_slots = _reachable_slots(slots, roles={"PRODUCT_OWNER"})
    if not po_slots:
        raise RuntimeError("No reachable PRODUCT_OWNER slot for PRESENT_ITEMS")

    ctx = _build_ctx(
        session, slots, phase_id, phase_name, 1,
        None, None, assignments, phase_history, human_messages,
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
    human_messages: list[dict] | None = None,
) -> dict[str, int]:
    all_reachable = _reachable_slots(slots)
    item_ids = [item["item_id"] for item in backlog_items]

    ctx = _build_ctx(
        session, slots, phase_id, phase_name, 1,
        backlog_items, None, assignments, phase_history, human_messages,
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
    human_messages: list[dict] | None = None,
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
            session, slots, eligible, backlog_items, selected_items, item, assignments, phase_id, phase_name, phase_history, human_messages
        )
        if assignee_id:
            assignments[item_id] = assignee_id
            await _broadcast_acknowledge(
                session, slots, all_reachable,
                item_id, assignee_id, reason,
                backlog_items, selected_items, assignments, phase_id, phase_name, phase_history, human_messages,
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
    human_messages: list[dict] | None = None,
) -> tuple[str | None, str]:
    ctx = _build_ctx(
        session, slots, phase_id, phase_name, 1,
        backlog_items, selected_items, assignments, phase_history, human_messages,
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
    human_messages: list[dict] | None = None,
) -> None:
    assignee_name = next(
        (s.name for s in slots if s.participant_id == assignee_id), assignee_id
    )
    ctx = _build_ctx(
        session, slots, phase_id, phase_name, 1,
        backlog_items, selected_items, assignments, phase_history, human_messages,
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


# ── US-31: Expertise-Based Assignment Algorithm ────────────────────────────────


async def _handle_generate_assignment(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    backlog_items: list[dict],
    selected_items: list[str],
    phase_id: str,
    phase_name: str,
    phase_history: list[dict],
    human_messages: list[dict] | None = None,
) -> dict[str, str]:
    """Expertise-based assignment using Jaccard similarity + workload balance (US-31)."""
    from app.a2a.models import CommEvent
    from app.comm_bus import publish_comm_event
    from app.models import Participant

    # Build participant capacity map from Agent Cards (US-34 data)
    participant_capacity: dict[str, dict[str, object]] = {}
    async with SessionLocal() as db:
        for slot in slots:
            if slot.participant_id and slot.status == "joined":
                result = await db.execute(
                    select(Participant).where(Participant.id == slot.participant_id)
                )
                p = result.scalar_one_or_none()
                if p:
                    cap_raw = (p.capabilities or {}).get("capacity", {})
                    if not isinstance(cap_raw, dict):
                        cap_raw = {}
                    participant_capacity[slot.participant_id] = {
                        "story_points": int(cap_raw.get("story_points", 0)),
                        "specialties": list(cap_raw.get("specialties", [])),
                        "name": slot.name,
                    }

    if not participant_capacity:
        log.warning("orchestrator.assign.no_capacity_data session_id=%s", session.id)
        return {}

    # Track remaining capacity per participant (AC7)
    remaining: dict[str, int] = {
        pid: int(cap["story_points"])  # type: ignore[arg-type]
        for pid, cap in participant_capacity.items()
    }

    # Build item lookup
    item_lookup: dict[str, dict[str, object]] = {
        item["item_id"]: item for item in backlog_items
    }

    # Deterministic sort: higher priority first, then higher SP, then item_id (AC8)
    ordered_items = sorted(
        selected_items,
        key=lambda iid: (
            -_PRIORITY_SCORE.get(
                str(item_lookup.get(iid, {}).get("priority", "LOW")), 1
            ),
            -(int(item_lookup.get(iid, {}).get("story_points") or 0)),
            iid,
        ),
    )

    assignments: dict[str, str] = {}

    for item_id in ordered_items:
        item = item_lookup.get(item_id, {})
        item_sp = int(item.get("story_points") or 1)
        item_labels: set[str] = set(
            item.get("labels", []) if isinstance(item.get("labels"), list) else []
        )

        best_score = -1.0
        best_pid: str | None = None

        max_remaining = max(remaining.values()) if remaining else 1

        for pid, cap in participant_capacity.items():
            if remaining.get(pid, 0) < item_sp:
                continue  # insufficient remaining capacity (AC3)

            specialties: set[str] = set(
                cap.get("specialties", [])  # type: ignore[arg-type]
                if isinstance(cap.get("specialties"), list)
                else []
            )

            # Jaccard similarity (AC4)
            if not item_labels and not specialties:
                jaccard = 0.0
            elif not item_labels or not specialties:
                jaccard = 0.0
            else:
                intersection = len(item_labels & specialties)
                union = len(item_labels | specialties)
                jaccard = intersection / union if union > 0 else 0.0

            # Workload balance bonus: prefer more remaining capacity (AC4)
            workload_bonus = remaining[pid] / max_remaining if max_remaining > 0 else 0.0

            score = jaccard + workload_bonus

            if score > best_score:
                best_score = score
                best_pid = pid

        if best_pid is not None:
            assignments[item_id] = best_pid
            remaining[best_pid] -= item_sp

    # Broadcast assignment proposal via comm bus (AC6)
    await publish_comm_event(CommEvent(
        comm_id=str(uuid4()),
        session_id=session.id,
        timestamp=_now_iso(),
        sender_id="platform",
        sender_name="Platform",
        receiver_id=None,
        receiver_name=None,
        task_type="assignment_proposal",
        message_kind="broadcast",
        content={
            "assignments": assignments,
            "remaining_capacity": remaining,
        },
    ))

    log.info(
        "orchestrator.generate_assignment session_id=%s assigned=%d/%d",
        session.id, len(assignments), len(ordered_items),
    )
    return assignments


# ── US-32: Discussion Phase Handler ─────────────────────────────────────────────


def _apply_recommendation_action(
    event: "CommEvent",
    working_items: list[str],
    backlog_items: list[dict],
) -> bool:
    """Apply a recommendation-context action. Returns True if state changed."""
    content = event.content if isinstance(event.content, dict) else {}
    action = event.task_type

    if action == "add_item":
        item_data = content.get("item", content)
        item_id = item_data.get("item_id", "")
        if not item_id or item_id in working_items:
            return False
        # Add to working list if not already present
        if item_id not in {it["item_id"] for it in backlog_items}:
            # Validate and add to backlog
            try:
                validated = BacklogItem.model_validate(item_data)
                backlog_items.append(validated.model_dump())
            except ValidationError:
                return False
        working_items.append(item_id)
        log.info("discussion.add_item item_id=%s", item_id)
        return True

    elif action == "remove_item":
        item_id = content.get("item_id", "")
        if item_id in working_items:
            working_items.remove(item_id)
            log.info("discussion.remove_item item_id=%s", item_id)
            return True
        return False

    elif action == "modify_item":
        item_id = content.get("item_id", "")
        updates = content.get("updates", {})
        if not item_id or not updates:
            return False
        for item in backlog_items:
            if item["item_id"] == item_id:
                allowed = {"title", "description", "priority", "story_points", "labels", "dependencies"}
                for k, v in updates.items():
                    if k in allowed:
                        item[k] = v
                log.info("discussion.modify_item item_id=%s", item_id)
                return True
        return False

    return False


def _apply_assignment_action(
    event: "CommEvent",
    assignments: dict[str, str],
    working_items: list[str],
    slots: list[_SlotSnap],
) -> bool:
    """Apply an assignment-context action. Returns True if state changed."""
    content = event.content if isinstance(event.content, dict) else {}
    action = event.task_type
    sender_id = event.sender_id

    if action == "volunteer":
        item_id = content.get("item_id", "")
        if not item_id or item_id not in working_items:
            return False
        # Only assign if unassigned; don't override existing
        if item_id not in assignments:
            assignments[item_id] = sender_id
            log.info("discussion.volunteer item_id=%s participant_id=%s", item_id, sender_id)
            return True
        return False

    elif action == "object":
        item_id = content.get("item_id", "")
        reason = content.get("reason", "")
        if not item_id or item_id not in assignments:
            return False
        # Objection removes the assignment, putting it back for re-assignment
        removed = assignments.pop(item_id, None)
        if removed:
            log.info("discussion.object item_id=%s by=%s reason=%s", item_id, sender_id, reason)
            return True
        return False

    elif action == "reassign":
        item_id = content.get("item_id", "")
        to_participant_id = content.get("to_participant_id", "")
        from_participant_id = content.get("from_participant_id", "")
        if not item_id or not to_participant_id:
            return False
        if item_id not in working_items:
            return False
        # Validate to_participant is a valid slot
        valid_pids = {s.participant_id for s in slots if s.participant_id}
        if to_participant_id not in valid_pids:
            return False
        assignments[item_id] = to_participant_id
        log.info(
            "discussion.reassign item_id=%s from=%s to=%s",
            item_id, from_participant_id, to_participant_id,
        )
        return True

    return False


async def _broadcast_discussion_state(
    session: _SessionSnap,
    context: str,
    working_items: list[str],
    assignments: dict[str, str],
    backlog_items: list[dict],
    round_count: int,
) -> None:
    """Broadcast current discussion state via comm bus (US-32 AC2, AC7)."""
    from app.a2a.models import CommEvent
    from app.comm_bus import publish_comm_event

    if context == "recommendation":
        item_details = [
            next((it for it in backlog_items if it["item_id"] == iid), {"item_id": iid})
            for iid in working_items
        ]
        payload: dict[str, Any] = {
            "context": "recommendation",
            "items": item_details,
            "round": round_count,
        }
    else:
        payload = {
            "context": "assignment",
            "assignments": assignments,
            "round": round_count,
        }

    await publish_comm_event(CommEvent(
        comm_id=str(uuid4()),
        session_id=session.id,
        timestamp=_now_iso(),
        sender_id="platform",
        sender_name="Platform",
        receiver_id=None,
        receiver_name=None,
        task_type="discussion_update",
        message_kind="broadcast",
        content=payload,
    ))


async def _handle_discussion(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    context: str,
    allowed_actions: list[str],
    timeout_seconds: int,
    backlog_items: list[dict],
    selected_items: list[str],
    assignments: dict[str, str],
    phase_id: str,
    phase_name: str,
    phase_history: list[dict],
    human_messages: list[dict] | None = None,
) -> tuple[list[str], dict[str, str], int]:
    """Shared discussion handler for recommendation and assignment phases (US-32).

    Returns (final_selected_items, final_assignments, round_count).
    """
    from app.a2a.models import CommEvent
    from app.message_bus import bus

    # Working copies
    working_items: list[str] = list(selected_items)
    working_assignments: dict[str, str] = dict(assignments)
    round_count = 0

    # Identify PO participants for advance signaling
    po_pids: set[str] = {
        s.participant_id for s in slots
        if s.role == "PRODUCT_OWNER" and s.participant_id
    }

    # Broadcast initial state (AC2)
    await _broadcast_discussion_state(
        session, context, working_items, working_assignments,
        backlog_items, round_count,
    )

    # Subscribe to session comm channel (AC3)
    channel = f"session:comm:{session.id}"
    pubsub = bus().pubsub()
    await pubsub.subscribe(channel)

    last_activity = asyncio.get_event_loop().time()
    loop = asyncio.get_event_loop()

    try:
        while True:
            # Check timeout with no activity (AC8a)
            elapsed = loop.time() - last_activity
            if elapsed >= timeout_seconds:
                log.info(
                    "discussion.timeout session_id=%s context=%s elapsed=%.1f",
                    session.id, context, elapsed,
                )
                break

            # Poll for messages with short timeout
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if msg is None:
                continue

            # Parse CommEvent (AC4)
            try:
                event = CommEvent.model_validate_json(msg["data"])
            except Exception:
                continue

            # Check for PO advance signal (AC8c)
            if (
                event.sender_id in po_pids
                and event.task_type in ("advance", "confirm_phase")
            ):
                log.info(
                    "discussion.po_advance session_id=%s sender_id=%s",
                    session.id, event.sender_id,
                )
                break

            # Validate action against allowed set (AC4)
            if event.task_type not in allowed_actions:
                continue

            # Apply the action (AC5, AC6)
            changed = False
            if context == "recommendation":
                changed = _apply_recommendation_action(
                    event, working_items, backlog_items,
                )
            elif context == "assignment":
                changed = _apply_assignment_action(
                    event, working_assignments, working_items, slots,
                )

            if changed:
                round_count += 1
                last_activity = loop.time()
                # Broadcast updated state (AC7)
                await _broadcast_discussion_state(
                    session, context, working_items, working_assignments,
                    backlog_items, round_count,
                )

    finally:
        await pubsub.unsubscribe(channel)
        # redis-py 5.x may require explicit close; guard against missing method
        close_fn = getattr(pubsub, "aclose", getattr(pubsub, "close", None))
        if close_fn is not None:
            if callable(close_fn):
                try:
                    await close_fn()  # type: ignore[misc]
                except Exception:
                    pass

    log.info(
        "discussion.complete session_id=%s context=%s rounds=%d",
        session.id, context, round_count,
    )
    return working_items, working_assignments, round_count


# ── US-33: Recommend Handler ───────────────────────────────────────────────────


async def _handle_recommend(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    backlog_items: list[dict],
    phase_id: str,
    phase_name: str,
    phase_history: list[dict],
    human_messages: list[dict] | None = None,
    discussion_config: dict[str, Any] | None = None,
) -> tuple[list[str], int]:
    """Generate recommendations via recommender, then enter discussion (US-33 AC1).

    Returns (final_selected_items, round_count).
    """
    from app.recommender import recommend

    # If backlog_items is empty, fetch from PO first
    if not backlog_items:
        backlog_items_fetched = await _handle_present_items(
            session, slots, phase_id, phase_name, {}, phase_history, human_messages,
        )
        backlog_items.extend(backlog_items_fetched)

    # Determine total capacity
    total_cap = session.sprint_capacity or sum(
        int((it.get("story_points") or 1)) for it in backlog_items
    )

    # Run recommender
    recommended = recommend(
        backlog_items=backlog_items,
        sprint_goal=session.sprint_goal,
        total_capacity=total_cap,
    )
    rec_item_ids = [it["item_id"] for it in recommended]

    log.info(
        "orchestrator.recommend session_id=%s recommended=%d/%d",
        session.id, len(rec_item_ids), len(backlog_items),
    )

    # Enter discussion if configured
    disc_cfg = discussion_config or {}
    if disc_cfg.get("allowed_actions"):
        final_items, _, rounds = await _handle_discussion(
            session=session,
            slots=slots,
            context="recommendation",
            allowed_actions=disc_cfg["allowed_actions"],
            timeout_seconds=disc_cfg.get("timeout_seconds", 60),
            backlog_items=backlog_items,
            selected_items=rec_item_ids,
            assignments={},
            phase_id=phase_id,
            phase_name=phase_name,
            phase_history=phase_history,
            human_messages=human_messages,
        )
        return final_items, rounds

    return rec_item_ids, 0


async def _handle_confirm(
    session: _SessionSnap,
    slots: list[_SlotSnap],
    backlog_items: list[dict],
    selected_items: list[str],
    assignments: dict[str, str],
    phase_id: str,
    phase_name: str,
    phase_history: list[dict],
    human_messages: list[dict] | None = None,
    *,
    is_v2: bool = False,
) -> float:
    """Confirm phase: v1 uses quorum, v2 polls only PRODUCT_OWNER (US-33 AC5)."""
    if is_v2:
        # v2: poll only PRODUCT_OWNER, no quorum needed
        po_slots = _reachable_slots(slots, roles={"PRODUCT_OWNER"})
        if not po_slots:
            log.warning("orchestrator.confirm_v2.no_po session_id=%s", session.id)
            return 1.0

        ctx = _build_ctx(
            session, slots, phase_id, phase_name, 1,
            backlog_items, selected_items, assignments, phase_history, human_messages,
        )
        po = po_slots[0]
        r = await _send_task_with_comm(
            session.id, po, "confirm", ctx,
            {
                "sprint_goal": session.sprint_goal,
                "selected_items": selected_items,
                "assignments": assignments,
            },
        )
        if not r.ok:
            log.warning("orchestrator.confirm_v2.po_failed slot=%s", po.id)
            return 0.0

        artifact = r.artifact or {}
        confirmed = bool(artifact.get("confirmed", artifact.get("ack", False)))
        quorum = 1.0 if confirmed else 0.0
        log.info(
            "orchestrator.confirm_v2 session_id=%s po_confirmed=%s",
            session.id, confirmed,
        )
        return quorum

    # v1: existing quorum-based confirmation
    reachable = _reachable_slots(slots)
    total = len(reachable)
    if total == 0:
        return 1.0

    ctx = _build_ctx(
        session, slots, phase_id, phase_name, 1,
        backlog_items, selected_items, assignments, phase_history, human_messages,
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
