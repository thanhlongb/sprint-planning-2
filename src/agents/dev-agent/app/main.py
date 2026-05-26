"""Reference DEVELOPER A2A Remote Agent (US-06).

Hosts a compliant A2A HTTP server. All task handling is stateless —
session state comes in via session_ctx only (AC7).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

AGENT_NAME = os.environ.get("AGENT_NAME", "dev-agent")
AGENT_PUBLIC_URL = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:8002")

# Maximum items this agent will accept in a single session (AC4).
MAX_ASSIGNMENTS = int(os.environ.get("MAX_ASSIGNMENTS", "2"))

# Capacity configuration (US-34).
AGENT_CAPACITY_SP = int(os.environ.get("AGENT_CAPACITY_SP", "0"))
AGENT_SPECIALTIES: list[str] = [
    s.strip()
    for s in os.environ.get("AGENT_SPECIALTIES", "").split(",")
    if s.strip()
]

# Declared auth scheme — validated on every inbound task call.
_AUTH_SCHEME = "none"

app = FastAPI(title=f"{AGENT_NAME} (A2A Remote Agent)")


# ── Pydantic models ───────────────────────────────────────────────────────────


class Task(BaseModel):
    task_id: str
    task_type: str
    session_ctx: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Agent Card (AC1) ──────────────────────────────────────────────────────────


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return {
        "name": AGENT_NAME,
        "description": "Reference Developer agent that votes and volunteers for work.",
        "role": "DEVELOPER",
        "capabilities": {
            "can_vote": True,
            "can_volunteer": True,
            "capacity": {
                "story_points": AGENT_CAPACITY_SP,
                "specialties": AGENT_SPECIALTIES,
            },
        },
        "endpoint": f"{AGENT_PUBLIC_URL}/a2a",
        "auth": {"scheme": _AUTH_SCHEME},
    }


# ── Auth guard ────────────────────────────────────────────────────────────────


def _check_auth(request: Request) -> None:
    """Reject calls whose auth scheme does not match the Agent Card declaration."""
    has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
    if _AUTH_SCHEME == "none" and has_bearer:
        raise HTTPException(
            status_code=401,
            detail="Agent Card declares auth scheme 'none'; Bearer token not accepted.",
        )
    if _AUTH_SCHEME == "bearer" and not has_bearer:
        raise HTTPException(
            status_code=401,
            detail="Agent Card declares auth scheme 'bearer'; Authorization header required.",
        )


# ── Session-ctx helpers (AC5) ─────────────────────────────────────────────────


def _own_participant_id(session_ctx: dict[str, Any]) -> str | None:
    """Resolve this agent's participant_id by matching AGENT_NAME in participants list."""
    for p in (session_ctx.get("participants") or []):
        if p.get("name") == AGENT_NAME:
            return p.get("participant_id")
    return None


def _count_own_assignments(session_ctx: dict[str, Any]) -> int:
    """Count assignments attributed to this agent from session_ctx.assignments (AC5)."""
    own_id = _own_participant_id(session_ctx)
    if not own_id:
        return 0
    assignments: dict[str, str] = session_ctx.get("assignments") or {}
    return sum(1 for pid in assignments.values() if pid == own_id)


# ── Task endpoint (AC2) ───────────────────────────────────────────────────────


@app.post("/a2a/tasks")
async def receive_task(task: Task, request: Request) -> dict:
    _check_auth(request)

    if task.task_type == "session_invite":
        import asyncio
        import httpx
        async def auto_join():
            own_id = _own_participant_id(task.session_ctx)
            if own_id:
                session_id = task.session_ctx.get("session_id")
                platform_url = os.environ.get("PLATFORM_URL", "http://platform:8000")
                async with httpx.AsyncClient() as client:
                    try:
                        await client.post(
                            f"{platform_url}/sessions/{session_id}/join",
                            json={"participant_id": own_id}
                        )
                    except Exception as e:
                        print(f"Failed to auto-join: {e}")
        asyncio.create_task(auto_join())
        return {"task_id": task.task_id, "status": "completed", "artifact": {"ack": True}}

    if task.task_type in ("session_ready", "session_aborted", "acknowledge_assignment", "sprint_backlog"):
        return {"task_id": task.task_id, "status": "completed", "artifact": {"ack": True}}

    if task.task_type == "vote":
        return _handle_vote(task)

    if task.task_type == "assign_opportunity":
        return _handle_assign_opportunity(task)

    if task.task_type == "confirm":
        return _handle_confirm(task)

    if task.task_type == "recommendation_update":
        return _handle_recommendation_update(task)

    if task.task_type == "assignment_proposal":
        return _handle_assignment_proposal(task)

    raise HTTPException(400, f"Unsupported task type: {task.task_type}")


