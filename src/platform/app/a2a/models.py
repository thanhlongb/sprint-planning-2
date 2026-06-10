from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskEnvelope(BaseModel):
    """Wire format for POST {agent_endpoint}/tasks (AC1)."""

    task_id: str
    task_type: str
    session_ctx: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskAck(BaseModel):
    """202 acknowledgement returned by an agent for an async task (AC3)."""

    task_id: str
    status: Literal["working"] = "working"


class TaskEvent(BaseModel):
    """One frame off the SSE stream (AC4)."""

    task_id: str
    status: TaskStatus
    progress: str | None = None
    artifact: dict[str, Any] | None = None
    error: str | None = None


class CommEvent(BaseModel):
    """A single inter-agent communication event for the US-26 comm feed.

    task_type values:
      - "task_request" | "task_response" | "thought"  (original US-26)
      - "your_turn"          — platform → participant: it's your turn (US-41)
      - "round_robin_started" — platform → all: discussion began (US-41)
      - "round_summary"      — platform → all: round completed (US-41)
      - "phase_started"      — platform → all: new phase active (US-36)
      - "discussion_update"  — platform → all: state change (US-32)
      - "assignment_proposal" — platform → all: auto-assignment done (US-31)
      - "add_item" | "remove_item" | "modify_item"  — recommendation actions
      - "volunteer" | "object" | "reassign"         — assignment actions
      - "advance" | "confirm_phase"                  — PO signals
    """

    event_type: str = "comm_event"
    comm_id: str
    session_id: str
    timestamp: str  # ISO-8601
    sender_id: str
    sender_name: str
    receiver_id: str | None = None
    receiver_name: str | None = None
    task_type: str
    message_kind: str
    content: dict[str, Any] | str


# ── Round-Robin Task Contracts (US-41) ─────────────────────────────────────────
#
# Platform → Participant A2A task: "your_turn"
#   payload: {
#       "round": int,              # 0-indexed round number
#       "context": "recommendation" | "assignment",
#       "allowed_actions": [...],  # e.g. ["add_item", "remove_item", "modify_item"]
#       "current_items": [...],    # full item dicts currently selected
#       "assignments": {...},      # item_id → participant_id (assignment context)
#       "discussion_so_far": [...],# messages from this round so far
#       "participants": [...],     # [{name, role, done}] for all participants
#   }
#
# Participant → Platform: turn response (returned as task artifact)
#   artifact: {
#       "message": str,            # free-text contribution (optional)
#       "actions": [               # structured actions (optional)
#           {
#               "type": "add_item" | "remove_item" | "modify_item"
#                      | "volunteer" | "object" | "reassign",
#               "item": {...},     # for add_item
#               "item_id": str,    # for remove_item/volunteer/object/reassign
#               "updates": {...},  # for modify_item
#               "to_participant_id": str,  # for reassign
#           }
#       ],
#       "done": bool,              # True = nothing more to add (consensus signal)
#   }
#
# Platform → All (comm bus broadcast): "round_summary"
#   content: {
#       "round": int,
#       "context": str,
#       "messages": [...],         # all turn responses from this round
#       "items": [...],            # current working items
#       "assignments": {...},
#       "consensus": {
#           "all_done": bool,
#           "state": {slot_id: bool}
#       },
#       "new_items_proposed": bool,
#   }
