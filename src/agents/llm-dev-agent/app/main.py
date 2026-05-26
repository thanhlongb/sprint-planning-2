"""LLM-Backed DEVELOPER A2A Remote Agent (US-25).

Uses an LLM to reason about the sprint backlog against a configurable developer
persona before casting votes and volunteering for tasks.  All task handling is
stateless — session state comes in via session_ctx only (AC2, AC3).

Key behaviours
--------------
* vote               — LLM evaluates backlog items against persona to assign priority
                       votes; streams reasoning thoughts while working (AC1, AC3).
* assign_opportunity — LLM decides whether to volunteer given current workload and
                       item complexity; hard-capped at 5 s (AC2, AC5).
* session_invite     — auto-joins the session via the platform REST API.
* All other task types return a simple ack.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# ── Environment configuration ─────────────────────────────────────────────────

AGENT_NAME: str = os.environ.get("AGENT_NAME", "llm-dev-agent")
AGENT_PUBLIC_URL: str = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:8012")
PLATFORM_URL: str = os.environ.get("PLATFORM_URL", "http://platform:8000")

LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "anthropic").lower()
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

PERSONA_SPECIALTIES: list[str] = [
    s.strip()
    for s in os.environ.get("PERSONA_SPECIALTIES", "backend,API,Python").split(",")
    if s.strip()
]
PERSONA_SENIORITY: str = os.environ.get("PERSONA_SENIORITY", "senior")
MAX_ASSIGNMENTS: int = int(os.environ.get("MAX_ASSIGNMENTS", "2"))

# Capacity configuration (US-34).
AGENT_CAPACITY_SP: int = int(os.environ.get("AGENT_CAPACITY_SP", "0"))
AGENT_SPECIALTIES: list[str] = [
    s.strip()
    for s in os.environ.get("AGENT_SPECIALTIES", "").split(",")
    if s.strip()
]

ASSIGNMENT_LLM_TIMEOUT: float = 4.5  # beats the platform's 5 s hard deadline (AC5)
DEFAULT_LLM_TIMEOUT: float = 30.0

_AUTH_SCHEME = "none"
_ASYNC_TASKS: set[str] = {"vote", "assign_opportunity"}

_streams: dict[str, asyncio.Queue[dict[str, Any]]] = {}

app = FastAPI(title=f"{AGENT_NAME} (LLM-Backed Developer A2A Agent)")

logging.basicConfig(level=logging.INFO)


# ── Pydantic models ───────────────────────────────────────────────────────────


class Task(BaseModel):
    task_id: str
    task_type: str
    session_ctx: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Agent Card ────────────────────────────────────────────────────────────────


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return {
        "name": AGENT_NAME,
        "description": (
            f"LLM-backed Developer agent ({PERSONA_SENIORITY}, "
            f"specialties: {', '.join(PERSONA_SPECIALTIES)}). "
            "Reasons about backlog items and workload before volunteering."
        ),
        "role": "DEVELOPER",
        "capabilities": {
            "can_vote": True,
            "can_volunteer": True,
            "llm_backed": True,
            "streams_thoughts": True,
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


# ── Session-ctx helpers ───────────────────────────────────────────────────────


def _own_participant_id(session_ctx: dict[str, Any]) -> str | None:
    for p in session_ctx.get("participants") or []:
        if p.get("name") == AGENT_NAME:
            return p.get("participant_id")
    return None


def _count_own_assignments(session_ctx: dict[str, Any]) -> int:
    own_id = _own_participant_id(session_ctx)
    if not own_id:
        return 0
    assignments: dict[str, str] = session_ctx.get("assignments") or {}
    return sum(1 for pid in assignments.values() if pid == own_id)


# ── Task endpoint ─────────────────────────────────────────────────────────────


@app.post("/a2a/tasks")
async def receive_task(task: Task, request: Request, response: Response) -> dict:
    _check_auth(request)
    log.info(
        "task.received agent=%s task_id=%s task_type=%s session_id=%s",
        AGENT_NAME, task.task_id, task.task_type,
        task.session_ctx.get("session_id", "<no-session>"),
    )

    if task.task_type in _ASYNC_TASKS:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        _streams[task.task_id] = queue
        if task.task_type == "vote":
            asyncio.create_task(_run_vote(task, queue))
        elif task.task_type == "assign_opportunity":
            asyncio.create_task(_run_assign_opportunity(task, queue))
        response.status_code = 202
        return {"task_id": task.task_id, "status": "working"}

    if task.task_type == "session_invite":
        asyncio.create_task(_auto_join(task))
        return {"task_id": task.task_id, "status": "completed", "artifact": {"ack": True}}

    if task.task_type in (
        "session_ready", "session_aborted", "acknowledge_assignment", "sprint_backlog"
    ):
        return {"task_id": task.task_id, "status": "completed", "artifact": {"ack": True}}

    if task.task_type == "confirm":
        return _handle_confirm(task)

    if task.task_type == "human_message":
        return await _handle_human_message(task)

    if task.task_type == "direct_message":
        return await _handle_direct_message(task)

    raise HTTPException(400, f"Unsupported task type: {task.task_type!r}")


# ── SSE stream endpoint ───────────────────────────────────────────────────────


@app.get("/a2a/tasks/{task_id}")
async def stream_task(task_id: str, request: Request) -> StreamingResponse:
    queue = _streams.get(task_id)
    if queue is None:
        raise HTTPException(404, f"Unknown task_id: {task_id!r}")

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


# ── Auto-join helper ──────────────────────────────────────────────────────────


async def _auto_join(task: Task) -> None:
    own_id = _own_participant_id(task.session_ctx)
    if not own_id:
        return
    session_id = task.session_ctx.get("session_id")
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{PLATFORM_URL}/sessions/{session_id}/join",
                json={"participant_id": own_id},
            )
            log.info("auto_join.ok session_id=%s participant_id=%s", session_id, own_id)
        except Exception as exc:
            log.warning("auto_join.failed session_id=%s exc=%s", session_id, exc)
            return

    intro = (
        f"Hi everyone, I'm {AGENT_NAME} — a {PERSONA_SENIORITY} developer "
        f"specialising in {', '.join(PERSONA_SPECIALTIES)}. "
        f"I can take up to {MAX_ASSIGNMENTS} items this sprint. Looking forward to planning!"
    )
    await _post_agent_message(session_id, own_id, intro)


# ── Proactive message helper ──────────────────────────────────────────────────


async def _post_agent_message(session_id: str, agent_id: str, content: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(
                f"{PLATFORM_URL}/sessions/{session_id}/message",
                json={
                    "sender_id": agent_id,
                    "sender_name": AGENT_NAME,
                    "content": content,
                    "reply_depth": 1,
                },
            )
        except Exception as exc:
            log.warning("post_agent_message.failed session_id=%s exc=%s", session_id, exc)


# ── Human message handler (US-27 AC4) ────────────────────────────────────────


async def _handle_human_message(task: Task) -> dict:
    sender_name = task.payload.get("sender_name", "a participant")
    content = task.payload.get("content", "")
    log.info("human_message.received from=%s content=%r", sender_name, content[:120])

    system_prompt = (
        f"You are a {PERSONA_SENIORITY} software developer with specialties in: "
        f"{', '.join(PERSONA_SPECIALTIES)}. "
        "You are participating in an agile sprint planning session. "
        "Reply concisely and in character to the human participant's message. "
        "Be helpful and professional. Keep your reply to 1-2 sentences."
    )
    user_prompt = (
        f"Sprint goal: {task.session_ctx.get('sprint_goal', '')}\n\n"
        f"{sender_name} says: {content}\n\n"
        "Reply in character as the developer."
    )

    reply = f"Thanks {sender_name}, noted."
    try:
        reply = await asyncio.wait_for(_call_llm(system_prompt, user_prompt), timeout=8.0)
    except Exception as exc:
        log.warning("human_message.llm_failed exc=%s", exc)

    return {
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {"ack": True, "reply": reply},
    }


# ── Direct message handler ────────────────────────────────────────────────────


async def _handle_direct_message(task: Task) -> dict:
    sender_name = task.payload.get("sender_name", "a participant")
    content = task.payload.get("content", "")
    recent_messages: list[dict] = task.payload.get("recent_messages") or []
    session_id = task.session_ctx.get("session_id", "<no-session>")
    log.info("direct_message.received from=%s content=%r", sender_name, content[:120])

    history = "\n".join(
        f"[{m.get('timestamp', '')[:19]}] {m.get('sender_name', '?')}: {m.get('content', '')}"
        for m in recent_messages[-10:]
    )
    participants = task.session_ctx.get("participants", [])
    participant_summary = ", ".join(
        f"{p.get('name')} ({p.get('role')})" for p in participants
    )

    system_prompt = (
        f"You are a {PERSONA_SENIORITY} software developer specialising in "
        f"{', '.join(PERSONA_SPECIALTIES)}. "
        "You are in an agile sprint planning session. "
        "A participant has @mentioned you in the team chat. "
        "Reply concisely and in character (1-3 sentences). "
        "Do not @-mention other participants in your reply."
    )
    user_prompt = (
        f"Sprint goal: {task.session_ctx.get('sprint_goal', '')}\n"
        f"Participants: {participant_summary}\n\n"
        f"Recent conversation:\n{history or '(none yet)'}\n\n"
        f"{sender_name} says to you: {content}\n\n"
        "Reply in character as the developer."
    )

    reply = f"Thanks {sender_name}, I'll keep that in mind."
    try:
        reply = await asyncio.wait_for(_call_llm(system_prompt, user_prompt), timeout=9.0)
    except Exception as exc:
        log.warning("direct_message.llm_failed exc=%s", exc)

    own_id = _own_participant_id(task.session_ctx)
    if own_id and session_id != "<no-session>":
        asyncio.create_task(_post_agent_message(session_id, own_id, reply))

    return {"task_id": task.task_id, "status": "completed", "artifact": {"ack": True}}


# ── Confirm handler ───────────────────────────────────────────────────────────


def _handle_confirm(task: Task) -> dict:
    confirmed = _count_own_assignments(task.session_ctx) > 0
    return {
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {"confirmed": confirmed},
    }


# ── Vote background task (AC1, AC3) ──────────────────────────────────────────


async def _run_vote(task: Task, queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Use LLM to evaluate backlog items against persona and assign priority votes."""
    session_id = task.session_ctx.get("session_id", "<no-session>")
    items: list[str] = task.payload.get("items", [])
    backlog_items: list[dict] = task.session_ctx.get("backlog_items") or []
    sprint_goal: str = task.session_ctx.get("sprint_goal", "")
    human_messages: list[dict] = task.session_ctx.get("human_messages") or []

    await queue.put({
        "task_id": task.task_id,
        "status": "working",
        "progress": "Analysing backlog items against developer persona...",
    })

    item_map: dict[str, dict] = {
        item["item_id"]: item for item in backlog_items if "item_id" in item
    }

    items_text = "\n".join(
        f"- {iid}: {item_map.get(iid, {}).get('title', iid)} "
        f"[priority={item_map.get(iid, {}).get('priority', 'UNKNOWN')}, "
        f"sp={item_map.get(iid, {}).get('story_points', '?')}, "
        f"labels={item_map.get(iid, {}).get('labels', [])}]"
        for iid in items
    )

    system_prompt = (
        f"You are a {PERSONA_SENIORITY} software developer with the following specialties: "
        f"{', '.join(PERSONA_SPECIALTIES)}.\n"
        "You are participating in an agile sprint planning session.\n"
        "Your job is to evaluate backlog items and cast dot-votes based on how important "
        "each item is — weighted towards items that align with your specialties and the sprint goal.\n"
        "Return ONLY a valid JSON object mapping each item_id to a priority string: "
        'HIGH, MEDIUM, or LOW. Example: {"ITEM-1": "HIGH", "ITEM-2": "LOW"}'
    )

    user_prompt = (
        f"Sprint goal: {sprint_goal}\n\n"
        f"Backlog items to evaluate:\n{items_text}\n\n"
        f"My specialties are: {', '.join(PERSONA_SPECIALTIES)}.\n"
        "For each item, decide HIGH / MEDIUM / LOW priority from my perspective.\n"
        "Favour items that match my specialties or are critical blockers.\n"
        "Output ONLY valid JSON mapping item_id to priority."
    )

    if human_messages:
        notes = "\n".join(
            f"- {m.get('sender_name', 'participant')}: {m.get('content', '')}"
            for m in human_messages[-5:]
        )
        user_prompt += f"\n\nAdditional context from session participants:\n{notes}"

    await queue.put({
        "task_id": task.task_id,
        "status": "working",
        "progress": f"Calling LLM ({LLM_PROVIDER}) to vote on {len(items)} items...",
    })

    try:
        raw_response = await asyncio.wait_for(
            _call_llm(system_prompt, user_prompt),
            timeout=DEFAULT_LLM_TIMEOUT,
        )
    except asyncio.TimeoutError:
        log.warning("vote.llm_timeout task_id=%s session_id=%s", task.task_id, session_id)
        raw_response = None
    except Exception as exc:
        log.error("vote.llm_error task_id=%s exc=%s", task.task_id, exc)
        raw_response = None

    votes: dict[str, str] = {}
    if raw_response:
        votes = _parse_votes(raw_response, items)
        await queue.put({
            "task_id": task.task_id,
            "status": "working",
            "progress": f"LLM reasoning complete. Votes cast for {len(votes)} items.",
        })

    # Fallback for any items not returned by LLM (AC4)
    for item_id in items:
        if item_id not in votes:
            declared = item_map.get(item_id, {}).get("priority", "MEDIUM")
            votes[item_id] = declared if declared in ("HIGH", "MEDIUM", "LOW") else "MEDIUM"

    log.info("vote.completed task_id=%s session_id=%s votes=%s", task.task_id, session_id, votes)

    own_id = _own_participant_id(task.session_ctx)
    if own_id and session_id != "<no-session>":
        high_items = [iid for iid, p in votes.items() if p == "HIGH"]
        if high_items:
            item_titles = [
                item_map.get(iid, {}).get("title", iid) for iid in high_items[:3]
            ]
            comment = (
                f"I've cast my votes. From my perspective as a {PERSONA_SENIORITY} "
                f"{'/'.join(PERSONA_SPECIALTIES)} dev, the highest-priority items are: "
                + ", ".join(f'"{t}"' for t in item_titles)
                + ("." if len(high_items) <= 3 else f" (and {len(high_items) - 3} more).")
            )
            asyncio.create_task(_post_agent_message(session_id, own_id, comment))

    await queue.put({
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {"votes": votes},
    })


