from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    endpoint: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    template: Mapped[str] = mapped_column(String, nullable=False, default="sprint_planning_v1")
    sprint_goal: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")
    join_url: Mapped[str] = mapped_column(String, nullable=False, default="")
    timeout_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SessionParticipant(Base):
    """One row per declared participant slot in a session."""

    __tablename__ = "session_participants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    # Assigned once the slot is filled (declared agents already have one; humans get one on join).
    participant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    # "AGENT" | "HUMAN"
    slot_type: Mapped[str] = mapped_column(String, nullable=False)
    # A2A endpoint for agents (None for humans).
    endpoint: Mapped[str | None] = mapped_column(String, nullable=True)
    # "declared" | "joined" | "absent"
    status: Mapped[str] = mapped_column(String, nullable=False, default="declared")


class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), nullable=False, unique=True, index=True)
    sprint_goal: Mapped[str] = mapped_column(String, nullable=False, default="")
    template_used: Mapped[str] = mapped_column(String, nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    participants: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    backlog_output: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    phase_breakdown: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    key_decisions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    messages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # "OK" | "PARTIAL"
    generation_status: Mapped[str] = mapped_column(String, nullable=False, default="OK")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    raw_yaml: Mapped[str] = mapped_column(String, nullable=False)
    phases: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    inputs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    outputs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
