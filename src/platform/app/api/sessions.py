"""Session Manager API (US-03).

POST /sessions      — create session with declared participants (AC1, AC2, AC3)
POST /sessions/{id}/join — agent or human joins (AC4, AC5)
GET  /sessions/{id} — inspect session state
GET  /sessions      — list all sessions
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import Participant, Session, SessionParticipant, Template
from app.session_service import (
    maybe_activate,
    schedule_timeout,
    send_invites_background,
)

log = logging.getLogger(__name__)

router = APIRouter()

# ── Request / response models ─────────────────────────────────────────────────

VALID_ROLES = {"PRODUCT_OWNER", "DEVELOPER", "ARCHITECT", "SCRUM_MASTER"}


class AgentByUrl(BaseModel):
    agent_url: HttpUrl
    role: str | None = None  # override if not already in the card (best-effort)


class AgentById(BaseModel):
    participant_id: str


class HumanSlot(BaseModel):
    type: Literal["HUMAN"]
    name: str
    role: str


ParticipantDeclaration = Annotated[
    AgentByUrl | AgentById | HumanSlot,
    Field(discriminator=None),
]


class CreateSessionRequest(BaseModel):
    template: str = "sprint_planning_v1"
    sprint_goal: str = ""
    participants: list[AgentByUrl | AgentById | HumanSlot] = Field(default_factory=list)


class SessionOut(BaseModel):
    session_id: str
    join_url: str
    timeout_at: datetime
    status: str
    template: str
    sprint_goal: str

    model_config = {"from_attributes": True}


class SessionDetailOut(SessionOut):
    participants: list[dict[str, Any]] = Field(default_factory=list)


class JoinByParticipantId(BaseModel):
    participant_id: str


class JoinByHuman(BaseModel):
    name: str
    role: str
    endpoint: str | None = None  # A2A proxy URL (AC1 of US-07)



class JoinResponse(BaseModel):
    participant_id: str
    status: str
    waiting_for: list[str]


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _resolve_agent_by_url(agent_url: str, db: AsyncSession) -> Participant:
    """Find a registered participant whose endpoint matches the given agent_url base."""
    # Normalise: strip trailing slash from the base URL and look for a registered
    # participant whose endpoint starts with it (e.g. base=http://po:8001,
    # endpoint=http://po:8001/a2a).
    base = str(agent_url).rstrip("/")
    result = await db.execute(
        select(Participant).where(Participant.endpoint.startswith(base))
    )
    participant = result.scalar_one_or_none()
    if participant is None:
        raise HTTPException(
            404,
            detail={
                "reason": "agent_not_registered",
                "agent_url": base,
                "hint": "POST /register first",
            },
        )
    return participant


async def _resolve_agent_by_id(participant_id: str, db: AsyncSession) -> Participant:
    result = await db.execute(
        select(Participant).where(Participant.id == participant_id)
    )
    participant = result.scalar_one_or_none()
    if participant is None:
        raise HTTPException(
            404,
            detail={"reason": "participant_not_found", "participant_id": participant_id},
        )
    return participant


# ── POST /sessions ────────────────────────────────────────────────────────────


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    req: CreateSessionRequest,
    db: AsyncSession = Depends(get_session),
) -> SessionOut:
    # Validate template exists
    template_result = await db.execute(select(Template).where(Template.id == req.template))
    template_row = template_result.scalar_one_or_none()
    if not template_row:
        raise HTTPException(
            status_code=400,
            detail={"reason": "invalid_template", "template": req.template}
        )

    timeout_at = datetime.utcnow() + timedelta(minutes=settings.join_timeout_minutes)

    session = Session(
        template=req.template,
        sprint_goal=req.sprint_goal,
        status="PENDING",
        timeout_at=timeout_at,
        context={},
        join_url="",  # filled below after we have the session id
    )
    db.add(session)
    await db.flush()  # get the id without committing

    session.join_url = f"{settings.ui_base_url.rstrip('/')}/join/{session.id}"

    # Build SessionParticipant slots for each declared participant.
    slots: list[SessionParticipant] = []
    for decl in req.participants:
        if isinstance(decl, HumanSlot):
            if decl.role not in VALID_ROLES:
                raise HTTPException(
                    422,
                    detail={"reason": "invalid_role", "role": decl.role, "valid_roles": sorted(VALID_ROLES)},
                )
            slot = SessionParticipant(
                session_id=session.id,
                participant_id=None,
                name=decl.name,
                role=decl.role,
                slot_type="HUMAN",
                endpoint=None,
                status="declared",
            )
        elif isinstance(decl, AgentById):
            p = await _resolve_agent_by_id(decl.participant_id, db)
            slot = SessionParticipant(
                session_id=session.id,
                participant_id=p.id,
                name=p.name,
                role=p.role,
                slot_type="AGENT",
                endpoint=p.endpoint,
                status="declared",
            )
        else:  # AgentByUrl
            p = await _resolve_agent_by_url(str(decl.agent_url), db)
            slot = SessionParticipant(
                session_id=session.id,
                participant_id=p.id,
                name=p.name,
                role=p.role,
                slot_type="AGENT",
                endpoint=p.endpoint,
                status="declared",
            )
        db.add(slot)
        slots.append(slot)

    await db.commit()
    await db.refresh(session)

    # Schedule the join-timeout check (AC6).
    schedule_timeout(session.id, timeout_at)

    # Fire session_invite to all agent slots in the background (AC3).
    # We capture a snapshot of the slot data so the background coroutine doesn't
    # need a live DB session.
    asyncio.create_task(send_invites_background(session.id, slots))

    return SessionOut(
        session_id=session.id,
        join_url=session.join_url,
        timeout_at=session.timeout_at,
        status=session.status,
        template=session.template,
        sprint_goal=session.sprint_goal,
    )


# ── POST /sessions/{session_id}/join ─────────────────────────────────────────


@router.post("/{session_id}/join", response_model=JoinResponse)
async def join_session(
    session_id: str,
    body: JoinByParticipantId | JoinByHuman,
    db: AsyncSession = Depends(get_session),
) -> JoinResponse:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(404, detail={"reason": "session_not_found", "session_id": session_id})

    if session.status != "PENDING":
        raise HTTPException(
            409,
            detail={
                "reason": "session_not_pending",
                "status": session.status,
                "hint": "Late join is not supported in Phase 1.",
            },
        )

    slots_result = await db.execute(
        select(SessionParticipant).where(SessionParticipant.session_id == session_id)
    )
    slots = list(slots_result.scalars())

    if isinstance(body, JoinByParticipantId):
        # Agent join — find the matching declared slot.
        slot = next(
            (s for s in slots if s.participant_id == body.participant_id and s.slot_type == "AGENT"),
            None,
        )
        if slot is None:
            raise HTTPException(
                404,
                detail={
                    "reason": "participant_not_declared",
                    "participant_id": body.participant_id,
                    "hint": "Only participants declared at session creation may join.",
                },
            )
        if slot.status == "joined":
            pass  # idempotent — already joined, just return current state
        else:
            slot.status = "joined"
            await db.flush()
        assigned_id = slot.participant_id
    else:
        # Human join — find a matching declared HUMAN slot by role.
        if body.role not in VALID_ROLES:
            raise HTTPException(
                422,
                detail={"reason": "invalid_role", "role": body.role, "valid_roles": sorted(VALID_ROLES)},
            )
        slot = next(
            (
                s
                for s in slots
                if s.slot_type == "HUMAN"
                and s.role == body.role
                and s.name == body.name
                and s.status == "declared"
            ),
            None,
        )
        if slot is None:
            raise HTTPException(
                404,
                detail={
                    "reason": "participant_not_declared",
                    "name": body.name,
                    "role": body.role,
                    "hint": "Only participants declared at session creation may join.",
                },
            )
        new_pid = str(uuid4())
        slot.participant_id = new_pid
        slot.status = "joined"
        # Store the proxy endpoint so the orchestrator can dispatch A2A tasks (US-07 AC1)
        if body.endpoint:
            slot.endpoint = body.endpoint
        await db.flush()
        assigned_id = new_pid


    # Refresh slot list after update.
    slots_result2 = await db.execute(
        select(SessionParticipant).where(SessionParticipant.session_id == session_id)
    )
    slots = list(slots_result2.scalars())

    waiting_for = [s.name for s in slots if s.status == "declared"]

    # Check if all declared participants have now joined (AC5).
    activated = await maybe_activate(session_id, db)
    if not activated:
        await db.commit()

    return JoinResponse(
        participant_id=assigned_id,
        status="ACTIVE" if activated else "PENDING",
        waiting_for=waiting_for if not activated else [],
    )


# ── GET /sessions/{session_id} ────────────────────────────────────────────────


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_session),
) -> SessionDetailOut:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(404, detail={"reason": "session_not_found", "session_id": session_id})

    slots_result = await db.execute(
        select(SessionParticipant).where(SessionParticipant.session_id == session_id)
    )
    slots = list(slots_result.scalars())

    return SessionDetailOut(
        session_id=session.id,
        join_url=session.join_url,
        timeout_at=session.timeout_at,
        status=session.status,
        template=session.template,
        sprint_goal=session.sprint_goal,
        participants=[
            {
                "participant_id": s.participant_id,
                "name": s.name,
                "role": s.role,
                "type": s.slot_type,
                "status": s.status,
            }
            for s in slots
        ],
    )


# ── GET /sessions ─────────────────────────────────────────────────────────────


@router.get("", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_session)) -> list[SessionOut]:
    result = await db.execute(select(Session))
    return [
        SessionOut(
            session_id=s.id,
            join_url=s.join_url,
            timeout_at=s.timeout_at,
            status=s.status,
            template=s.template,
            sprint_goal=s.sprint_goal,
        )
        for s in result.scalars()
    ]


# ── POST /sessions/{session_id}/human-message — US-27 human chat ─────────────


class HumanMessageRequest(BaseModel):
    sender_id: str
    sender_name: str
    content: str
    target: str = "all"  # "all" or a specific participant_id


@router.post("/{session_id}/human-message")
async def send_human_message(
    session_id: str,
    body: HumanMessageRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from app.a2a.client import A2AClient
    from app.a2a.models import CommEvent
    from app.comm_bus import publish_comm_event

    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(404, detail={"reason": "session_not_found"})
    if session.status != "ACTIVE":
        raise HTTPException(409, detail={"reason": "session_not_active", "status": session.status})

    slots_result = await db.execute(
        select(SessionParticipant).where(SessionParticipant.session_id == session_id)
    )
    slots = list(slots_result.scalars())

    # Persist message into session context (AC8 audit trail via DB)
    ctx = dict(session.context or {})
    messages: list[dict[str, Any]] = list(ctx.get("human_messages", []))
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    message_entry: dict[str, Any] = {
        "sender_id": body.sender_id,
        "sender_name": body.sender_name,
        "content": body.content,
        "target": body.target,
        "timestamp": timestamp,
    }
    messages.append(message_entry)
    ctx["human_messages"] = messages
    session.context = ctx
    await db.commit()

    # Publish to comm feed so all watchers see the human message immediately
    await publish_comm_event(CommEvent(
        comm_id=str(uuid4()),
        session_id=session_id,
        timestamp=timestamp,
        sender_id=body.sender_id,
        sender_name=body.sender_name,
        receiver_id=body.target if body.target != "all" else None,
        receiver_name=None,
        task_type="human_message",
        message_kind="human_message",
        content=body.content,
    ))

    log.info(
        "human_message.received session_id=%s sender=%s target=%s content_len=%d",
        session_id, body.sender_name, body.target, len(body.content),
    )

    # Identify target agent slots
    target_slots = [
        s for s in slots
        if s.slot_type == "AGENT"
        and s.status == "joined"
        and s.endpoint
        and (body.target == "all" or s.participant_id == body.target)
    ]

    session_ctx: dict[str, Any] = {
        "session_id": session_id,
        "sprint_goal": session.sprint_goal,
        "human_messages": messages,
        "participants": [
            {
                "participant_id": s.participant_id,
                "name": s.name,
                "role": s.role,
                "type": "AI_AGENT" if s.slot_type == "AGENT" else "HUMAN",
            }
            for s in slots
        ],
    }

    a2a = A2AClient(default_timeout_seconds=10.0)

    async def _dispatch_to_agent(slot: SessionParticipant) -> None:
        receiver_id = slot.participant_id or slot.id

        async def _on_thought(thought: str) -> None:
            await publish_comm_event(CommEvent(
                comm_id=str(uuid4()),
                session_id=session_id,
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
                sender_id=receiver_id,
                sender_name=slot.name,
                receiver_id=None,
                receiver_name=None,
                task_type="human_message",
                message_kind="thought",
                content=thought,
            ))

        try:
            await a2a.send_task(
                endpoint=slot.endpoint,
                task_type="human_message",
                session_ctx=session_ctx,
                payload={"content": body.content, "sender_name": body.sender_name},
                on_progress=_on_thought,
            )
        except Exception as exc:
            log.warning("human_message.agent_dispatch_failed slot=%s exc=%s", slot.id, exc)

    if target_slots:
        asyncio.create_task(
            asyncio.gather(*[_dispatch_to_agent(s) for s in target_slots], return_exceptions=True)
        )

    return {"ok": True, "dispatched_to": len(target_slots)}


# ── GET /sessions/{session_id}/comm-feed — US-26 communication feed SSE ───────


@router.get("/{session_id}/comm-feed")
async def comm_feed_sse(session_id: str) -> StreamingResponse:
    """Stream inter-agent CommEvents for the given session as SSE."""
    from app.message_bus import bus

    channel = f"session:comm:{session_id}"

    async def event_stream():
        pubsub = bus().pubsub()
        await pubsub.subscribe(channel)
        queue: asyncio.Queue[str] = asyncio.Queue()

        async def _reader() -> None:
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    await queue.put(msg["data"])

        reader = asyncio.create_task(_reader())
        try:
            yield f"data: {json.dumps({'type': 'connected', 'session_id': session_id})}\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