# ── Assign-opportunity background task (AC2, AC3, AC5) ───────────────────────


async def _run_assign_opportunity(task: Task, queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Use LLM to decide whether to volunteer for a task, within a 5 s window (AC5)."""
    session_id = task.session_ctx.get("session_id", "<no-session>")
    item_id: str = task.payload.get("item_id", "")
    item_title: str = task.payload.get("title", item_id)
    current_assignments = _count_own_assignments(task.session_ctx)
    backlog_items: list[dict] = task.session_ctx.get("backlog_items") or []
    sprint_goal: str = task.session_ctx.get("sprint_goal", "")
    human_messages: list[dict] = task.session_ctx.get("human_messages") or []

    await queue.put({
        "task_id": task.task_id,
        "status": "working",
        "progress": f"Evaluating whether to volunteer for '{item_title}'...",
    })

    # Short-circuit when already at capacity — no need to call LLM (AC5)
    if current_assignments >= MAX_ASSIGNMENTS:
        log.info(
            "assign_opportunity.capacity_full task_id=%s item_id=%s current=%d max=%d",
            task.task_id, item_id, current_assignments, MAX_ASSIGNMENTS,
        )
        await queue.put({
            "task_id": task.task_id,
            "status": "working",
            "progress": (
                f"Already at maximum capacity ({current_assignments}/{MAX_ASSIGNMENTS}). "
                "Not volunteering."
            ),
        })
        await queue.put({
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"volunteer": False},
        })
        return

    item_map: dict[str, dict] = {
        item["item_id"]: item for item in backlog_items if "item_id" in item
    }
    target_item = item_map.get(item_id, {"item_id": item_id, "title": item_title})
    target_labels: list[str] = target_item.get("labels", [])
    target_sp: Any = target_item.get("story_points", "unknown")
    target_priority: str = target_item.get("priority", "MEDIUM")

    assignments: dict[str, str] = task.session_ctx.get("assignments") or {}
    own_id = _own_participant_id(task.session_ctx)
    my_items: list[str] = [iid for iid, pid in assignments.items() if pid == own_id]
    my_items_detail = ", ".join(
        f"{iid} ({item_map.get(iid, {}).get('title', iid)})" for iid in my_items
    ) or "none"

    system_prompt = (
        f"You are a {PERSONA_SENIORITY} software developer with specialties in: "
        f"{', '.join(PERSONA_SPECIALTIES)}.\n"
        "You are in a sprint planning session and the platform is offering you a task.\n"
        "Decide whether you should volunteer based on:\n"
        "  1. Whether the task aligns with your specialties.\n"
        f"  2. Your current workload (you can take at most {MAX_ASSIGNMENTS} tasks total).\n"
        "  3. The task's complexity (story points and priority).\n"
        'Return ONLY a valid JSON object: {"volunteer": true|false, "reason": "brief explanation"}'
    )

    user_prompt = (
        f"Sprint goal: {sprint_goal}\n\n"
        f"Task being offered:\n"
        f"  item_id: {item_id}\n"
        f"  title: {item_title}\n"
        f"  labels: {target_labels}\n"
        f"  story_points: {target_sp}\n"
        f"  priority: {target_priority}\n\n"
        f"My current assignments ({current_assignments}/{MAX_ASSIGNMENTS}): {my_items_detail}\n"
        f"My specialties: {', '.join(PERSONA_SPECIALTIES)}\n\n"
        'Should I volunteer? Output ONLY valid JSON: {"volunteer": true|false, "reason": "..."}'
    )

    if human_messages:
        notes = "\n".join(
            f"- {m.get('sender_name', 'participant')}: {m.get('content', '')}"
            for m in human_messages[-5:]
        )
        user_prompt += f"\n\nAdditional context from session participants:\n{notes}"

    await queue.put({
        "task_id": task.task_id,
        "status": "working",
        "progress": f"Calling LLM ({LLM_PROVIDER}) to evaluate fit and workload...",
    })

    volunteer = False
    reason = "LLM timeout -- defaulting to not volunteering"

    try:
        raw_response = await asyncio.wait_for(
            _call_llm(system_prompt, user_prompt),
            timeout=ASSIGNMENT_LLM_TIMEOUT,
        )
        parsed = _parse_volunteer(raw_response)
        volunteer = parsed.get("volunteer", False)
        reason = parsed.get("reason", "")
    except asyncio.TimeoutError:
        log.warning(
            "assign_opportunity.llm_timeout task_id=%s session_id=%s -- falling back to False",
            task.task_id, session_id,
        )
        reason = "LLM timed out (>4.5 s); defaulting to not volunteering (AC5)."
    except Exception as exc:
        log.error(
            "assign_opportunity.llm_error task_id=%s exc=%s -- falling back to False",
            task.task_id, exc,
        )
        reason = f"LLM error: {exc}; defaulting to not volunteering."

    await queue.put({
        "task_id": task.task_id,
        "status": "working",
        "progress": f"Decision: {'volunteering' if volunteer else 'declining'}. Reason: {reason}",
    })

    log.info(
        "assign_opportunity.completed task_id=%s session_id=%s item_id=%s volunteer=%s",
        task.task_id, session_id, item_id, volunteer,
    )

    own_id = _own_participant_id(task.session_ctx)
    if own_id and session_id != "<no-session>":
        if volunteer:
            comment = f"I'd like to take \"{item_title}\" — {reason}"
        else:
            comment = f"I'll pass on \"{item_title}\" — {reason}"
        asyncio.create_task(_post_agent_message(session_id, own_id, comment))

    await queue.put({
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {"volunteer": volunteer, "reason": reason},
    })


# ── LLM call dispatcher ───────────────────────────────────────────────────────


async def _call_llm(system_prompt: str, user_prompt: str) -> str:
    if LLM_PROVIDER == "anthropic":
        return await _call_anthropic(system_prompt, user_prompt)
    return await _call_openai(system_prompt, user_prompt)


async def _call_openai(system_prompt: str, user_prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 512,
    }
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def _call_anthropic(system_prompt: str, user_prompt: str) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 512,
        "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_prompt}],
    }
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "prompt-caching-2024-07-31",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]


# ── Response parsers (AC4) ────────────────────────────────────────────────────


def _parse_votes(raw: str, expected_ids: list[str]) -> dict[str, str]:
    """Extract {item_id: priority} from LLM output; ignore extra keys."""
    valid_priorities = {"HIGH", "MEDIUM", "LOW"}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found")
        obj = json.loads(raw[start:end])
        if not isinstance(obj, dict):
            raise ValueError("Parsed JSON is not a dict")
        result: dict[str, str] = {}
        for item_id in expected_ids:
            val = obj.get(item_id, "")
            if isinstance(val, str) and val.upper() in valid_priorities:
                result[item_id] = val.upper()
        return result
    except Exception as exc:
        log.warning("_parse_votes.failed exc=%s raw=%r", exc, raw[:200])
        return {}


def _parse_volunteer(raw: str) -> dict[str, Any]:
    """Extract {volunteer: bool, reason: str} from LLM output."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found")
        obj = json.loads(raw[start:end])
        if not isinstance(obj, dict):
            raise ValueError("Parsed JSON is not a dict")
        return {
            "volunteer": bool(obj.get("volunteer", False)),
            "reason": str(obj.get("reason", "")),
        }
    except Exception as exc:
        log.warning("_parse_volunteer.failed exc=%s raw=%r", exc, raw[:200])
        return {"volunteer": False, "reason": f"Parse error: {exc}"}
