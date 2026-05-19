"""LLM-Backed PRODUCT_OWNER A2A Remote Agent (US-24).

Hosts a compliant A2A HTTP server whose backlog is generated dynamically by
an LLM from the session's sprint_goal.  All task handling is stateless —
session state arrives exclusively via session_ctx per AC4.

Supported task types
--------------------
session_invite          -> auto-joins the session then ACKs
session_ready           -> ACK
present_backlog         -> async (202 + SSE): calls LLM, streams thoughts, returns items
vote                    -> sync: calls LLM to rank items against sprint_goal
confirm                 -> sync: confirms when selected_items is non-empty
acknowledge_assignment  -> ACK
sprint_backlog          -> ACK

LLM provider is selected via env var LLM_PROVIDER (openai | anthropic).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

# ── Configuration ─────────────────────────────────────────────────────────────

AGENT_NAME = os.environ.get("AGENT_NAME", "llm-po-agent")
AGENT_PUBLIC_URL = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:8011")
PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://platform:8000")

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))

_AUTH_SCHEME = "none"

log = logging.getLogger(AGENT_NAME)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title=f"{AGENT_NAME} (LLM-Backed A2A Remote Agent)")

# ── In-flight SSE queues (per task_id; cleared after stream ends) ─────────────

_streams: dict[str, asyncio.Queue[dict[str, Any]]] = {}

# ── Pydantic models ───────────────────────────────────────────────────────────


class Task(BaseModel):
    task_id: str
    task_type: str
    session_ctx: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class BacklogItem(BaseModel):
    item_id: str
    title: str
    description: str
    priority: str
    story_points: int | None = None
    labels: list[str] = []
    dependencies: list[str] = []

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in ("HIGH", "MEDIUM", "LOW"):
            raise ValueError(f"invalid priority: {v!r}")
        return v

    @field_validator("story_points", mode="before")
    @classmethod
    def coerce_story_points(cls, v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None


# ── Agent Card ────────────────────────────────────────────────────────────────


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return {
        "name": AGENT_NAME,
        "description": (
            "LLM-backed Product Owner agent. Dynamically generates a realistic backlog "
            "from a sprint_goal and votes intelligently using LLM reasoning."
        ),
        "role": "PRODUCT_OWNER",
        "capabilities": {
            "can_provide_backlog": True,
            "can_vote": True,
            "can_volunteer": False,
            "streams_thoughts": True,
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
    for p in (session_ctx.get("participants") or []):
        if p.get("name") == AGENT_NAME:
            return p.get("participant_id")
    return None


# ── Task endpoint ─────────────────────────────────────────────────────────────


@app.post("/a2a/tasks")
async def receive_task(task: Task, request: Request, response: Response) -> dict:
    _check_auth(request)
    session_id = task.session_ctx.get("session_id", "<no-session>")
    log.info(
        "task.received session_id=%s task_id=%s task_type=%s",
        session_id, task.task_id, task.task_type,
    )

    if task.task_type == "present_backlog":
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        _streams[task.task_id] = queue
        asyncio.create_task(_run_present_backlog(task, queue))
        response.status_code = 202
        return {"task_id": task.task_id, "status": "working"}

    if task.task_type == "session_invite":
        asyncio.create_task(_auto_join(task))
        return {"task_id": task.task_id, "status": "completed", "artifact": {"ack": True}}

    if task.task_type in ("session_ready", "session_aborted", "acknowledge_assignment", "sprint_backlog"):
        return {"task_id": task.task_id, "status": "completed", "artifact": {"ack": True}}

    if task.task_type == "vote":
        return await _handle_vote(task)

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
        log.warning("auto_join: could not resolve own participant_id for agent %s", AGENT_NAME)
        return
    session_id = task.session_ctx.get("session_id")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{PLATFORM_URL}/sessions/{session_id}/join",
                json={"participant_id": own_id},
            )
            log.info("auto_join session_id=%s status=%d", session_id, resp.status_code)
        except Exception as exc:
            log.warning("auto_join failed session_id=%s exc=%s", session_id, exc)
            return

    sprint_goal = task.session_ctx.get("sprint_goal", "")
    intro = (
        f"Hi team, I'm {AGENT_NAME}, your Product Owner for this session. "
        f"Our sprint goal is: \"{sprint_goal}\". "
        "I'll be presenting the backlog shortly — feel free to ask questions as we go."
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


# ── present_backlog (async SSE) ───────────────────────────────────────────────


async def _run_present_backlog(task: Task, queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Generate backlog via LLM, streaming thoughts along the way (AC1, AC2)."""
    session_id = task.session_ctx.get("session_id", "<no-session>")
    sprint_goal = task.session_ctx.get("sprint_goal", "")

    async def emit(status: str, *, progress: str | None = None, artifact: dict | None = None) -> None:
        event: dict[str, Any] = {"task_id": task.task_id, "status": status}
        if progress is not None:
            event["progress"] = progress
        if artifact is not None:
            event["artifact"] = artifact
        await queue.put(event)

    try:
        await emit("working", progress=f"Analysing sprint goal: {sprint_goal!r}")
        await emit("working", progress="Calling LLM to generate backlog items...")

        raw_json = await _llm_generate_backlog(sprint_goal, session_id, task.task_id)

        await emit("working", progress="Validating and formatting backlog items...")

        backlog = _parse_and_validate_backlog(raw_json, sprint_goal)

        log.info(
            "present_backlog.done session_id=%s task_id=%s items=%d",
            session_id, task.task_id, len(backlog),
        )

        own_id = _own_participant_id(task.session_ctx)
        if own_id and session_id != "<no-session>":
            high_count = sum(1 for item in backlog if item.get("priority") == "HIGH")
            total_sp = sum(item.get("story_points") or 0 for item in backlog)
            comment = (
                f"I've prepared {len(backlog)} backlog items ({high_count} high-priority, "
                f"{total_sp} story points total). Let's vote on priorities — "
                "feel free to ask me about any item's rationale."
            )
            asyncio.create_task(_post_agent_message(session_id, own_id, comment))

        await emit("completed", artifact={"backlog": backlog})

    except Exception as exc:
        log.exception(
            "present_backlog.failed session_id=%s task_id=%s exc=%s",
            session_id, task.task_id, exc,
        )
        await emit("failed", artifact={"error": str(exc)})


