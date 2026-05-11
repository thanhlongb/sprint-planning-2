from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Participant

router = APIRouter()


class ParticipantOut(BaseModel):
    id: str
    name: str
    role: str
    endpoint: str
    capabilities: dict

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ParticipantOut])
async def list_participants(db: AsyncSession = Depends(get_session)) -> list[ParticipantOut]:
    result = await db.execute(select(Participant))
    return [ParticipantOut.model_validate(p) for p in result.scalars()]
