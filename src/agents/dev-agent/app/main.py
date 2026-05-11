import os
import random
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

AGENT_NAME = os.environ.get("AGENT_NAME", "dev-agent")
AGENT_PUBLIC_URL = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:8002")

app = FastAPI(title=f"{AGENT_NAME} (A2A Remote Agent)")


class Task(BaseModel):
    type: str
    session_ctx: dict | None = None
    payload: dict | None = None


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
    task_id = str(uuid4())
    payload = task.payload or {}

    if task.type in ("session_invite", "session_ready", "confirm", "session_aborted"):
        return {"task_id": task_id, "status": "completed", "artifact": {"ack": True}}

    if task.type == "vote":
        items = payload.get("items", [])
        priorities = ["HIGH", "MEDIUM", "LOW"]
        return {
            "task_id": task_id,
            "status": "completed",
            "artifact": {"votes": {item: random.choice(priorities) for item in items}},
        }

    if task.type == "assign_opportunity":
        item_id = payload.get("item_id")
        return {
            "task_id": task_id,
            "status": "completed",
            "artifact": {"volunteer": True, "item_id": item_id, "estimate": 3},
        }

    if task.type == "acknowledge_assignment":
        return {"task_id": task_id, "status": "completed", "artifact": {"ack": True}}

    raise HTTPException(400, f"Unsupported task type: {task.type}")
