"""POST /register — Participant Registry (US-02).

Fetches the agent's Agent Card from {agent_url}/.well-known/agent.json,
validates required fields and role-capability contracts, then persists the
participant (endpoint, role, validated capabilities only — not the full card).
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Participant

router = APIRouter()

# ── Role / capability contract ────────────────────────────────────────────────

VALID_ROLES = {"PRODUCT_OWNER", "DEVELOPER", "ARCHITECT", "SCRUM_MASTER"}

# Capabilities every role must declare (any boolean value).
_UNIVERSAL_CAPS: set[str] = {"can_vote"}

# Capabilities each role must declare as True specifically.
_ROLE_REQUIRED_TRUE: dict[str, set[str]] = {
    "PRODUCT_OWNER": {"can_provide_backlog"},
}

# Capabilities each role must at least declare (value unrestricted).
_ROLE_REQUIRED_DECLARED: dict[str, set[str]] = {
    "DEVELOPER": {"can_volunteer"},
    "ARCHITECT": {"can_volunteer"},
}

VALID_AUTH_SCHEMES = {"none", "bearer"}

# ── Validation helpers ────────────────────────────────────────────────────────

def _validate_card(card: dict[str, Any]) -> None:
    """Raise HTTPException(422) with machine-readable reason on any violation."""

    # AC2: required top-level fields.
    for field in ("name", "role", "capabilities", "endpoint", "auth"):
        if field not in card:
            raise HTTPException(
                422,
                detail={"reason": "missing_field", "field": field},
            )

    role: str = card["role"]
    if role not in VALID_ROLES:
        raise HTTPException(
            422,
            detail={"reason": "invalid_role", "role": role, "valid_roles": sorted(VALID_ROLES)},
        )

    auth = card["auth"]
    if not isinstance(auth, dict) or "scheme" not in auth:
        raise HTTPException(
            422,
            detail={"reason": "missing_field", "field": "auth.scheme"},
        )
    scheme = auth["scheme"].lower()
    if scheme not in VALID_AUTH_SCHEMES:
        raise HTTPException(
            422,
            detail={"reason": "unsupported_auth_scheme", "scheme": scheme},
        )

    caps: dict[str, Any] = card["capabilities"]
    if not isinstance(caps, dict):
        raise HTTPException(
            422,
            detail={"reason": "missing_field", "field": "capabilities"},
        )

    # AC3: universal capabilities all roles must declare.
    for cap in _UNIVERSAL_CAPS:
        if cap not in caps:
            raise HTTPException(
                422,
                detail={"reason": "missing_capability", "capability": cap, "role": role},
            )

    # AC3: role-specific capabilities that must be True.
    for cap in _ROLE_REQUIRED_TRUE.get(role, set()):
        if not caps.get(cap):
            raise HTTPException(
                422,
                detail={
                    "reason": "role_capability_mismatch",
                    "capability": cap,
                    "required_value": True,
                    "declared_value": caps.get(cap),
                    "role": role,
                },
            )

    # AC3: role-specific capabilities that must be declared (value unrestricted).
    for cap in _ROLE_REQUIRED_DECLARED.get(role, set()):
        if cap not in caps:
            raise HTTPException(
                422,
                detail={"reason": "missing_capability", "capability": cap, "role": role},
            )


# ── Request / response models ─────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    agent_url: HttpUrl


class RegisterResponse(BaseModel):
    participant_id: str
    status: str = "REGISTERED"


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("", response_model=RegisterResponse, status_code=201)
async def register(
    req: RegisterRequest, db: AsyncSession = Depends(get_session)
) -> RegisterResponse:
    # AC1: fetch the Agent Card from the well-known URL.
    card_url = f"{str(req.agent_url).rstrip('/')}/.well-known/agent.json"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(card_url)
    except httpx.RequestError as exc:
        raise HTTPException(
            422,
            detail={"reason": "unreachable_url", "url": card_url, "error": str(exc)},
        )

    if resp.status_code != 200:
        raise HTTPException(
            422,
            detail={
                "reason": "unreachable_url",
                "url": card_url,
                "http_status": resp.status_code,
            },
        )

    card = resp.json()

    # AC2 + AC3: validate the card.
    _validate_card(card)

    endpoint: str = card["endpoint"]
    role: str = card["role"]
    capabilities: dict = card["capabilities"]

    # US-34: extract capacity from Agent Card, default to 0/empty (AC6).
    capacity = capabilities.get("capacity", {})
    if not isinstance(capacity, dict):
        capacity = {}
    capacity.setdefault("story_points", 0)
    capacity.setdefault("specialties", [])
    capabilities["capacity"] = capacity

    # AC7: idempotent — if the same endpoint is already registered, return the
    # existing participant_id rather than creating a duplicate.
    existing = await db.execute(select(Participant).where(Participant.endpoint == endpoint))
    participant = existing.scalar_one_or_none()

    if participant is None:
        participant = Participant(
            name=card["name"],
            role=role,
            endpoint=endpoint,
            capabilities=capabilities,
        )
        db.add(participant)
        await db.commit()
        await db.refresh(participant)

    # AC4: return participant_id + status.
    return RegisterResponse(participant_id=participant.id)
