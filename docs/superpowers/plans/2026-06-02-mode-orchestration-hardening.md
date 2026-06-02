# Mode-Orchestration Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make any mode mis-route (tutor↔qa, resume↔facilitate, or a newly added mode) a loud, CI-caught failure instead of a silent wrong-mode answer.

**Architecture:** Convert the router's `if req.mode == ...` chain into an explicit `dict[ModeId, runner]` dispatch table, add an exhaustiveness test over `ModeId`, a per-mode routing contract test (mocked agents) that pins "mode X runs agent X", make the v1 unknown-mode fallback fail loud, and add backend↔frontend mode-set parity tests.

**Tech Stack:** Python 3.12 (FastAPI, pydantic, pytest), TypeScript/React (vitest).

---

## Background (read before starting)

Mode flows: frontend `activeMode` → POST `mode` → `ChatRequest.mode` (`ModeId = Literal["tutor","qa","facilitate","resume"]`, so Pydantic 422-rejects unknown strings at the API boundary) → `router.stream_chat` dispatches by `req.mode`.

Two silent-fallback holes today:
1. `src/services/chat/router.py:272` — a `req.mode` not matched by the if-chain silently falls through to the v1 orchestrator.
2. `src/services/chat/orchestrator.py:213` — `ModeRegistry.get(req.mode)` `KeyError` → silently runs **tutor**.

Current router dispatch (lines ~243-274) — note tutor has a deep/v2 toggle:
```python
if req.mode == "tutor":
    if os.environ.get("TUTOR_DEEP_MODE", "1") != "0":
        from src.services.chat.agents.deep_tutor import run_deep_tutor
        async for event in run_deep_tutor(req): yield event
        return
    async for event in _tutor_v2(req, history): yield event
    return
if req.mode == "qa":
    from src.services.chat.agents.qa import run_qa
    async for event in run_qa(req): yield event
    return
if req.mode == "facilitate":
    from src.services.chat.agents.facilitate import run_facilitate
    async for event in run_facilitate(req): yield event
    return
if req.mode == "resume":
    from src.services.chat.agents.chapter import run_chapter
    async for event in run_chapter(req): yield event
    return
# Unknown mode — fall through.
async for event in _v1_passthrough(req, history): yield event
```

`_v2_enabled_for(req.mode)` gates the whole v2 path (already runs BEFORE dispatch — keep that; the dispatch table only governs the v2 branch).

---

## File Structure

- **Modify** `src/services/chat/router.py` — extract per-mode runner coroutines, build `_V2_DISPATCH: dict[str, Callable]`, replace the if-chain, make the post-dispatch fallthrough explicit.
- **Modify** `src/services/chat/orchestrator.py` — unknown-mode `KeyError` becomes a loud error event instead of a silent tutor fallback.
- **Create** `src/services/chat/tests/test_mode_routing_contract.py` — exhaustiveness + per-mode routing contract.
- **Create** `src/services/chat/tests/test_mode_parity.py` — backend canonical mode-set assertion.
- **Create** `web/src/lib/modeParity.test.ts` — frontend `STATRAG_MODES` parity to the same canonical list.
- **Modify** `web/src/App.tsx` — export `STATRAG_MODES` (so the test can import it) if not already exported.

---

### Task 1: Router dispatch table + exhaustiveness test

**Files:**
- Modify: `src/services/chat/router.py`
- Test: `src/services/chat/tests/test_mode_routing_contract.py`

- [ ] **Step 1: Write the failing exhaustiveness test**

```python
# src/services/chat/tests/test_mode_routing_contract.py
"""Mode-routing guarantees: every ModeId has an explicit v2 runner, and each
mode dispatches to its own agent (no tutor↔qa / resume↔facilitate cross-wiring)."""
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
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_mode_routing_contract.py -q -k dispatch_entry`
Expected: FAIL — `cannot import name '_V2_DISPATCH'`.

- [ ] **Step 3: Implement the dispatch table in `src/services/chat/router.py`**

