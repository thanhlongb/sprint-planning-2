import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Participant

router = APIRouter()


class RegisterRequest(BaseModel):
    agent_card_url: HttpUrl


class ParticipantOut(BaseModel):
    id: str
    name: str
    role: str
    endpoint: str

    model_config = {"from_attributes": True}


@router.post("", response_model=ParticipantOut, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_session)) -> ParticipantOut:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(str(req.agent_card_url))
    if resp.status_code != 200:
        raise HTTPException(400, f"Could not fetch agent card: HTTP {resp.status_code}")
    card = resp.json()
    for field in ("name", "role", "endpoint"):
        if field not in card:
            raise HTTPException(400, f"Agent card missing required field: {field}")

    participant = Participant(
        name=card["name"], role=card["role"], endpoint=card["endpoint"], agent_card=card
    )
    db.add(participant)
    await db.commit()
    await db.refresh(participant)
    return ParticipantOut.model_validate(participant)


@router.get("", response_model=list[ParticipantOut])
async def list_participants(db: AsyncSession = Depends(get_session)) -> list[ParticipantOut]:
    result = await db.execute(select(Participant))
    return [ParticipantOut.model_validate(p) for p in result.scalars()]
