"""Session Manager API (US-03).

POST /sessions      — create session with declared participants (AC1, AC2, AC3)
POST /sessions/{id}/join — agent or human joins (AC4, AC5)
GET  /sessions/{id} — inspect session state
GET  /sessions      — list all sessions
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import Participant, Session, SessionParticipant
from app.session_service import (
    maybe_activate,
    schedule_timeout,
    send_invites_background,
)

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
    timeout_at = datetime.now(tz=timezone.utc) + timedelta(minutes=settings.join_timeout_minutes)

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

    session.join_url = f"{settings.platform_base_url.rstrip('/')}/sessions/{session.id}/join"

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
