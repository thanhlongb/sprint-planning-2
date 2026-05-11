"""Reference DEVELOPER A2A Remote Agent.

Agent side of US-01: accepts the new task envelope and responds synchronously
(all developer tasks are short).
"""

from __future__ import annotations

import os
import random
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

AGENT_NAME = os.environ.get("AGENT_NAME", "dev-agent")
AGENT_PUBLIC_URL = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:8002")

app = FastAPI(title=f"{AGENT_NAME} (A2A Remote Agent)")


class Task(BaseModel):
    task_id: str
    task_type: str
    session_ctx: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return {
        "name": AGENT_NAME,
        "description": "Reference Developer agent that votes and volunteers for work.",
        "role": "DEVELOPER",
        "capabilities": {
            "can_provide_backlog": False,
            "can_vote": True,
            "can_volunteer": True,
        },
        "endpoint": f"{AGENT_PUBLIC_URL}/a2a",
        "auth": {"scheme": "none"},
    }


@app.post("/a2a/tasks")
async def receive_task(task: Task) -> dict:
    if task.task_type in (
        "session_invite",
        "session_ready",
        "session_aborted",
        "acknowledge_assignment",
    ):
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
        priorities = ["HIGH", "MEDIUM", "LOW"]
        return {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"votes": {item: random.choice(priorities) for item in items}},
        }

    if task.task_type == "assign_opportunity":
        item_id = task.payload.get("item_id")
        return {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"volunteer": True, "item_id": item_id, "estimate": 3},
        }

    raise HTTPException(400, f"Unsupported task type: {task.task_type}")