# ── vote (sync with LLM) ──────────────────────────────────────────────────────


async def _handle_vote(task: Task) -> dict:
    """Cast votes using LLM reasoning aligned with the sprint goal (AC3)."""
    session_id = task.session_ctx.get("session_id", "<no-session>")
    sprint_goal = task.session_ctx.get("sprint_goal", "")
    items: list[str] = task.payload.get("items", [])
    backlog_items: list[dict] = task.session_ctx.get("backlog_items") or []
    human_messages: list[dict] = task.session_ctx.get("human_messages") or []

    if not items:
        return {"task_id": task.task_id, "status": "completed", "artifact": {"votes": {}}}

    try:
        raw_json = await _llm_vote(sprint_goal, items, backlog_items, human_messages, session_id, task.task_id)
        votes = _parse_and_validate_votes(raw_json, items)
    except Exception as exc:
        log.warning(
            "vote.llm_failed session_id=%s task_id=%s exc=%s -- falling back to priority-mirror",
            session_id, task.task_id, exc,
        )
        priority_map = {
            item["item_id"]: item.get("priority", "MEDIUM")
            for item in backlog_items
            if "item_id" in item
        }
        votes = {iid: priority_map.get(iid, "MEDIUM") for iid in items}

    log.info("vote.done session_id=%s task_id=%s votes=%s", session_id, task.task_id, votes)

    own_id = _own_participant_id(task.session_ctx)
    if own_id and session_id != "<no-session>":
        high_items = [iid for iid, p in votes.items() if p == "HIGH"]
        if high_items:
            item_lookup = {item["item_id"]: item for item in backlog_items if "item_id" in item}
            titles = [item_lookup.get(iid, {}).get("title", iid) for iid in high_items[:3]]
            comment = (
                "From a product strategy perspective, the items I'm prioritising HIGH are: "
                + ", ".join(f'"{t}"' for t in titles)
                + ("." if len(high_items) <= 3 else f" (and {len(high_items) - 3} more).")
                + " These best advance our sprint goal."
            )
            asyncio.create_task(_post_agent_message(session_id, own_id, comment))

    return {"task_id": task.task_id, "status": "completed", "artifact": {"votes": votes}}


