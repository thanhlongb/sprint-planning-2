"""A2A client used by the platform to drive Remote Agents.

Implements US-01: synchronous + asynchronous task dispatch, SSE subscription,
auth-scheme handling, per-task timeout, and structured logging keyed by
`session_id` / `task_id`.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from app.a2a.models import TaskEnvelope, TaskEvent, TaskStatus
from app.logging_setup import task_logger


class A2AError(RuntimeError):
    """Raised for protocol-level failures (bad HTTP status, malformed SSE, etc.)."""


@dataclass(slots=True)
class TaskResult:
    task_id: str
    status: TaskStatus
    artifact: dict[str, Any] | None = None
    error: str | None = None
    progress: list[str] | None = None

    @property
    def ok(self) -> bool:
        return self.status is TaskStatus.COMPLETED


class A2AClient:
    """Thin A2A client. One instance per platform process is fine."""

    def __init__(self, *, default_timeout_seconds: float = 30.0) -> None:
        self._default_timeout = default_timeout_seconds

    async def send_task(
        self,
        *,
        endpoint: str,
        task_type: str,
        session_ctx: dict[str, Any],
        payload: dict[str, Any] | None = None,
        auth: dict[str, Any] | None = None,
        bearer_token: str | None = None,
        duration_limit_seconds: float | None = None,
        task_id: str | None = None,
    ) -> TaskResult:
        """Send a single A2A task. Handles sync (200) and async (202 + SSE) paths."""

        task_id = task_id or str(uuid4())
        session_id = session_ctx.get("session_id", "<no-session>")
        log = task_logger(session_id=session_id, task_id=task_id)

        envelope = TaskEnvelope(
            task_id=task_id,
            task_type=task_type,
            session_ctx=session_ctx,
            payload=payload or {},
        )
        headers = self._auth_headers(auth, bearer_token)
        timeout = duration_limit_seconds or self._default_timeout

        url = self._join(endpoint, "tasks")
        log.info(
            "a2a.task.send url=%s task_type=%s timeout=%.1fs", url, task_type, timeout
        )

        try:
            return await asyncio.wait_for(
                self._run(envelope, endpoint, url, headers, log),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            log.warning("a2a.task.timeout after=%.1fs", timeout)
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=f"timeout after {timeout:.1f}s",
            )

    async def _run(
        self,
        envelope: TaskEnvelope,
        endpoint: str,
        url: str,
        headers: dict[str, str],
        log,
    ) -> TaskResult:
        async with httpx.AsyncClient(timeout=None) as client:
            resp = await client.post(
                url, json=envelope.model_dump(), headers=headers
            )
            log.info("a2a.task.http_response status=%d", resp.status_code)

            if resp.status_code == 200:
                # AC2: synchronous completed path.
                body = resp.json()
                event = self._event_from_body(envelope.task_id, body)
                log.info(
                    "a2a.task.sync_completed status=%s", event.status.value
                )
                return TaskResult(
                    task_id=event.task_id,
                    status=event.status,
                    artifact=event.artifact,
                    error=event.error,
                )

            if resp.status_code == 202:
                # AC3: async — open SSE stream.
                ack = resp.json()
                log.info("a2a.task.async_accepted ack=%s", ack)
                return await self._consume_sse(
                    client=client,
                    endpoint=endpoint,
                    task_id=envelope.task_id,
                    headers=headers,
                    log=log,
                )

            raise A2AError(
                f"agent returned unexpected status {resp.status_code}: "
                f"{resp.text[:200]}"
            )

    async def _consume_sse(
        self,
        *,
        client: httpx.AsyncClient,
        endpoint: str,
        task_id: str,
        headers: dict[str, str],
        log,
    ) -> TaskResult:
        sse_url = self._join(endpoint, f"tasks/{task_id}")
        sse_headers = {**headers, "Accept": "text/event-stream"}
        progress: list[str] = []

        async with client.stream("GET", sse_url, headers=sse_headers) as resp:
            if resp.status_code != 200:
                raise A2AError(
                    f"SSE subscribe failed: HTTP {resp.status_code}"
                )

            async for raw in resp.aiter_lines():
                if not raw or not raw.startswith("data:"):
                    continue
                data = raw[len("data:") :].strip()
                if not data:
                    continue
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise A2AError(f"malformed SSE frame: {data!r}") from exc

                event = self._event_from_body(task_id, parsed)
                log.info(
                    "a2a.task.sse_event status=%s progress=%s",
                    event.status.value,
                    event.progress,
                )

                if event.status is TaskStatus.WORKING:
                    if event.progress:
                        progress.append(event.progress)
                    continue

                # Terminal completed / failed (AC4).
                return TaskResult(
                    task_id=event.task_id,
                    status=event.status,
                    artifact=event.artifact,
                    error=event.error,
                    progress=progress or None,
                )

        raise A2AError("SSE stream closed before terminal event")

    @staticmethod
    def _event_from_body(task_id: str, body: dict[str, Any]) -> TaskEvent:
        # Agents echo the task_id; fall back to the one we sent so a forgetful
        # agent still produces a coherent event.
        body.setdefault("task_id", task_id)
        return TaskEvent.model_validate(body)

    @staticmethod
    def _auth_headers(
        auth: dict[str, Any] | None, bearer_token: str | None
    ) -> dict[str, str]:
        """AC5: apply the agent's declared auth scheme."""
        if not auth:
            return {}
        scheme = (auth.get("scheme") or "").lower()
        if scheme in ("", "none"):
            return {}
        if scheme == "bearer":
            token = bearer_token or auth.get("token")
            if not token:
                raise A2AError(
                    "agent declared bearer auth but no token configured"
                )
            return {"Authorization": f"Bearer {token}"}
        raise A2AError(f"unsupported auth scheme: {scheme}")

    @staticmethod
    def _join(base: str, suffix: str) -> str:
        return f"{base.rstrip('/')}/{suffix.lstrip('/')}"
