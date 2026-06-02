"""Mode-routing guarantees: every ModeId has an explicit v2 runner, and each
mode dispatches to its own agent (no tutor<->qa / resume<->facilitate cross-wiring)."""
from __future__ import annotations

from typing import get_args

import pytest

from src.services.chat.schemas._core import ModeId


def test_every_modeid_has_a_v2_dispatch_entry():
    from src.services.chat.router import _V2_DISPATCH

    declared = set(get_args(ModeId))
    routed = set(_V2_DISPATCH)
    assert declared == routed, (
        f"ModeId/_V2_DISPATCH mismatch — declared-only={declared - routed}, "
        f"routed-only={routed - declared}"
    )


def _make_request(mode: str):
    from src.services.chat.schemas._core import ChatRequest
    return ChatRequest(message="hi", mode=mode, model="gpt-4o")


async def _collect(agen):
    return [ev async for ev in agen]


_MODE_TO_PATCH = {
    "tutor": ("src.services.chat.agents.deep_tutor", "run_deep_tutor"),
    "qa": ("src.services.chat.agents.qa", "run_qa"),
    "facilitate": ("src.services.chat.agents.facilitate", "run_facilitate"),
    "resume": ("src.services.chat.agents.chapter", "run_chapter"),
}


@pytest.mark.parametrize("mode", list(get_args(ModeId)))
@pytest.mark.asyncio
async def test_mode_routes_to_its_own_agent(mode, monkeypatch):
    """Each mode must invoke ONLY its own agent runner — no cross-wiring."""
    import importlib

    from src.services.chat import router as r

    called: list[str] = []

    for m, (modpath, fname) in _MODE_TO_PATCH.items():
        agent_mod = importlib.import_module(modpath)

        def _make_sentinel(tag):
            async def _sentinel(req):
                called.append(tag)
                yield {"type": "meta", "mode": req.mode}
            return _sentinel

        monkeypatch.setattr(agent_mod, fname, _make_sentinel(m))

    monkeypatch.setenv("TUTOR_DEEP_MODE", "1")
    monkeypatch.setattr(r, "_v2_enabled_for", lambda _m: True)

    events = await _collect(r.stream_chat(_make_request(mode), history=None))

    assert called == [mode], f"mode={mode} routed to {called}, expected [{mode!r}]"
    metas = [e for e in events if e.get("type") == "meta"]
    assert metas and metas[0]["mode"] == mode


def test_mode_to_patch_covers_every_modeid():
    """_MODE_TO_PATCH must list every ModeId so the routing contract test stays
    exhaustive when a new mode is added."""
    assert set(_MODE_TO_PATCH) == set(get_args(ModeId)), (
        f"_MODE_TO_PATCH out of sync with ModeId: "
        f"missing={set(get_args(ModeId)) - set(_MODE_TO_PATCH)}, "
        f"extra={set(_MODE_TO_PATCH) - set(get_args(ModeId))}"
    )


def test_v1_registry_get_unknown_mode_raises_not_silent_tutor():
    """ModeRegistry.get must raise KeyError for an unknown mode (no silent tutor)."""
    from src.services.chat.modes import ModeRegistry

    with pytest.raises(KeyError):
        ModeRegistry.get("definitely-not-a-mode")


@pytest.mark.asyncio
async def test_v1_orchestrator_unknown_mode_emits_error(monkeypatch):
    from src.services.chat import orchestrator as o

    req = _make_request("tutor")
    # Force an unknown mode at runtime, bypassing the ModeId Literal validation.
    try:
        object.__setattr__(req, "mode", "ghost-mode")
    except Exception:
        pytest.skip("ChatRequest does not allow runtime mode mutation")

    events = [ev async for ev in o.stream_chat(req, None)]
    assert any(
        e.get("type") == "error" and e.get("code") == "MODE_NOT_REGISTERED"
        for e in events
    ), events
    assert any(e.get("type") == "done" for e in events), events
    # error precedes done
    types = [e.get("type") for e in events]
    assert types.index("error") < types.index("done")