# ── human_message (sync) ─────────────────────────────────────────────────────


async def _handle_human_message(task: Task) -> dict:
    sender_name = task.payload.get("sender_name", "a participant")
    content = task.payload.get("content", "")
    log.info("human_message.received from=%s content=%r", sender_name, content[:120])

    system_prompt = (
        "You are an experienced Product Owner participating in an agile sprint planning session. "
        "Reply concisely and in character to the human participant's message. "
        "Be helpful, strategic, and professional. Keep your reply to 1-2 sentences."
    )
    user_prompt = (
        f"Sprint goal: {task.session_ctx.get('sprint_goal', '')}\n\n"
        f"{sender_name} says: {content}\n\n"
        "Reply in character as the Product Owner."
    )

    reply = f"Thanks {sender_name}, noted."
    try:
        reply = await asyncio.wait_for(_llm_call(system_prompt, user_prompt), timeout=8.0)
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
        "You are an experienced Product Owner in an agile sprint planning session. "
        "A participant has @mentioned you in the team chat. "
        "Reply concisely and in character (1-3 sentences). "
        "Do not @-mention other participants in your reply."
    )
    user_prompt = (
        f"Sprint goal: {task.session_ctx.get('sprint_goal', '')}\n"
        f"Participants: {participant_summary}\n\n"
        f"Recent conversation:\n{history or '(none yet)'}\n\n"
        f"{sender_name} says to you: {content}\n\n"
        "Reply in character as the Product Owner."
    )

    reply = f"Thanks {sender_name}, good point."
    try:
        reply = await asyncio.wait_for(_llm_call(system_prompt, user_prompt), timeout=9.0)
    except Exception as exc:
        log.warning("direct_message.llm_failed exc=%s", exc)

    own_id = _own_participant_id(task.session_ctx)
    if own_id and session_id != "<no-session>":
        asyncio.create_task(_post_agent_message(session_id, own_id, reply))

    return {"task_id": task.task_id, "status": "completed", "artifact": {"ack": True}}


# ── confirm (sync) ────────────────────────────────────────────────────────────


def _handle_confirm(task: Task) -> dict:
    selected_items = task.session_ctx.get("selected_items")
    confirmed = bool(selected_items)
    return {
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {"confirmed": confirmed},
    }


# ── LLM helpers ───────────────────────────────────────────────────────────────

_BACKLOG_SYSTEM_PROMPT = """\
You are an experienced Product Owner participating in an Agile sprint planning session.
Your job is to generate a realistic, diverse sprint backlog based on the sprint goal provided.

Rules:
- Generate between 10 and 15 backlog items.
- Each item must have: item_id (e.g. "LLM-PO-1"), title, description, priority (HIGH|MEDIUM|LOW),
  story_points (integer 1-13), labels (list of strings), dependencies (list of item_ids or empty).
- Items must be directly relevant to the sprint_goal.
- Mix priorities realistically: roughly 30% HIGH, 50% MEDIUM, 20% LOW.
- Use Fibonacci-ish story points: 1, 2, 3, 5, 8, 13.
- Output ONLY a valid JSON array of objects. No markdown fences, no commentary.

Example item:
{"item_id": "LLM-PO-1", "title": "...", "description": "...", "priority": "HIGH",
 "story_points": 5, "labels": ["backend"], "dependencies": []}
"""

