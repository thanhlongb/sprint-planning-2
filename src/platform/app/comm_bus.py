"""US-26: publish inter-agent communication events to a per-session Redis channel."""

from __future__ import annotations

import logging

from app.a2a.models import CommEvent
from app.message_bus import bus

log = logging.getLogger(__name__)

_CHANNEL_PREFIX = "session:comm:"


async def publish_comm_event(event: CommEvent) -> None:
    channel = f"{_CHANNEL_PREFIX}{event.session_id}"
    try:
        await bus().publish(channel, event.model_dump_json())
    except Exception as exc:
        # Never let a publish failure break orchestration.
        log.warning("comm_bus.publish_failed channel=%s exc=%s", channel, exc)
