"""Session Summary Service (US-28).

Generates and persists a SessionSummary when a session transitions to COMPLETED.
Called by the phase orchestrator; retried up to 3 times on failure (AC4).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Session, SessionParticipant, SessionSummary, Template

log = logging.getLogger(__name__)

_MAX_RETRIES = 3
_KEY_DECISIONS_LIMIT = 10


async def generate_summary(session_id: str) -> None:
    """Entry point: attempt summary generation with exponential-backoff retries."""
    for attempt in range(_MAX_RETRIES):
        try:
            await _generate(session_id)
            log.info("summary.generated session_id=%s", session_id)
            return
        except Exception as exc:
            if attempt < _MAX_RETRIES - 1:
                delay = 2 ** attempt
                log.warning(
                    "summary.retry session_id=%s attempt=%d exc=%s sleeping=%ds",
                    session_id, attempt + 1, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                log.error(
                    "summary.failed session_id=%s exc=%s — storing partial",
                    session_id, exc,
                )
                await _store_partial(session_id)


async def _generate(session_id: str) -> None:
    async with SessionLocal() as db:
        session_result = await db.execute(select(Session).where(Session.id == session_id))
        session = session_result.scalar_one()

        slots_result = await db.execute(
            select(SessionParticipant).where(SessionParticipant.session_id == session_id)
        )
        slots = list(slots_result.scalars())

        template_result = await db.execute(select(Template).where(Template.id == session.template))
        template_row = template_result.scalar_one_or_none()

        ctx = session.context or {}
        # Use naive UTC datetimes (consistent with other DateTime columns in the schema)
        now = datetime.utcnow()
        started_at = session.created_at.replace(tzinfo=None) if session.created_at.tzinfo else session.created_at

        # ── Messages ────────────────────────────────────────────────────────────
        # Combine peer-to-peer chat and human messages, sort chronologically.
        raw_messages: list[dict] = ctx.get("messages", []) + ctx.get("human_messages", [])
        raw_messages.sort(key=lambda m: m.get("timestamp", ""))
        messages_out = [
            {
                "sender_id": m.get("sender_id", ""),
                "sender_name": m.get("sender_name", ""),
                "content": m.get("content", ""),
                "timestamp": m.get("timestamp"),
                "kind": "human" if m.get("sender_id") in {
                    s.participant_id for s in slots if s.slot_type == "HUMAN"
                } else "agent",
            }
            for m in raw_messages
        ]

        # ── Participants ────────────────────────────────────────────────────────
        messages: list[dict] = raw_messages
        msg_count_by_sender: dict[str, int] = {}
        for m in messages:
            sid = m.get("sender_id", "")
            msg_count_by_sender[sid] = msg_count_by_sender.get(sid, 0) + 1

        participants_out = [
            {
                "participant_id": s.participant_id,
                "name": s.name,
                "role": s.role,
                "type": "HUMAN" if s.slot_type == "HUMAN" else "AGENT",
                "message_count": msg_count_by_sender.get(s.participant_id or "", 0),
            }
            for s in slots
        ]

        # ── Backlog output ──────────────────────────────────────────────────────
        backlog_items: list[dict] = ctx.get("backlog_items") or []
        selected_ids: list[str] = ctx.get("selected_items") or []
        assignments: dict[str, str] = ctx.get("assignments") or {}
        name_lookup: dict[str, str] = {s.participant_id: s.name for s in slots if s.participant_id}
        item_lookup: dict[str, dict] = {item["item_id"]: item for item in backlog_items}

        backlog_output = [
            {
                "item_id": iid,
                "title": item_lookup.get(iid, {}).get("title", ""),
                "story_points": item_lookup.get(iid, {}).get("story_points"),
                "priority": item_lookup.get(iid, {}).get("priority", "LOW"),
                "assigned_to": name_lookup.get(assignments.get(iid, ""), assignments.get(iid)),
            }
            for iid in selected_ids
            if (item := item_lookup.get(iid)) is not None  # noqa: F841
        ]

        # ── Phase breakdown ─────────────────────────────────────────────────────
        phase_history: list[dict] = ctx.get("phase_history") or []
        template_phases: list[dict] = template_row.phases if template_row else []
        phase_name_lookup: dict[str, str] = {p["phase_id"]: p.get("name", p["phase_id"]) for p in template_phases}

        phase_breakdown = []
        prev_ts = started_at
        for entry in phase_history:
            completed_str = entry.get("completed_at", "")
            try:
                completed_dt = datetime.fromisoformat(completed_str)
                # Normalize to naive UTC
                if completed_dt.tzinfo is not None:
                    completed_dt = completed_dt.replace(tzinfo=None)
            except ValueError:
                completed_dt = now

            duration_s = max(0, int((completed_dt - prev_ts).total_seconds()))
            phase_breakdown.append({
                "phase_name": phase_name_lookup.get(entry["phase_id"], entry["phase_id"]),
                "duration_seconds": duration_s,
                "outcome": entry.get("outcome", "COMPLETED"),
            })
            prev_ts = completed_dt

        duration_seconds = max(0, int((now - started_at).total_seconds()))

        # ── Key decisions ───────────────────────────────────────────────────────
        key_decisions: list[dict] = []

        if backlog_items:
            key_decisions.append({
                "type": "backlog_presented",
                "description": f"{len(backlog_items)} backlog items presented",
                "timestamp": phase_history[0].get("completed_at") if phase_history else None,
            })

        if selected_ids:
            key_decisions.append({
                "type": "items_selected",
                "description": f"{len(selected_ids)} of {len(backlog_items)} items selected for sprint",
                "timestamp": next(
                    (e.get("completed_at") for e in phase_history if "select" in e.get("phase_id", "").lower()),
                    phase_history[1].get("completed_at") if len(phase_history) > 1 else None,
                ),
            })

        for item_id, assignee_id in list(assignments.items())[:_KEY_DECISIONS_LIMIT - len(key_decisions) - 1]:
            item_title = item_lookup.get(item_id, {}).get("title", item_id)
            assignee_name = name_lookup.get(assignee_id, assignee_id)
            key_decisions.append({
                "type": "assignment",
                "description": f'"{item_title}" assigned to {assignee_name}',
                "timestamp": None,
            })

        for ph in phase_history:
            if len(key_decisions) >= _KEY_DECISIONS_LIMIT:
                break
            outcome = ph.get("outcome", "")
            if "quorum" in outcome or "timed_out" in outcome.lower():
                key_decisions.append({
                    "type": "phase_outcome",
                    "description": f'{phase_name_lookup.get(ph["phase_id"], ph["phase_id"])}: {outcome}',
                    "timestamp": ph.get("completed_at"),
                })

        # ── Metrics snapshot ────────────────────────────────────────────────────
        total_sp = sum(item_lookup.get(iid, {}).get("story_points") or 0 for iid in selected_ids)
        assigned_count = sum(1 for iid in selected_ids if iid in assignments)
        human_count = sum(1 for s in slots if s.slot_type == "HUMAN")
        agent_count = sum(1 for s in slots if s.slot_type == "AGENT")

        metrics_snapshot = {
            "total_items": len(backlog_items),
            "selected_items": len(selected_ids),
            "assigned_items": assigned_count,
            "total_story_points": total_sp,
            "human_participants": human_count,
            "agent_participants": agent_count,
            "phase_count": len(phase_history),
            "total_messages": len(messages),
        }

        # ── Check for existing (idempotent) ────────────────────────────────────
        existing = await db.execute(
            select(SessionSummary).where(SessionSummary.session_id == session_id)
        )
        if existing.scalar_one_or_none() is not None:
            log.info("summary.already_exists session_id=%s", session_id)
            return

        summary = SessionSummary(
            id=str(uuid4()),
            session_id=session_id,
            sprint_goal=session.sprint_goal,
            template_used=session.template,
            started_at=started_at,
            ended_at=now,
            duration_seconds=duration_seconds,
            participants=participants_out,
            backlog_output=backlog_output,
            phase_breakdown=phase_breakdown,
            key_decisions=key_decisions,
            metrics_snapshot=metrics_snapshot,
            messages=messages_out,
            generation_status="OK",
        )
        db.add(summary)
        await db.commit()


async def _store_partial(session_id: str) -> None:
    """Store a minimal partial summary so the endpoint returns something."""
    try:
        async with SessionLocal() as db:
            existing = await db.execute(
                select(SessionSummary).where(SessionSummary.session_id == session_id)
            )
            if existing.scalar_one_or_none() is not None:
                return

            session_result = await db.execute(select(Session).where(Session.id == session_id))
            session = session_result.scalar_one_or_none()
            if session is None:
                return

            now = datetime.utcnow()
            started_at = session.created_at.replace(tzinfo=None) if session.created_at.tzinfo else session.created_at

            summary = SessionSummary(
                id=str(uuid4()),
                session_id=session_id,
                sprint_goal=session.sprint_goal,
                template_used=session.template,
                started_at=started_at,
                ended_at=now,
                duration_seconds=max(0, int((now - started_at).total_seconds())),
                participants=[],
                backlog_output=[],
                phase_breakdown=[],
                key_decisions=[],
                metrics_snapshot={},
                generation_status="PARTIAL",
            )
            db.add(summary)
            await db.commit()
    except Exception as exc:
        log.error("summary.partial_store_failed session_id=%s exc=%s", session_id, exc)