_VOTE_SYSTEM_PROMPT = """\
You are an experienced Product Owner evaluating backlog items for an Agile sprint.
Your job is to assign a priority vote (HIGH, MEDIUM, or LOW) to each backlog item
based on how well it aligns with the sprint goal.

Rules:
- Evaluate each item_id provided in the list.
- Return ONLY a valid JSON object mapping item_id to priority string ("HIGH", "MEDIUM", or "LOW").
- Base your decisions on strategic alignment with the sprint_goal.
- Do not output markdown fences or commentary -- only valid JSON.

Example output:
{"ITEM-1": "HIGH", "ITEM-2": "LOW", "ITEM-3": "MEDIUM"}
"""


async def _llm_generate_backlog(sprint_goal: str, session_id: str, task_id: str) -> str:
    user_message = (
        f"Sprint Goal: {sprint_goal}\n\n"
        "Generate a sprint backlog as a JSON array of 10-15 items. Output only JSON."
    )
    log.info(
        "llm.backlog.call provider=%s session_id=%s task_id=%s",
        LLM_PROVIDER, session_id, task_id,
    )
    return await _llm_call(_BACKLOG_SYSTEM_PROMPT, user_message)


async def _llm_vote(
    sprint_goal: str,
    item_ids: list[str],
    backlog_items: list[dict],
    human_messages: list[dict],
    session_id: str,
    task_id: str,
) -> str:
    item_summaries = []
    item_lookup = {item["item_id"]: item for item in backlog_items if "item_id" in item}
    for iid in item_ids:
        item = item_lookup.get(iid)
        if item:
            item_summaries.append(
                f'- {iid}: {item.get("title", "")} -- {item.get("description", "")[:80]}'
            )
        else:
            item_summaries.append(f"- {iid}: (no details available)")

    user_message = (
        f"Sprint Goal: {sprint_goal}\n\n"
        f"Backlog items to evaluate:\n" + "\n".join(item_summaries) + "\n\n"
        "Return a JSON object mapping each item_id to HIGH, MEDIUM, or LOW. Output only JSON."
    )

    if human_messages:
        notes = "\n".join(
            f"- {m.get('sender_name', 'participant')}: {m.get('content', '')}"
            for m in human_messages[-5:]
        )
        user_message += f"\n\nAdditional context from session participants:\n{notes}"
    log.info(
        "llm.vote.call provider=%s session_id=%s task_id=%s items=%d",
        LLM_PROVIDER, session_id, task_id, len(item_ids),
    )
    return await _llm_call(_VOTE_SYSTEM_PROMPT, user_message)


async def _llm_call(system_prompt: str, user_message: str) -> str:
    if LLM_PROVIDER == "anthropic":
        return await _call_anthropic(system_prompt, user_message)
    return await _call_openai(system_prompt, user_message)


async def _call_openai(system_prompt: str, user_message: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    needs_array = "JSON array" in user_message
    payload: dict[str, Any] = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    if not needs_array:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_anthropic(system_prompt: str, user_message: str) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_message}],
    }
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "prompt-caching-2024-07-31",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


# ── Output parsers and validators ─────────────────────────────────────────────


def _extract_json(text: str) -> str:
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()
    if text.startswith(("[", "{")):
        return text
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        if start != -1:
            depth = 0
            for i, ch in enumerate(text[start:], start=start):
                if ch == start_char:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                    if depth == 0:
                        return text[start : i + 1]
    return text


