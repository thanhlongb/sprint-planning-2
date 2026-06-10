"""Shared LLM client for agent use.

Unified interface for calling OpenAI and Anthropic APIs.
Credentials are read from environment variables.

Usage:
    from llm_agent.llm_client import complete

    reply = complete("Hello!")
    print(reply)

Async usage (preferred for FastAPI agents):
    from llm_agent.llm_client import complete_async

    reply = await complete_async("Hello!")
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ── Configuration (from environment) ──────────────────────────────────────────

LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "anthropic").lower()
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
LLM_TIMEOUT_SECONDS: float = float(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))

# ── Public API ────────────────────────────────────────────────────────────────


def complete(prompt: str, *, system_prompt: str = "You are a helpful assistant.") -> str:
    """Synchronous LLM completion. Returns text response.

    Args:
        prompt: The user message to send.
        system_prompt: Optional system prompt (default: helpful assistant).

    Returns:
        The model's text response.

    Raises:
        RuntimeError: if required API key is missing.
        httpx.HTTPStatusError: on non-2xx API response.
        httpx.RequestError: on network/timeout errors.
    """
    return asyncio.run(complete_async(prompt, system_prompt=system_prompt))


async def complete_async(
    prompt: str,
    *,
    system_prompt: str = "You are a helpful assistant.",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Async LLM completion — the primary interface for FastAPI agents.

    Args:
        prompt: The user message to send.
        system_prompt: Optional system prompt (default: helpful assistant).
        temperature: Model temperature. Defaults: openai=0.7, anthropic=N/A.
        max_tokens: Max tokens in response. Defaults: openai=4096, anthropic=4096.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: if required API key is missing.
        httpx.HTTPStatusError: on non-2xx API response.
        httpx.RequestError: on network/timeout errors.
    """
    if LLM_PROVIDER == "anthropic":
        return await _call_anthropic(
            system_prompt, prompt,
            temperature=temperature, max_tokens=max_tokens,
        )
    return await _call_openai(
        system_prompt, prompt,
        temperature=temperature, max_tokens=max_tokens,
    )


# ── Provider implementations ──────────────────────────────────────────────────


async def _call_openai(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    temp = temperature if temperature is not None else 0.7
    tokens = max_tokens if max_tokens is not None else 4096

    payload: dict[str, Any] = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temp,
        "max_tokens": tokens,
    }

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


async def _call_anthropic(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    tokens = max_tokens if max_tokens is not None else 4096

    payload: dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": tokens,
        "system": [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": user_message}],
    }
    if temperature is not None:
        payload["temperature"] = temperature

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
