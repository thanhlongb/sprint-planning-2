"""Debug endpoint to manually dispatch an A2A task to a registered participant.

Used to exercise US-01 end-to-end before the Phase Orchestrator (US-04) exists.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.a2a import A2AClient, TaskStatus
from app.config import settings
from app.db import get_session
from app.models import Participant

router = APIRouter()
_client = A2AClient()


class SendTaskRequest(BaseModel):
    participant_id: str
    task_type: str
    session_id: str = "debug-session"
    session_ctx: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    duration_limit_seconds: float | None = None


class SendTaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    artifact: dict[str, Any] | None = None
    error: str | None = None
    progress: list[str] | None = None


@router.post("/send", response_model=SendTaskResponse)
async def send_task(
    req: SendTaskRequest, db: AsyncSession = Depends(get_session)
) -> SendTaskResponse:
    participant = await db.get(Participant, req.participant_id)
    if participant is None:
        raise HTTPException(404, f"participant {req.participant_id} not registered")

    session_ctx = {"session_id": req.session_id, **req.session_ctx}
    result = await _client.send_task(
        endpoint=participant.endpoint,
        task_type=req.task_type,
        session_ctx=session_ctx,
        payload=req.payload,
        auth=participant.agent_card.get("auth"),
        bearer_token=settings.a2a_bearer_token,
        duration_limit_seconds=req.duration_limit_seconds,
    )
    return SendTaskResponse(
        task_id=result.task_id,
        status=result.status,
        artifact=result.artifact,
        error=result.error,
        progress=result.progress,
    )