Add near the top imports:
```python
from collections.abc import AsyncIterator, Callable
```
Add these per-mode runner coroutines ABOVE `stream_chat` (each is an async generator with the uniform signature `(req, history)`):
```python
async def _run_tutor(req: ChatRequest, history: list[dict] | None) -> AsyncIterator[dict]:
    """Tutor runner: deep-tutor by default, v2 LangChain agent when
    ``TUTOR_DEEP_MODE=0``."""
    if os.environ.get("TUTOR_DEEP_MODE", "1") != "0":
        from src.services.chat.agents.deep_tutor import run_deep_tutor  # noqa: PLC0415
        async for event in run_deep_tutor(req):
            yield event
        return
    async for event in _tutor_v2(req, history):
        yield event


async def _run_qa(req: ChatRequest, history: list[dict] | None) -> AsyncIterator[dict]:
    from src.services.chat.agents.qa import run_qa  # noqa: PLC0415
    async for event in run_qa(req):
        yield event


async def _run_facilitate(req: ChatRequest, history: list[dict] | None) -> AsyncIterator[dict]:
    from src.services.chat.agents.facilitate import run_facilitate  # noqa: PLC0415
    async for event in run_facilitate(req):
        yield event


async def _run_resume(req: ChatRequest, history: list[dict] | None) -> AsyncIterator[dict]:
    from src.services.chat.agents.chapter import run_chapter  # noqa: PLC0415
    async for event in run_chapter(req):
        yield event


# Explicit mode → v2 runner table. Every ``ModeId`` MUST appear here; the
# exhaustiveness test (test_mode_routing_contract.py) fails otherwise, so a new
# mode cannot ship unrouted.
_V2_DISPATCH: dict[str, Callable[["ChatRequest", "list[dict] | None"], AsyncIterator[dict]]] = {
    "tutor": _run_tutor,
    "qa": _run_qa,
    "facilitate": _run_facilitate,
    "resume": _run_resume,
}
```
Now replace the body of `stream_chat` from `if req.mode == "tutor":` through the final `_v1_passthrough` fallthrough with:
```python
    runner = _V2_DISPATCH.get(req.mode)
    if runner is None:
        # ModeId is a Literal, so Pydantic rejects unknown modes at the API
        # boundary; reaching here means a declared mode lacks a runner — fail
        # loud rather than silently running the wrong pipeline.
        yield {
            "type": "error",
            "code": "MODE_NOT_ROUTED",
            "message": f"No v2 runner registered for mode '{req.mode}'.",
        }
        return
    async for event in runner(req, history):
        yield event
```
(Keep the `if not _v2_enabled_for(req.mode): _v1_passthrough; return` block exactly as-is ABOVE this — v1 rollback semantics are unchanged.)

- [ ] **Step 4: Run, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_mode_routing_contract.py -q -k dispatch_entry`
Expected: PASS.

- [ ] **Step 5: Run the existing router/mode tests for regressions**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q -k "router or tutor or qa or chapter or facilitate"`
Expected: PASS (3 groq skips ok).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/router.py src/services/chat/tests/test_mode_routing_contract.py
git commit -m "refactor(router): explicit _V2_DISPATCH table + exhaustiveness over ModeId

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Per-mode routing contract test

**Files:**
- Test: `src/services/chat/tests/test_mode_routing_contract.py` (extend)

- [ ] **Step 1: Write the failing contract test**

Append to `test_mode_routing_contract.py`. It patches each agent module's runner with a sentinel async-gen and asserts that `stream_chat` invokes ONLY the runner for the requested mode. Patching targets are the source modules the runner imports lazily.

```python
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

    # Install a sentinel for every agent runner; only the requested mode's
    # sentinel may fire.
    for m, (modpath, fname) in _MODE_TO_PATCH.items():
        agent_mod = importlib.import_module(modpath)

        def _make_sentinel(tag):
            async def _sentinel(req):  # agents are called as run_x(req)
                called.append(tag)
                yield {"type": "meta", "mode": req.mode}
            return _sentinel

        monkeypatch.setattr(agent_mod, fname, _make_sentinel(m))

    # Force tutor down the deep-tutor branch (default) so the patch above hits.
    monkeypatch.setenv("TUTOR_DEEP_MODE", "1")
    # Ensure v2 is enabled for the mode under test.
    monkeypatch.setattr(r, "_v2_enabled_for", lambda _m: True)

    events = await _collect(r.stream_chat(_make_request(mode), history=None))

    assert called == [mode], f"mode={mode} routed to {called}, expected [{mode!r}]"
    metas = [e for e in events if e.get("type") == "meta"]
    assert metas and metas[0]["mode"] == mode
```

