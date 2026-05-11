"""Reference PRODUCT_OWNER A2A Remote Agent.

Implements the agent side of US-01: accepts the platform's task envelope on
`POST /a2a/tasks` and, for long-running task types, returns `202 working` and
streams updates via `GET /a2a/tasks/{task_id}` (SSE).
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

app = FastAPI(title=f"{AGENT_NAME} (A2A Remote Agent)")

STATIC_BACKLOG = [
    {
        "item_id": "PO-1",
        "title": "Add OAuth login",
        "description": "Allow users to sign in with Google.",
        "priority": "HIGH",
        "story_points": None,
        "labels": ["auth"],
        "dependencies": [],
    },
    {
        "item_id": "PO-2",
        "title": "Dark mode",
        "description": "Provide a dark theme across the app.",
        "priority": "MEDIUM",
        "story_points": None,
        "labels": ["ui"],
        "dependencies": [],
    },
]

# Task types that take noticeable time and should stream via SSE.
ASYNC_TASKS = {"present_backlog"}


class Task(BaseModel):
    task_id: str
    task_type: str
    session_ctx: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


_streams: dict[str, asyncio.Queue[dict[str, Any]]] = {}


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
        "auth": {"scheme": "none"},
    }


@app.post("/a2a/tasks")
async def receive_task(task: Task, response: Response) -> dict:
    if task.task_type in ASYNC_TASKS:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        _streams[task.task_id] = queue
        asyncio.create_task(_run_present_backlog(task, queue))
        response.status_code = 202
        return {"task_id": task.task_id, "status": "working"}

    if task.task_type in ("session_invite", "session_ready", "acknowledge_assignment"):
        return {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"ack": True},
        }

    if task.task_type == "confirm":
        return {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"confirmed": True},
        }

    if task.task_type == "vote":
        items = task.payload.get("items", [])
        return {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"votes": {item: "HIGH" for item in items}},
        }

    raise HTTPException(400, f"Unsupported task type: {task.task_type}")


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


async def _run_present_backlog(
    task: Task, queue: asyncio.Queue[dict[str, Any]]
) -> None:
    """Simulate a long-running backlog presentation."""
    await queue.put(
        {
            "task_id": task.task_id,
            "status": "working",
            "progress": "loading backlog from source system",
        }
    )
    await asyncio.sleep(0.5)
    await queue.put(
        {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"backlog": STATIC_BACKLOG},
        }
    )
