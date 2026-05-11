import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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


class Task(BaseModel):
    type: str
    session_ctx: dict | None = None
    payload: dict | None = None


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
async def receive_task(task: Task) -> dict:
    task_id = str(uuid4())
    if task.type == "present_backlog":
        return {
            "task_id": task_id,
            "status": "completed",
            "artifact": {"backlog": STATIC_BACKLOG},
        }
    if task.type in ("session_invite", "session_ready", "confirm", "acknowledge_assignment"):
        return {"task_id": task_id, "status": "completed", "artifact": {"ack": True}}
    if task.type == "vote":
        items = (task.payload or {}).get("items", [])
        return {
            "task_id": task_id,
            "status": "completed",
            "artifact": {"votes": {item: "HIGH" for item in items}},
        }
    raise HTTPException(400, f"Unsupported task type: {task.type}")
