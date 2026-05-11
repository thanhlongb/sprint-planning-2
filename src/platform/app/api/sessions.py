from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Session

router = APIRouter()


class CreateSessionRequest(BaseModel):
    template: str = "sprint_planning_v1"


class SessionOut(BaseModel):
    id: str
    template: str
    status: str

    model_config = {"from_attributes": True}


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    req: CreateSessionRequest, db: AsyncSession = Depends(get_session)
) -> SessionOut:
    session = Session(template=req.template, status="pending", context={})
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionOut.model_validate(session)


@router.get("", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_session)) -> list[SessionOut]:
    result = await db.execute(select(Session))
    return [SessionOut.model_validate(s) for s in result.scalars()]
