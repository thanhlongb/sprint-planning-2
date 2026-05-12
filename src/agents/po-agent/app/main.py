"""Reference PRODUCT_OWNER A2A Remote Agent (US-05).

Hosts a compliant A2A HTTP server backed by a static backlog fixture.
All task handling is stateless — session state comes in via session_ctx only (AC8).
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

AGENT_NAME = os.environ.get("AGENT_NAME", "po-agent")
AGENT_PUBLIC_URL = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:8001")

# Declared auth scheme — validated on every inbound task call (AC7).
_AUTH_SCHEME = "none"

app = FastAPI(title=f"{AGENT_NAME} (A2A Remote Agent)")

# ── Static backlog fixture (AC4: ≥5 items, no metadata field) ─────────────────

STATIC_BACKLOG: list[dict[str, Any]] = [
    {
        "item_id": "PO-1",
        "title": "Add OAuth login",
        "description": "Allow users to sign in with Google and GitHub via OAuth 2.0.",
        "priority": "HIGH",
        "story_points": 8,
        "labels": ["auth", "security"],
        "dependencies": [],
    },
    {
        "item_id": "PO-2",
        "title": "User profile page",
        "description": "Display and allow editing of display name, avatar, and notification preferences.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["ui", "profile"],
        "dependencies": ["PO-1"],
    },
    {
        "item_id": "PO-3",
        "title": "Dark mode",
        "description": "Provide a persistent dark theme across the entire application.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["ui", "accessibility"],
        "dependencies": [],
    },
    {
        "item_id": "PO-4",
        "title": "Email notification digest",
        "description": "Send a daily summary email of activity in subscribed projects.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["notifications", "email"],
        "dependencies": ["PO-2"],
    },
    {
        "item_id": "PO-5",
        "title": "API rate limiting",
        "description": "Enforce per-token request quotas to protect service stability.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["api", "security"],
        "dependencies": [],
    },
    {
        "item_id": "PO-6",
        "title": "Audit log export",
        "description": "Allow admins to export a CSV of all user actions for the past 90 days.",
        "priority": "LOW",
        "story_points": 2,
        "labels": ["admin", "compliance"],
        "dependencies": [],
    },
]

# Priority ordering used for deterministic voting (AC5).
_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# Task types that use async SSE streaming.
_ASYNC_TASKS = {"present_backlog"}

# In-flight SSE queues keyed by task_id (stateless between separate task calls — AC8).
_streams: dict[str, asyncio.Queue[dict[str, Any]]] = {}

# ── Pydantic models ───────────────────────────────────────────────────────────


class Task(BaseModel):
    task_id: str
    task_type: str
    session_ctx: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Agent Card (AC1, AC2) ──────────────────────────────────────────────────────


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return {
        "name": AGENT_NAME,
        "description": "Reference Product Owner agent backed by a static backlog.",
        "role": "PRODUCT_OWNER",
        "capabilities": {
            "can_provide_backlog": True,
            "can_vote": True,
            "can_volunteer": False,
        },
        "endpoint": f"{AGENT_PUBLIC_URL}/a2a",
        "auth": {"scheme": _AUTH_SCHEME},
    }


# ── Auth guard (AC7) ──────────────────────────────────────────────────────────


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


def _own_participant_id(session_ctx: dict[str, Any]) -> str | None:
    """Resolve this agent's participant_id by matching AGENT_NAME in participants list."""
    for p in (session_ctx.get("participants") or []):
        if p.get("name") == AGENT_NAME:
            return p.get("participant_id")
    return None


# ── Task endpoint (AC3) ────────────────────────────────────────────────────────


@app.post("/a2a/tasks")
async def receive_task(task: Task, request: Request, response: Response) -> dict:
    _check_auth(request)

    # Async: present_backlog streams progress via SSE before returning the items.
    if task.task_type in _ASYNC_TASKS:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        _streams[task.task_id] = queue
        asyncio.create_task(_run_present_backlog(task, queue))
        response.status_code = 202
        return {"task_id": task.task_id, "status": "working"}

    if task.task_type == "session_invite":
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
        return {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"ack": True},
        }

    # Simple acknowledgement messages — no session state required.
    if task.task_type in ("session_ready", "session_aborted", "acknowledge_assignment", "sprint_backlog"):
        return {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"ack": True},
        }

    if task.task_type == "vote":
        return _handle_vote(task)

    if task.task_type == "confirm":
        return _handle_confirm(task)

    raise HTTPException(400, f"Unsupported task type: {task.task_type}")


# ── Vote handler (AC5) ────────────────────────────────────────────────────────


def _handle_vote(task: Task) -> dict:
    """Deterministically cast dot votes using only session_ctx fields (AC5).

    Strategy: mirror each item's declared priority from session_ctx.backlog_items.
    Items not found in the backlog receive MEDIUM as a safe default.
    Same input always produces the same output — no randomness involved.
    """
    items: list[str] = task.payload.get("items", [])
    backlog_items: list[dict] = task.session_ctx.get("backlog_items") or []

    priority_map: dict[str, str] = {
        item["item_id"]: item.get("priority", "MEDIUM")
        for item in backlog_items
        if "item_id" in item
    }

    votes: dict[str, str] = {
        item_id: priority_map.get(item_id, "MEDIUM")
        for item_id in items
    }
    return {
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {"votes": votes},
    }


# ── Confirm handler (AC6) ─────────────────────────────────────────────────────


def _handle_confirm(task: Task) -> dict:
    """Return confirmed=true only when session_ctx.selected_items is non-empty (AC6)."""
    selected_items = task.session_ctx.get("selected_items")
    confirmed = bool(selected_items)
    return {
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {"confirmed": confirmed},
    }


# ── SSE stream endpoint ───────────────────────────────────────────────────────


@app.get("/a2a/tasks/{task_id}")
async def stream_task(task_id: str, request: Request) -> StreamingResponse:
    queue = _streams.get(task_id)
    if queue is None:
        raise HTTPException(404, f"unknown task_id: {task_id}")

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    return
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("status") in ("completed", "failed"):
                    return
        finally:
            _streams.pop(task_id, None)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── present_backlog background task ──────────────────────────────────────────


async def _run_present_backlog(task: Task, queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Simulate a long-running backlog fetch, then emit the static fixture (AC4)."""
    await queue.put(
        {
            "task_id": task.task_id,
            "status": "working",
            "progress": "loading backlog from source system",
        }
    )
    await asyncio.sleep(0.3)
    await queue.put(
        {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"backlog": STATIC_BACKLOG},
        }
    )
