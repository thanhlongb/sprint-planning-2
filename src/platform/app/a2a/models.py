from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskEnvelope(BaseModel):
    """Wire format for POST {agent_endpoint}/tasks (AC1)."""

    task_id: str
    task_type: str
    session_ctx: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskAck(BaseModel):
    """202 acknowledgement returned by an agent for an async task (AC3)."""

    task_id: str
    status: Literal["working"] = "working"


class TaskEvent(BaseModel):
    """One frame off the SSE stream (AC4)."""

    task_id: str
    status: TaskStatus
    progress: str | None = None
    artifact: dict[str, Any] | None = None
    error: str | None = None


class CommEvent(BaseModel):
    """A single inter-agent communication event for the US-26 comm feed."""

    event_type: str = "comm_event"
    comm_id: str
    session_id: str
    timestamp: str  # ISO-8601
    sender_id: str
    sender_name: str
    receiver_id: str | None = None
    receiver_name: str | None = None
    task_type: str
    # "task_request" | "task_response" | "thought"
    message_kind: str
    content: dict[str, Any] | str
