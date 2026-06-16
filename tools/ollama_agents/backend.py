"""Ollama cloud transport — native /api/chat with Bearer auth.

The OpenAI-compatible /v1 path 401s for these keys; the native endpoint
(matching the working MCP server: host https://ollama.com, Authorization: Bearer)
is what authenticates. Key/host come from the environment, falling back to the
repo .env (which is symlinked in and holds the full key — note the key contains
a '.', so never extract it with a token regex that stops at punctuation).
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

_ENV = Path(__file__).resolve().parents[2] / ".env"


def _from_dotenv(var: str) -> str | None:
    if _ENV.exists():
        for line in _ENV.read_text().splitlines():
            line = line.strip()
            if line.startswith(var + "=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    return None


def _from_env(var: str) -> str | None:
    # .env first: host+key must be a MATCHED pair, and the shell environment may
    # carry a different (non-working) OLLAMA_HOST/KEY. .env is the project's
    # verified pair (host https://ollama.com + the 265eb key). os.environ is the
    # fallback only when .env lacks the var.
    return _from_dotenv(var) or os.environ.get(var)


def credentials() -> tuple[str, str]:
    key = _from_env("OLLAMA_API_KEY")
    host = _from_env("OLLAMA_HOST") or "https://ollama.com"
    if not key:
        raise RuntimeError("OLLAMA_API_KEY not set (env or .env)")
    return key, host.rstrip("/")


def chat(model: str, messages: list[dict], tools: list[dict] | None = None,
         timeout: float = 180.0) -> dict:
    """One turn against Ollama cloud. Returns the assistant ``message`` dict
    (may contain ``tool_calls``). Raises httpx.HTTPStatusError on non-2xx."""
    key, host = credentials()
    body: dict = {"model": model, "stream": False, "messages": messages}
    if tools:
        body["tools"] = tools
    r = httpx.post(f"{host}/api/chat",
                   headers={"Authorization": f"Bearer {key}"},
                   json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()["message"]
