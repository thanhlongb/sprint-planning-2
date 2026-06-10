#!/usr/bin/env python3
"""US-38: End-to-End Test for sprint_planning_v2 workflow.

This script:
  1. Starts docker compose (platform + postgres + redis + agents) if not running
  2. Registers po-agent and dev-agent via POST /register
  3. Creates a session via POST /sessions with template=sprint_planning_v2
  4. Waits for session to become ACTIVE (agents auto-join)
  5. Injects a discussion message (add_item) via Redis comm bus so the
     recommendation phase produces recommendation_rounds >= 1
  6. Waits for the session to transition to COMPLETED
  7. Verifies all required outputs from the session context and sprint backlog

Usage:
    python3 test_v2_e2e.py        # start docker + run test + stop docker
    python3 test_v2_e2e.py --no-standup  # assume stack already running
    python3 test_v2_e2e.py --no-teardown # leave stack running after test
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from typing import Any

import httpx
import redis


# ── Configuration ─────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_DIR = os.path.join(PROJECT_ROOT, "src")
COMPOSE_FILE = os.path.join(COMPOSE_DIR, "docker-compose.yml")

PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://localhost:8000")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# These are the Docker-internal hostnames the *platform* uses to reach agents.
PO_AGENT_URL = os.environ.get("PO_AGENT_URL", "http://po-agent:8001")
DEV_AGENT_URL = os.environ.get("DEV_AGENT_URL", "http://dev-agent:8002")


# ── Health-check helpers ──────────────────────────────────────────────────────


def platform_healthy(timeout: float = 120.0) -> bool:
    """Poll GET /health until we get a 200 or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{PLATFORM_URL}/health", timeout=5)
            if r.status_code == 200:
                data = r.json()
                print(f"  Platform healthy: {data}")
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


# ── Docker compose helpers ────────────────────────────────────────────────────


def docker_up() -> None:
    """Bring up the full stack, building if necessary."""
    print("  Starting docker compose (this may take a minute)...")
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", "--build"],
        cwd=COMPOSE_DIR,
        check=True,
        capture_output=False,
    )
    print("  Docker compose started, waiting for platform...")
    if not platform_healthy():
        raise RuntimeError("Platform did not become healthy in time")


def docker_down() -> None:
    """Tear down the stack."""
    print("  Stopping docker compose...")
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"],
        cwd=COMPOSE_DIR,
        check=False,  # best-effort
        capture_output=False,
    )


# ── API helpers ───────────────────────────────────────────────────────────────


def register_agent(client: httpx.Client, agent_url: str) -> str:
    """POST /register and return participant_id. Retries on transient errors."""
    deadline = time.monotonic() + 30
    last_error = None
    while time.monotonic() < deadline:
        try:
            r = client.post(
                f"{PLATFORM_URL}/register",
                json={"agent_url": agent_url},
                timeout=10,
            )
            if r.status_code == 201:
                data = r.json()
                pid = data["participant_id"]
                print(f"  Registered {agent_url} → {pid}")
                return pid
            elif r.status_code == 422:
                # May be "already registered" or card not ready yet
                detail = r.json().get("detail", {})
                reason = detail.get("reason", "")
                if reason == "unreachable_url":
                    print(f"    Agent not reachable yet at {agent_url}, retrying...")
                    time.sleep(2)
                    continue
                raise RuntimeError(f"Register {agent_url} failed (422): {detail}")
            else:
                raise RuntimeError(f"Register {agent_url} failed ({r.status_code}): {r.text}")
        except httpx.RequestError as e:
            last_error = e
            time.sleep(2)
    raise RuntimeError(f"Register {agent_url} timed out: {last_error}")