- [ ] **Step 2: Run, verify it passes (guard is meaningful)**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_mode_routing_contract.py -q -k routes_to_its_own_agent`
Expected: PASS for all 4 modes. (If tutor fails because the deep-tutor lazy import path differs, confirm `_run_tutor` imports `run_deep_tutor` from `src.services.chat.agents.deep_tutor` — the patch target must match the import source.)

- [ ] **Step 3: Prove the guard catches cross-wiring (temporary sanity check, then revert)**

Temporarily edit `_V2_DISPATCH` in `router.py` to point `"qa": _run_facilitate`, run the test, confirm `test_mode_routes_to_its_own_agent[qa]` FAILS with `routed to ['facilitate']`. Then REVERT the edit (leave the table correct). Do not commit the broken table.

- [ ] **Step 4: Re-run to confirm green after revert**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_mode_routing_contract.py -q`
Expected: PASS (exhaustiveness + 4 routing cases).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/tests/test_mode_routing_contract.py
git commit -m "test(router): per-mode routing contract pins mode->agent (no cross-wiring)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Loud-fail the v1 unknown-mode fallback

**Files:**
- Modify: `src/services/chat/orchestrator.py` (~lines 209-214)
- Test: `src/services/chat/tests/test_mode_routing_contract.py` (extend)

- [ ] **Step 1: Write the failing test**

Append:
```python
def test_v1_registry_get_unknown_mode_raises_not_silent_tutor():
    """ModeRegistry.get must raise KeyError for an unknown mode (the orchestrator
    must not silently substitute tutor)."""
    from src.services.chat.modes import ModeRegistry

    with pytest.raises(KeyError):
        ModeRegistry.get("definitely-not-a-mode")
```

- [ ] **Step 2: Run, verify result**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_mode_routing_contract.py -q -k registry_get_unknown`
Expected: PASS already (ModeRegistry.get raises KeyError today). This test LOCKS that contract so a future "default to tutor" inside `get` would break it.

- [ ] **Step 3: Make the orchestrator caller fail loud instead of silent-tutor**

In `src/services/chat/orchestrator.py`, replace the silent fallback (around lines 211-214):
```python
        try:
            spec = ModeRegistry.get(req.mode)
        except KeyError:
            spec = ModeRegistry.get("tutor")
```
with:
```python
        try:
            spec = ModeRegistry.get(req.mode)
        except KeyError:
            # Do NOT silently run tutor — surface the mis-route so it is caught.
            yield {
                "type": "error",
                "code": "MODE_NOT_REGISTERED",
                "message": f"Mode '{req.mode}' has no registered ModeSpec.",
            }
            return
```
(Verify this block is inside the async generator `stream_chat` so `yield`/`return` are valid; it is — it sits in the `try:` at step 0. Keep surrounding code unchanged.)

- [ ] **Step 4: Add a test that the orchestrator emits the error event for an unknown mode**

Append:
```python
@pytest.mark.asyncio
async def test_v1_orchestrator_unknown_mode_emits_error(monkeypatch):
    from src.services.chat import orchestrator as o
    from src.services.chat.schemas._core import ChatRequest

    # Bypass ModeId Literal validation by constructing then mutating.
    req = ChatRequest(message="hi", mode="tutor", model="gpt-4o")
    object.__setattr__(req, "mode", "ghost-mode")  # force unknown at runtime

    events = [ev async for ev in o.stream_chat(req, None)]
    assert any(
        e.get("type") == "error" and e.get("code") == "MODE_NOT_REGISTERED"
        for e in events
    ), events
```
NOTE: if `ChatRequest` is a frozen/validated pydantic model and `object.__setattr__` is blocked, instead construct a lightweight stub with `.mode`, `.message`, `.model`, `.conversationId=None` attributes sufficient for the early code path, OR monkeypatch `ModeRegistry.get` to raise `KeyError` for the real request. Pick whichever the model allows; the assertion (error event with code `MODE_NOT_REGISTERED`) stays the same.

- [ ] **Step 5: Run, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_mode_routing_contract.py -q`
Expected: PASS.

- [ ] **Step 6: Run full backend chat suite for regressions**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: PASS (3 groq skips ok; a pre-existing `test_pipeline_latency_under_2s_when_mocked` may flake — re-run alone to confirm).