# ── Vote handler (AC3) ────────────────────────────────────────────────────────


def _handle_vote(task: Task) -> dict:
    """Cast dot votes using priority from session_ctx.backlog_items (AC3).

    Strategy: mirror each item's declared priority from the backlog.
    Same input always produces the same output — no randomness.
    Items absent from the backlog default to MEDIUM.
    """
    items: list[str] = task.payload.get("items", [])
    backlog_items: list[dict] = task.session_ctx.get("backlog_items") or []

    priority_map: dict[str, str] = {
        item["item_id"]: item.get("priority", "MEDIUM")
        for item in backlog_items
        if "item_id" in item
    }
    votes = {item_id: priority_map.get(item_id, "MEDIUM") for item_id in items}
    return {"task_id": task.task_id, "status": "completed", "artifact": {"votes": votes}}


# ── Assign-opportunity handler (AC4, AC5) ─────────────────────────────────────


def _handle_assign_opportunity(task: Task) -> dict:
    """Volunteer if current assignment count < MAX_ASSIGNMENTS (AC4).

    Assignment count is read from session_ctx.assignments — no internal counter (AC5).
    """
    current = _count_own_assignments(task.session_ctx)
    volunteer = current < MAX_ASSIGNMENTS
    return {"task_id": task.task_id, "status": "completed", "artifact": {"volunteer": volunteer}}


# ── Confirm handler (AC6) ─────────────────────────────────────────────────────


def _handle_confirm(task: Task) -> dict:
    """Return confirmed=true only when this agent has ≥1 assignment (AC6)."""
    confirmed = _count_own_assignments(task.session_ctx) > 0
    return {"task_id": task.task_id, "status": "completed", "artifact": {"confirmed": confirmed}}


# ── Recommendation-update handler (US-36 AC2) ────────────────────────────────


def _handle_recommendation_update(task: Task) -> dict:
    """Acknowledge receipt of a recommendation update.  Informational only.

    The platform broadcasts recalculated recommendation lists during the
    discussion-driven refinement phase.  No decision is required from the agent.
    """
    return {"task_id": task.task_id, "status": "completed", "artifact": {"ack": True}}


# ── Assignment-proposal handler (US-36 AC3) ───────────────────────────────────


def _handle_assignment_proposal(task: Task) -> dict:
    """Respond to algorithmic assignment map with structured decisions.

    Receives the assignment map (item_id → participant_id) and returns
    volunteer/object/reassignment decisions based on specialty alignment.
    """
    assignments: dict[str, str] = task.payload.get("assignments", {})
    backlog_items: list[dict] = task.session_ctx.get("backlog_items") or []
    own_id = _own_participant_id(task.session_ctx)

    volunteers: list[str] = []
    objects: list[str] = []
    reassignments: list[dict] = []

    if not own_id:
        return {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {
                "volunteers": volunteers,
                "objects": objects,
                "reassignments": reassignments,
            },
        }

    item_map: dict[str, dict] = {
        item["item_id"]: item for item in backlog_items if "item_id" in item
    }

    my_specialties: set[str] = set(AGENT_SPECIALTIES)

    # Items assigned to this agent
    assigned_to_me = [iid for iid, pid in assignments.items() if pid == own_id]

    # Object to items assigned to me that don't match my specialties
    for iid in assigned_to_me:
        item = item_map.get(iid, {})
        labels: set[str] = set(item.get("labels", []))
        if my_specialties and not labels & my_specialties:
            objects.append(iid)

    # Volunteer for unassigned items matching specialties (respect capacity)
    total_sp = sum(
        item_map.get(iid, {}).get("story_points", 0) for iid in assigned_to_me
    )
    capacity = AGENT_CAPACITY_SP
    for iid, pid in assignments.items():
        if pid:  # skip already assigned items (including unassigned/empty)
            continue
        item = item_map.get(iid, {})
        labels = set(item.get("labels", []))
        sp = item.get("story_points", 1)
        if my_specialties and labels & my_specialties:
            if capacity == 0 or total_sp + sp <= capacity:
                volunteers.append(iid)
                total_sp += sp

    return {
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {
            "volunteers": volunteers,
            "objects": objects,
            "reassignments": reassignments,
        },
    }