def create_session(
    client: httpx.Client,
    po_pid: str,
    dev_pid: str,
) -> dict[str, Any]:
    """POST /sessions with v2 template and return the response dict."""
    r = client.post(
        f"{PLATFORM_URL}/sessions",
        json={
            "template": "sprint_planning_v2",
            "sprint_goal": "Ship OAuth + user profile",
            "participants": [
                {"participant_id": po_pid},
                {"participant_id": dev_pid},
            ],
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    print(f"  Session created: {data['session_id']} status={data['status']}")
    return data


def get_session(client: httpx.Client, session_id: str) -> dict[str, Any]:
    """GET /sessions/{id} and return the detail dict."""
    r = client.get(f"{PLATFORM_URL}/sessions/{session_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def wait_for_status(
    client: httpx.Client,
    session_id: str,
    target_status: str,
    timeout: float = 300.0,
    poll_interval: float = 2.0,
) -> dict[str, Any]:
    """Poll GET /sessions/{id} until status matches target or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session = get_session(client, session_id)
        status = session["status"]
        if status == target_status:
            print(f"  Session {session_id} → {target_status}")
            return session
        if status == "ABORTED":
            raise RuntimeError(f"Session aborted: {json.dumps(session, indent=2)}")
        print(f"    status={status}, waiting for {target_status}...")
        time.sleep(poll_interval)
    raise TimeoutError(f"Session did not reach '{target_status}' within {timeout}s")


# ── Redis comm-bus helpers ────────────────────────────────────────────────────


def publish_comm_event(
    r: redis.Redis,
    session_id: str,
    task_type: str,
    content: dict[str, Any] | str,
    sender_id: str = "test-runner",
    sender_name: str = "E2E Test",
) -> None:
    """Publish a CommEvent JSON message to the session's Redis comm channel."""
    channel = f"session:comm:{session_id}"
    event: dict[str, Any] = {
        "comm_id": str(uuid.uuid4()),
        "session_id": session_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "sender_id": sender_id,
        "sender_name": sender_name,
        "receiver_id": None,
        "receiver_name": None,
        "task_type": task_type,
        "message_kind": "discussion_action",
        "content": content,
    }
    payload = json.dumps(event)
    count = r.publish(channel, payload)
    print(f"  Published {task_type} → channel={channel} (subscribers={count})")


def inject_add_item(r: redis.Redis, session_id: str) -> None:
    """Add a new backlog item during the recommendation discussion phase."""
    publish_comm_event(
        r,
        session_id,
        task_type="add_item",
        content={
            "item": {
                "item_id": "E2E-ADD-1",
                "title": "E2E test item — two-factor auth",
                "description": "Add TOTP-based two-factor authentication.",
                "priority": "MEDIUM",
                "story_points": 5,
                "labels": ["auth", "security"],
                "dependencies": [],
            },
        },
    )


def inject_remove_item(r: redis.Redis, session_id: str, item_id: str) -> None:
    """Remove an item from the recommendation during discussion."""
    publish_comm_event(
        r,
        session_id,
        task_type="remove_item",
        content={"item_id": item_id},
    )


# ── Verification helpers ──────────────────────────────────────────────────────


def assert_condition(condition: bool, message: str) -> None:
    """Simple assertion with a prefix for readability."""
    if condition:
        print(f"  ✅ {message}")
    else:
        print(f"  ❌ {message}")
        raise AssertionError(message)


def verify_session(session: dict[str, Any]) -> None:
    """Run all assertions against the completed session state."""
    ctx = session.get("context") or {}
    participants = session.get("participants", [])

    participant_names = {p.get("name") for p in participants}
    print(f"\n  Participants seen: {participant_names}")

    # AC3: backlog_items populated (recommendation phase ran)
    backlog_items = ctx.get("backlog_items", [])
    assert_condition(
        len(backlog_items) > 0,
        f"backlog_items populated ({len(backlog_items)} items)",
    )

    # AC3: selected_items populated
    selected_items = ctx.get("selected_items", [])
    assert_condition(
        len(selected_items) > 0,
        f"selected_items populated ({len(selected_items)} item IDs)",
    )
    print(f"    Selected item IDs: {selected_items}")

    # AC5: recommendation_rounds >= 1
    rec_rounds = ctx.get("recommendation_rounds")
    assert_condition(
        isinstance(rec_rounds, int) and rec_rounds >= 1,
        f"recommendation_rounds >= 1 (got {rec_rounds})",
    )

    # AC5: initial_recommendation snapshotted
    initial_rec = ctx.get("initial_recommendation")
    assert_condition(
        isinstance(initial_rec, list) and len(initial_rec) > 0,
        f"initial_recommendation snapshotted ({len(initial_rec or [])} items)",
    )

    # AC6: assignments populated
    assignments = ctx.get("assignments", {})
    assert_condition(
        len(assignments) > 0,
        f"assignments populated ({len(assignments)} item→participant pairs)",
    )
    print(f"    Assignments: {json.dumps(assignments)}")

    # AC8: session COMPLETED
    assert_condition(
        session["status"] == "COMPLETED",
        f"session status is COMPLETED (got {session['status']})",
    )

    # AC9/10: convergence_metrics present in context
    convergence_keys = {
        "initial_recommendation",
        "recommendation_rounds",
        "assignment_rounds",
        "retention_pct",
    }
    present_keys = convergence_keys & set(ctx.keys())
    assert_condition(
        len(present_keys) >= 3,
        f"convergence_metrics present (keys: {sorted(present_keys)})",
    )

    # AC10: retention_pct is a float between 0.0 and 1.0
    retention_pct = ctx.get("retention_pct")
    assert_condition(
        isinstance(retention_pct, (int, float)) and 0.0 <= float(retention_pct) <= 1.0,
        f"retention_pct is float in [0.0, 1.0] (got {retention_pct})",
    )

    # Verify the sprint_goal matches what we submitted
    assert_condition(
        session.get("sprint_goal") == "Ship OAuth + user profile",
        f"sprint_goal preserved: {session.get('sprint_goal')}",
    )

    # Verify template
    assert_condition(
        session.get("template") == "sprint_planning_v2",
        f"template is sprint_planning_v2",
    )

    print(f"\n  All assertions passed! 🎉")


# ── Main test flow ───────────────────────────────────────────────────────────


def run_e2e_test(standup: bool = True, teardown: bool = True) -> bool:
    """Run the full E2E test. Returns True on success."""
    print("=" * 60)
    print("US-38: E2E Test for sprint_planning_v2 Workflow")
    print("=" * 60)

    try:
        # ── 1. Start docker compose ────────────────────────────────────────
        if standup:
            print("\n[1/7] Starting docker stack...")
            docker_up()
        else:
            print("\n[1/7] Skipped (--no-standup), assuming stack is running...")
            if not platform_healthy():
                raise RuntimeError("Platform not reachable. Is the stack running?")

        # ── 2. Register agents ────────────────────────────────────────────
        print("\n[2/7] Registering agents...")
        with httpx.Client() as client:
            po_pid = register_agent(client, PO_AGENT_URL)
            dev_pid = register_agent(client, DEV_AGENT_URL)

        # ── 3. Create session ─────────────────────────────────────────────
        print("\n[3/7] Creating v2 session...")
        with httpx.Client() as client:
            session_data = create_session(client, po_pid, dev_pid)
            session_id = session_data["session_id"]

        # ── 4. Wait for ACTIVE ────────────────────────────────────────────
        print("\n[4/7] Waiting for session to become ACTIVE...")
        with httpx.Client() as client:
            active = wait_for_status(client, session_id, "ACTIVE", timeout=60)
            assert_condition(
                len(active.get("participants", [])) >= 2,
                f"At least 2 participants joined ({len(active.get('participants', []))})",
            )

        # ── 5. Round-robin agents auto-respond to your_turn ──────────────────
        # The platform now sends your_turn tasks sequentially to each agent.
        # Reference agents handle your_turn and return done=True after round 0,
        # so consensus is reached quickly.  No manual Redis injection needed.
        print("\n[5/7] Round-robin discussion in progress (agents responding to your_turn)...")

        # ── 6. Wait for COMPLETED ─────────────────────────────────────────
        print("\n[6/7] Waiting for session to complete...")
        with httpx.Client() as client:
            # Round-robin: each round sends your_turn to 2 agents (PO + DEV),
            # each with 30s timeout. Reference agents reply immediately and
            # mark done=True after round 0, so consensus is fast (~5-10s per
            # discussion phase). 300s timeout is generous.
            completed = wait_for_status(client, session_id, "COMPLETED", timeout=300)

        # ── 7. Verify outputs ─────────────────────────────────────────────
        print("\n[7/7] Verifying session outputs...")
        verify_session(completed)

        return True

    except Exception as e:
        print(f"\n❌ E2E test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if teardown:
            print("\n[Tear down] Stopping docker stack...")
            docker_down()
        else:
            print("\n[Tear down] Skipped (--no-teardown), stack left running.")


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="US-38 E2E test for sprint_planning_v2 workflow"
    )
    parser.add_argument(
        "--no-standup",
        action="store_true",
        help="Assume docker stack is already running; skip docker compose up",
    )
    parser.add_argument(
        "--no-teardown",
        action="store_true",
        help="Leave docker stack running after the test",
    )
    args = parser.parse_args()

    success = run_e2e_test(standup=not args.no_standup, teardown=not args.no_teardown)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