- [ ] **Step 7: Commit**

```bash
git add src/services/chat/orchestrator.py src/services/chat/tests/test_mode_routing_contract.py
git commit -m "fix(orchestrator): unknown mode emits MODE_NOT_REGISTERED error (was silent tutor)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Backend↔frontend mode-set parity

**Files:**
- Create: `src/services/chat/tests/test_mode_parity.py`
- Modify: `web/src/App.tsx` (export `STATRAG_MODES`)
- Create: `web/src/lib/modeParity.test.ts`

- [ ] **Step 1: Write the backend canonical-set test**

```python
# src/services/chat/tests/test_mode_parity.py
"""Backend canonical mode set. The SAME list is asserted on the frontend
(web/src/lib/modeParity.test.ts). Changing modes requires updating BOTH, on
purpose — that is the parity guard."""
from __future__ import annotations

from typing import get_args

from src.services.chat.schemas._core import ModeId

CANONICAL_MODES = ["tutor", "qa", "facilitate", "resume"]


def test_modeid_matches_canonical_list():
    assert sorted(get_args(ModeId)) == sorted(CANONICAL_MODES)
```

- [ ] **Step 2: Run, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_mode_parity.py -q`
Expected: PASS.

- [ ] **Step 3: Ensure `STATRAG_MODES` is exported in `web/src/App.tsx`**

Find `const STATRAG_MODES: ModeMeta[] = [` and prefix with `export ` if not already exported:
```ts
export const STATRAG_MODES: ModeMeta[] = [
```

- [ ] **Step 4: Write the failing frontend parity test**

```ts
// web/src/lib/modeParity.test.ts
import { describe, it, expect } from "vitest";
import { STATRAG_MODES } from "../App";

// MUST stay in sync with CANONICAL_MODES in
// src/services/chat/tests/test_mode_parity.py — both fail if the sets drift.
const CANONICAL_MODES = ["tutor", "qa", "facilitate", "resume"];

describe("mode parity (frontend ↔ backend)", () => {
  it("STATRAG_MODES ids equal the canonical backend mode set", () => {
    const ids = STATRAG_MODES.map((m) => m.id).sort();
    expect(ids).toEqual([...CANONICAL_MODES].sort());
  });
});
```

- [ ] **Step 5: Run, verify PASS**

Run: `cd web && npx vitest run src/lib/modeParity.test.ts`
Expected: PASS. If importing from `../App` pulls heavy module side-effects and fails under jsdom, instead import the list from where it is defined; if needed, extract `STATRAG_MODES` into `web/src/modes.ts` and re-export from `App.tsx`, then import the test from `web/src/modes.ts`. Keep the assertion identical.

- [ ] **Step 6: Run full frontend suite for regressions**

Run: `cd web && npx vitest run`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/services/chat/tests/test_mode_parity.py web/src/App.tsx web/src/lib/modeParity.test.ts
git commit -m "test(modes): backend<->frontend mode-set parity guard

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- #1 dispatch table → Task 1. ✔
- #2 exhaustiveness over ModeId → Task 1 Step 1. ✔
- #3 per-mode routing contract (no cross-wiring) → Task 2 (+ Step 3 proves the guard bites). ✔
- #4 loud-fail v1 unknown-mode fallback → Task 3. ✔
- #5 backend↔frontend parity → Task 4. ✔

**Placeholder scan:** none. The two NOTEs (Task 3 Step 4 pydantic-mutation fallback; Task 4 Step 5 import fallback) are explicit contingency instructions with concrete alternatives, not deferred work.

**Type consistency:** `_V2_DISPATCH` name + signature `(req, history) -> AsyncIterator[dict]` consistent across Tasks 1-2. Runner names `_run_tutor/_run_qa/_run_facilitate/_run_resume` consistent. Error codes: router `MODE_NOT_ROUTED`, orchestrator `MODE_NOT_REGISTERED` (intentionally distinct — different layers). `CANONICAL_MODES` mirrored in Task 4 backend + frontend by design.

**Note on `_v2_enabled_for`:** unchanged; the v1-rollback branch still runs before dispatch. The dispatch table governs only the v2 path. Task 2 patches `_v2_enabled_for→True` to isolate the v2 routing.
