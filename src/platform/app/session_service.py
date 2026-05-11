"""Session lifecycle service (US-03).

Responsibilities:
  - Build and persist the session + declared-participant rows.
  - Fire session_invite A2A tasks to all agent slots (background).
  - Schedule the join-timeout check for each PENDING session.
  - Evaluate required_roles when the timeout fires.
  - Transition PENDING → ACTIVE / ABORTED and broadcast accordingly.
  - Restore pending timeout tasks on platform startup (AC8).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.a2a.client import A2AClient
from app.config import settings
from app.db import SessionLocal
from app.models import Participant, Session, SessionParticipant

log = logging.getLogger(__name__)

# ── Hard-coded Phase-1 template definition ────────────────────────────────────
# First-phase required_roles per template_id.  When the join timeout fires we
# compare absentee roles against this set to decide ACTIVE-with-note vs ABORT.
_FIRST_PHASE_REQUIRED_ROLES: dict[str, set[str]] = {
    "sprint_planning_v1": {"PRODUCT_OWNER"},
}

# ── In-process timeout task registry ─────────────────────────────────────────
# Maps session_id → asyncio.Task.  Used only by the current process; restored
# from Postgres on startup (see restore_pending_timeouts).
_timeout_tasks: dict[str, asyncio.Task] = {}

_a2a_client = A2AClient(default_timeout_seconds=15.0)

# ── Session creation ──────────────────────────────────────────────────────────


async def build_session_ctx(session: Session, slots: list[SessionParticipant]) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "sprint_goal": session.sprint_goal,
        "template_id": session.template,
        "participants": [
            {
                "participant_id": s.participant_id,
                "name": s.name,
                "role": s.role,
                "type": "AI_AGENT" if s.slot_type == "AGENT" else "HUMAN",
                "status": s.status,
            }
            for s in slots
        ],
    }


async def send_invites_background(session_id: str, slots: list[SessionParticipant]) -> None:
    """Fire session_invite to every agent slot; ignore failures (timeout handles absentees).

    Accepts a snapshot of slot data — the objects may be detached from their
    original DB session by the time this coroutine runs, so we re-fetch the
    session from a fresh connection and work from the in-memory slot list.
    """
    # Capture primitive data from the ORM objects before they might be detached.
    agent_slots_data = [
        {"id": s.id, "endpoint": s.endpoint, "participant_id": s.participant_id,
         "name": s.name, "role": s.role, "slot_type": s.slot_type, "status": s.status}
        for s in slots
        if s.slot_type == "AGENT" and s.endpoint
    ]
    if not agent_slots_data:
        return

    async with SessionLocal() as db:
        result = await db.execute(select(Session).where(Session.id == session_id))
        session = result.scalar_one_or_none()
        if session is None:
            return

    session_ctx: dict[str, Any] = {
        "session_id": session.id,
        "sprint_goal": session.sprint_goal,
        "template_id": session.template,
        "participants": [
            {"participant_id": s.participant_id, "name": s.name,
             "role": s.role, "type": "AI_AGENT" if s.slot_type == "AGENT" else "HUMAN",
             "status": s.status}
            for s in slots
        ],
    }
    join_url = session.join_url

    async def invite(slot_data: dict) -> None:
        try:
            result = await _a2a_client.send_task(
                endpoint=slot_data["endpoint"],
                task_type="session_invite",
                session_ctx=session_ctx,
                payload={"join_url": join_url},
            )
            if not result.ok:
                log.warning(
                    "session_invite failed session_id=%s endpoint=%s error=%s",
                    session_id, slot_data["endpoint"], result.error,
                )
        except Exception as exc:
            log.warning(
                "session_invite error session_id=%s endpoint=%s exc=%s",
                session_id, slot_data["endpoint"], exc,
            )

    await asyncio.gather(*[invite(s) for s in agent_slots_data], return_exceptions=True)


# ── Timeout evaluation ────────────────────────────────────────────────────────


async def _evaluate_timeout(session_id: str) -> None:
    async with SessionLocal() as db:
        result = await db.execute(select(Session).where(Session.id == session_id))
        session = result.scalar_one_or_none()
        if session is None or session.status != "PENDING":
            return

        slots_result = await db.execute(
            select(SessionParticipant).where(SessionParticipant.session_id == session_id)
        )
        slots = list(slots_result.scalars())

        absent_roles = {s.role for s in slots if s.status == "declared"}
        required = _FIRST_PHASE_REQUIRED_ROLES.get(session.template, set())
        missing_required = absent_roles & required

        absent_names = [s.name for s in slots if s.status == "declared"]

        if missing_required:
            await _transition(session, "ABORTED", db)
            await db.commit()
            log.info(
                "session.aborted session_id=%s missing_required=%s",
                session_id, missing_required,
            )
            await _broadcast_aborted(session, slots, missing_required)
        else:
            note = f"Absent (non-required): {', '.join(absent_names)}" if absent_names else None
            ctx = session.context or {}
            if note:
                ctx["absent_note"] = note
            session.context = ctx
            await _transition(session, "ACTIVE", db)
            await db.commit()
            log.info(
                "session.active_with_note session_id=%s note=%s",
                session_id, note,
            )
            slots_result2 = await db.execute(
                select(SessionParticipant).where(SessionParticipant.session_id == session_id)
            )
            await _broadcast_ready(session, list(slots_result2.scalars()), note)


async def _run_timeout(session_id: str, timeout_at: datetime) -> None:
    now = datetime.now(tz=timezone.utc)
    delay = (timeout_at - now).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    log.info("session.timeout_fired session_id=%s", session_id)
    try:
        await _evaluate_timeout(session_id)
    except Exception as exc:
        log.exception("session.timeout_error session_id=%s exc=%s", session_id, exc)
    finally:
        _timeout_tasks.pop(session_id, None)


def schedule_timeout(session_id: str, timeout_at: datetime) -> None:
    if session_id in _timeout_tasks:
        return
    task = asyncio.create_task(_run_timeout(session_id, timeout_at))
    _timeout_tasks[session_id] = task


# ── All-joined fast path ──────────────────────────────────────────────────────


async def maybe_activate(session_id: str, db: AsyncSession) -> bool:
    """Transition to ACTIVE immediately if all declared slots have joined."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None or session.status != "PENDING":
        return False

    slots_result = await db.execute(
        select(SessionParticipant).where(SessionParticipant.session_id == session_id)
    )
    slots = list(slots_result.scalars())
    all_joined = all(s.status == "joined" for s in slots)
    if not all_joined:
        return False

    _timeout_tasks.pop(session_id, None)
    await _transition(session, "ACTIVE", db)
    await db.commit()
    log.info("session.active_all_joined session_id=%s", session_id)
    await _broadcast_ready(session, slots, note=None)
    return True


