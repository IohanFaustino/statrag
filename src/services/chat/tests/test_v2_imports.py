"""T01 acceptance: LangChain 1.0 + LangGraph + LangSmith importable, v2 scaffold present.

Asserts:
1. LangChain >= 1.0 installed.
2. LangGraph >= 1.0 installed.
3. LangSmith >= 0.3.0 installed.
4. Key v2 entry points importable: `create_agent`, `StateGraph`, `MemorySaver`.
5. v2 scaffold modules exist: `modes`, `retrievers`, `router`.
6. v2 router falls through to v1 when no mode is flagged.
"""
from __future__ import annotations

import importlib

import pytest


def _version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse a dotted version string into a tuple of ints, ignoring trailing tags."""
    parts: list[int] = []
    for chunk in version_str.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def test_langchain_one_oh_installed():
    import langchain

    assert _version_tuple(langchain.__version__) >= (1, 0), (
        f"LangChain >= 1.0 required, got {langchain.__version__}"
    )


def test_langgraph_one_oh_installed():
    import importlib.metadata

    version = importlib.metadata.version("langgraph")
    assert _version_tuple(version) >= (1, 0), (
        f"LangGraph >= 1.0 required, got {version}"
    )


def test_langsmith_three_oh_installed():
    import langsmith

    assert _version_tuple(langsmith.__version__) >= (0, 3), (
        f"LangSmith >= 0.3.0 required, got {langsmith.__version__}"
    )


def test_v2_entry_points_importable():
    from langchain.agents import create_agent  # noqa: F401
    from langchain_core.tools import tool  # noqa: F401
    from langgraph.graph import StateGraph, START, END  # noqa: F401
    from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: F401


def test_v2_scaffold_packages_present():
    importlib.import_module("src.services.chat.mode_impls")
    importlib.import_module("src.services.chat.retrievers")
    importlib.import_module("src.services.chat.router")


def test_v2_router_falls_through_to_v1_when_empty(monkeypatch):
    """With USE_V2_MODES explicitly empty, the router must defer to v1.

    T12 changed the default to ['*'] (every mode on v2). This test still
    asserts the v1 fallback path works when the env var is explicitly empty.
    """
    from src.services.chat import router
    from src.services.chat import orchestrator as v1
    from src.services.chat.schemas import ChatRequest

    monkeypatch.setattr(router.settings, "use_v2_modes", [], raising=False)

    called = {"hit": False}

    async def _stub_stream(req, history=None):
        called["hit"] = True
        yield {"type": "done"}

    monkeypatch.setattr(v1, "stream_chat", _stub_stream)

    import asyncio

    async def _drive():
        req = ChatRequest(message="hi", mode="tutor", model="gpt-5.4-nano-2026-03-17")
        async for _ in router.stream_chat(req):
            pass

    asyncio.run(_drive())
    assert called["hit"], "v1 stream_chat was never invoked despite empty USE_V2_MODES"


def test_v2_settings_present():
    from src.core.config import settings

    assert hasattr(settings, "use_v2_modes"), "USE_V2_MODES config missing"
    assert hasattr(settings, "checkpointer_db"), "CHECKPOINTER_DB config missing"
    assert hasattr(settings, "langsmith_disabled"), "LANGSMITH_DISABLED config missing"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ([], []),
        (["tutor"], ["tutor"]),
        (["tutor", "compare"], ["tutor", "compare"]),
    ],
)
def test_parsed_use_v2_modes(monkeypatch, raw, expected):
    from src.core.config import settings

    monkeypatch.setattr(settings, "use_v2_modes", raw, raising=False)
    assert settings.parsed_use_v2_modes() == expected