def _parse_and_validate_backlog(raw: str, sprint_goal: str) -> list[dict]:
    """Parse LLM output into validated BacklogItem dicts (AC5)."""
    try:
        extracted = _extract_json(raw)
        parsed = json.loads(extracted)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("backlog.parse_failed exc=%s raw_snippet=%r", exc, raw[:200])
        return _fallback_backlog(sprint_goal)

    if isinstance(parsed, dict):
        for key in ("backlog", "items", "backlog_items"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
        else:
            log.warning("backlog.unexpected_structure keys=%s", list(parsed.keys()))
            return _fallback_backlog(sprint_goal)

    if not isinstance(parsed, list):
        log.warning("backlog.not_a_list type=%s", type(parsed).__name__)
        return _fallback_backlog(sprint_goal)

    validated: list[dict] = []
    for i, raw_item in enumerate(parsed, start=1):
        if not isinstance(raw_item, dict):
            continue
        if not raw_item.get("item_id"):
            raw_item["item_id"] = f"LLM-PO-{i}"
        try:
            item = BacklogItem.model_validate(raw_item)
            validated.append(item.model_dump())
        except ValidationError as exc:
            log.warning("backlog.invalid_item item=%r err=%s", raw_item.get("item_id"), exc)

    if not validated:
        log.warning("backlog.no_valid_items -- using fallback")
        return _fallback_backlog(sprint_goal)

    return validated


def _parse_and_validate_votes(raw: str, item_ids: list[str]) -> dict[str, str]:
    """Parse LLM output into a validated votes dict (AC5)."""
    try:
        extracted = _extract_json(raw)
        parsed = json.loads(extracted)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("votes.parse_failed exc=%s raw_snippet=%r", exc, raw[:200])
        return {iid: "MEDIUM" for iid in item_ids}

    if not isinstance(parsed, dict):
        log.warning("votes.not_a_dict type=%s", type(parsed).__name__)
        return {iid: "MEDIUM" for iid in item_ids}

    valid_priorities = {"HIGH", "MEDIUM", "LOW"}
    votes: dict[str, str] = {}
    for iid in item_ids:
        raw_vote = str(parsed.get(iid, "MEDIUM")).upper().strip()
        votes[iid] = raw_vote if raw_vote in valid_priorities else "MEDIUM"

    return votes


def _fallback_backlog(sprint_goal: str) -> list[dict]:
    """Emergency fallback when LLM output is completely unparseable."""
    log.warning("backlog.using_fallback sprint_goal=%r", sprint_goal[:80])
    goal_slug = sprint_goal[:40].replace(" ", "-").lower() if sprint_goal else "task"
    return [
        {
            "item_id": "LLM-PO-FB-1",
            "title": f"Core feature for: {goal_slug}",
            "description": f"Implement the primary deliverable to achieve the sprint goal: {sprint_goal}",
            "priority": "HIGH",
            "story_points": 8,
            "labels": ["core"],
            "dependencies": [],
        },
        {
            "item_id": "LLM-PO-FB-2",
            "title": "Supporting infrastructure",
            "description": "Set up any supporting infrastructure or services required by the main feature.",
            "priority": "HIGH",
            "story_points": 5,
            "labels": ["infrastructure"],
            "dependencies": ["LLM-PO-FB-1"],
        },
        {
            "item_id": "LLM-PO-FB-3",
            "title": "Testing and QA",
            "description": "Write automated tests and perform QA for the sprint deliverables.",
            "priority": "MEDIUM",
            "story_points": 3,
            "labels": ["testing", "qa"],
            "dependencies": ["LLM-PO-FB-1"],
        },
        {
            "item_id": "LLM-PO-FB-4",
            "title": "Documentation",
            "description": "Update technical and user-facing documentation for the new feature.",
            "priority": "LOW",
            "story_points": 2,
            "labels": ["docs"],
            "dependencies": [],
        },
        {
            "item_id": "LLM-PO-FB-5",
            "title": "Deployment and release preparation",
            "description": "Prepare deployment scripts, configuration, and release notes.",
            "priority": "MEDIUM",
            "story_points": 3,
            "labels": ["devops", "release"],
            "dependencies": ["LLM-PO-FB-2"],
        },
    ]