# ── State-machine guard (AC7) ─────────────────────────────────────────────────

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"ACTIVE", "ABORTED"},
    "ACTIVE": {"COMPLETED"},
    "COMPLETED": set(),
    "ABORTED": set(),
}


async def _transition(session: Session, target: str, db: AsyncSession) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(session.status, set())
    if target not in allowed:
        raise ValueError(
            f"Illegal transition {session.status!r} → {target!r}"
        )
    session.status = target


# ── A2A broadcasts ────────────────────────────────────────────────────────────


async def _broadcast_ready(session: Session, slots: list[SessionParticipant], note: str | None) -> None:
    session_ctx = await _build_ctx_inline(session, slots)
    payload: dict[str, Any] = {}
    if note:
        payload["note"] = note

    agent_slots = [s for s in slots if s.slot_type == "AGENT" and s.endpoint and s.status == "joined"]

    async def notify(slot: SessionParticipant) -> None:
        try:
            await _a2a_client.send_task(
                endpoint=slot.endpoint,
                task_type="session_ready",
                session_ctx=session_ctx,
                payload=payload,
            )
        except Exception as exc:
            log.warning("session_ready failed slot=%s exc=%s", slot.id, exc)

    await asyncio.gather(*[notify(s) for s in agent_slots], return_exceptions=True)


async def _broadcast_aborted(
    session: Session, slots: list[SessionParticipant], missing_required: set[str]
) -> None:
    session_ctx = await _build_ctx_inline(session, slots)
    payload = {"reason": f"Required role(s) did not join: {', '.join(sorted(missing_required))}"}

    agent_slots = [s for s in slots if s.slot_type == "AGENT" and s.endpoint and s.status == "joined"]

    async def notify(slot: SessionParticipant) -> None:
        try:
            await _a2a_client.send_task(
                endpoint=slot.endpoint,
                task_type="session_aborted",
                session_ctx=session_ctx,
                payload=payload,
            )
        except Exception as exc:
            log.warning("session_aborted notify failed slot=%s exc=%s", slot.id, exc)

    await asyncio.gather(*[notify(s) for s in agent_slots], return_exceptions=True)


async def _build_ctx_inline(session: Session, slots: list[SessionParticipant]) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "sprint_goal": session.sprint_goal,
        "template_id": session.template,
        "participants": [
            {
                "participant_id": s.participant_id,
                "name": s.name,
                "role": s.role,
                "type": "AI_AGENT" if s.slot_type == "AGENT" else "HUMAN",
                "status": s.status,
            }
            for s in slots
        ],
    }


# ── Startup restoration (AC8) ─────────────────────────────────────────────────


async def restore_pending_timeouts() -> None:
    """Re-schedule timeout tasks for any PENDING sessions that survived a restart."""
    async with SessionLocal() as db:
        result = await db.execute(select(Session).where(Session.status == "PENDING"))
        pending = list(result.scalars())

    for session in pending:
        timeout_at = session.timeout_at
        if timeout_at.tzinfo is None:
            timeout_at = timeout_at.replace(tzinfo=timezone.utc)
        log.info(
            "session.restore_timeout session_id=%s timeout_at=%s",
            session.id, timeout_at.isoformat(),
        )
        schedule_timeout(session.id, timeout_at)
