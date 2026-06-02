# Per-Turn Mode Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One conversation can hold turns of different modes; each turn runs and persists its own mode, reloads with the correct per-turn pipeline, and the picker (next-turn mode) is never silently overridden after the user switches it.

**Architecture:** Backend persists `metadata.mode = req.mode` per assistant turn (the dispatch table already routes by `req.mode`). Frontend reads per-message mode on reload and syncs the picker to a conversation's last-turn mode only once per conversation switch (replacing the over-eager reset that clobbered mid-conversation switches).

**Tech Stack:** Python 3.12 (FastAPI, pytest), TypeScript/React (vitest).

---

## File Structure

- **Modify** `src/services/chat/api.py` — `chat_event_gen._persist_assistant` writes `metadata.mode = req.mode`.
- **Modify** `web/src/lib/mapConversationMessages.ts` — assistant `mode` from `metadata.mode ?? convMode`.
- **Create** `web/src/lib/lastTurnMode.ts` — pure helper: last assistant message's mode or fallback.
- **Modify** `web/src/App.tsx` — guarded one-shot picker sync per conversation switch.
- **Tests:** `src/services/chat/tests/test_run_cancel.py` (extend) + `test_per_turn_mode.py` (new); `web/src/lib/mapConversationMessages.test.ts`, `web/src/lib/lastTurnMode.test.ts`.

Run: backend `.venv/bin/python -m pytest <path> -q`; frontend `cd web && npx vitest run <path>`.

---

### Task 1: Persist each turn's mode (backend)

**Files:**
- Modify: `src/services/chat/api.py` (`chat_event_gen._persist_assistant`)
- Test: `src/services/chat/tests/test_run_cancel.py` (extend)

CONTEXT — `_persist_assistant(stopped)` currently builds metadata as:
```python
            metadata = collected_meta
            if stopped:
                metadata = {**(collected_meta or {}), "stopped": True}
```
Change it to always include the request mode, and keep the stopped marker:
```python
            metadata = {**(collected_meta or {}), "mode": req.mode}
            if stopped:
                metadata["stopped"] = True
```

- [ ] **Step 1: Write the failing test** (append to `test_run_cancel.py`)

```python
@pytest.mark.asyncio
async def test_chat_event_gen_persists_turn_mode(monkeypatch):
    """A normal turn persists metadata.mode == req.mode."""
    import asyncio as _asyncio

    from src.services.chat import api as chat_api
    from src.services.chat.schemas._core import ChatRequest

    appended: list[dict] = []
    monkeypatch.setattr(chat_api.store, "append_message", lambda **kw: appended.append(kw))
    monkeypatch.setattr(chat_api.store, "get_messages", lambda _c: [])

    async def _fake_stream(req, history=None):
        yield {"type": "token", "text": "hi"}

    monkeypatch.setattr(chat_api, "stream_chat", _fake_stream)

    req = ChatRequest(message="q", mode="facilitate", model="gpt-4o",
                      conversationId="conv-z")
    async for _ in chat_api.chat_event_gen(req):
        pass

    assert appended, "assistant row not persisted"
    assert appended[-1]["metadata"]["mode"] == "facilitate"
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_run_cancel.py -q -k persists_turn_mode`
Expected: FAIL — `metadata` has no `"mode"` key (KeyError) because today it persists `collected_meta` (None → KeyError on subscript).

- [ ] **Step 3: Implement**

In `src/services/chat/api.py`, inside `_persist_assistant`, replace the metadata block as shown in CONTEXT above (always merge `"mode": req.mode`; add `"stopped": True` only when stopped).

- [ ] **Step 4: Run, verify PASS (and the cancel test still carries both keys)**

Add to the existing `test_chat_event_gen_persists_partial_on_cancel` an extra assertion after the stopped checks:
```python
    assert row["metadata"]["mode"] == "tutor"
    assert row["metadata"]["stopped"] is True
```
Run: `.venv/bin/python -m pytest src/services/chat/tests/test_run_cancel.py -q`
Expected: PASS (turn-mode + cancel-partial both carry `mode`; cancel also carries `stopped`).

- [ ] **Step 5: Regression**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: PASS (3 groq skips ok; ignore the known `test_pipeline_latency_under_2s_when_mocked` timing flake — re-run alone to confirm).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/api.py src/services/chat/tests/test_run_cancel.py
git commit -m "feat(chat): persist metadata.mode = req.mode per assistant turn

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Per-message mode on reload (frontend)

**Files:**
- Modify: `web/src/lib/mapConversationMessages.ts`
- Test: `web/src/lib/mapConversationMessages.test.ts`

CONTEXT — the assistant `base` object sets `mode: convMode` (where `convMode = parseConvMode(data.mode)`). Change it to prefer the row's own metadata.

- [ ] **Step 1: Write the failing test** (append to `mapConversationMessages.test.ts`)

```ts
it("uses per-message metadata.mode, falling back to the conversation mode", () => {
  const out = mapConversationMessages({
    mode: "tutor",
    messages: [
      { role: "user", content: "q" },
      { role: "assistant", content: "digest", metadata: { mode: "facilitate" } },
      { role: "user", content: "q2" },
      { role: "assistant", content: "ans" }, // legacy: no metadata.mode
    ],
  } as never);
  const assistants = out.filter((m) => m.role === "assistant") as AssistantMessage[];
  expect(assistants[0].mode).toBe("facilitate"); // from metadata
  expect(assistants[1].mode).toBe("tutor");      // fallback to convMode
});
```
(Match the real input shape used by other tests in this file; adjust the literal to satisfy its parameter type.)

- [ ] **Step 2: Run, verify FAIL**

Run: `cd web && npx vitest run src/lib/mapConversationMessages.test.ts -t "per-message metadata.mode"`
Expected: FAIL — first assistant maps to `"tutor"` (convMode), not `"facilitate"`.

- [ ] **Step 3: Implement**

In `web/src/lib/mapConversationMessages.ts`, in the assistant `base` object, change:
```ts
      mode: convMode,
```
to:
```ts
      mode: ((m.metadata as { mode?: string } | null)?.mode) ?? convMode,
```
(Leave the `retrievalMetadata` and `stopped` reads unchanged.) Update the function's leading comment ("stamps it on every assistant message") to note per-message mode with conversation fallback.

- [ ] **Step 4: Run, verify PASS**

Run: `cd web && npx vitest run src/lib/mapConversationMessages.test.ts`
Expected: PASS (new + existing, including the stopped-mapping tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/mapConversationMessages.ts web/src/lib/mapConversationMessages.test.ts
git commit -m "feat(web): per-message mode on reload (metadata.mode ?? conversation mode)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Guarded one-shot picker sync (frontend)

**Files:**
- Create: `web/src/lib/lastTurnMode.ts`
- Test: `web/src/lib/lastTurnMode.test.ts`
- Modify: `web/src/App.tsx` (`handleSelectConv`)

- [ ] **Step 1: Write the failing test** — create `web/src/lib/lastTurnMode.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { lastTurnMode } from "./lastTurnMode";
import type { Message } from "../types";

const asst = (mode: string): Message =>
  ({ role: "assistant", id: "a", time: "", timestamp: 0, mode, model: "", books: [],
     sourceCount: 0, latencyMs: 0, blocks: [], status: "complete" } as Message);
const user = (): Message =>
  ({ role: "user", id: "u", time: "", timestamp: 0, text: "x" } as Message);

describe("lastTurnMode", () => {
  it("returns the most recent assistant message's mode", () => {
    expect(lastTurnMode([user(), asst("tutor"), user(), asst("facilitate")], "tutor"))
      .toBe("facilitate");
  });
  it("falls back when there is no assistant message", () => {
    expect(lastTurnMode([user()], "resume")).toBe("resume");
  });
});
```

- [ ] **Step 2: Run, verify FAIL**

Run: `cd web && npx vitest run src/lib/lastTurnMode.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `web/src/lib/lastTurnMode.ts`**

```ts
import type { Message } from "../types";

// The mode to default the picker to when a conversation is opened: the mode of
// its most recent assistant turn, falling back to the conversation mode when the
// conversation has no assistant message yet.
export function lastTurnMode(messages: Message[], fallback: string): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "assistant" && typeof m.mode === "string" && m.mode) {
      return m.mode;
    }
  }
  return fallback;
}
```

- [ ] **Step 4: Run, verify PASS**

Run: `cd web && npx vitest run src/lib/lastTurnMode.test.ts`
Expected: PASS.

- [ ] **Step 5: Wire the guarded sync into `web/src/App.tsx`**

Add the import:
```ts
import { lastTurnMode } from "./lib/lastTurnMode";
```
Add a ref near the other refs/state in the `App` component body:
```ts
  // Tracks the last conversation whose picker mode we synced, so opening the
  // SAME conversation again (popstate / re-select) never clobbers a mode the
  // user changed mid-conversation.
  const lastSyncedConvRef = React.useRef<string | null>(null);
```
(`React` is already imported in App.tsx.)

In `handleSelectConv`, replace the unconditional sync line:
```ts
      setActiveMode((cur) => pickOpenedMode(data.mode, STATRAG_MODES, cur));
```
with the one-shot, last-turn sync:
```ts
      if (lastSyncedConvRef.current !== id) {
        lastSyncedConvRef.current = id;
        const desiredMode = lastTurnMode(msgs, data.mode);
        setActiveMode((cur) => pickOpenedMode(desiredMode, STATRAG_MODES, cur));
      }
```
(`msgs` is already `mapConversationMessages(data)` just above; `pickOpenedMode` stays — it validates the mode against `STATRAG_MODES`.)

- [ ] **Step 6: Full frontend suite + typecheck**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: all green, no type errors.

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/lastTurnMode.ts web/src/lib/lastTurnMode.test.ts web/src/App.tsx
git commit -m "fix(web): picker syncs once per conversation switch to last-turn mode (no mid-conversation clobber)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Functional E2E — many modes in one conversation (backend)

**Files:**
- Create: `src/services/chat/tests/test_per_turn_mode.py`

This is the "final test": drive several turns with different `req.mode` into ONE conversation id and assert each persisted assistant row carries that turn's mode. Deterministic + provider-agnostic (mocks the agent stream), so it runs with any model/provider.

- [ ] **Step 1: Write the test**

```python
"""Functional: a single conversation holds turns of different modes, each
persisted with its own metadata.mode."""
from __future__ import annotations

import pytest

from src.services.chat import api as chat_api
from src.services.chat.schemas._core import ChatRequest


@pytest.mark.asyncio
async def test_one_conversation_many_modes(monkeypatch):
    rows: list[dict] = []
    monkeypatch.setattr(chat_api.store, "append_message", lambda **kw: rows.append(kw))
    monkeypatch.setattr(chat_api.store, "get_messages", lambda _c: [])

    # Each turn's fake stream emits a meta echo + a structured payload tagged
    # with the requested mode, mimicking the real per-mode agents.
    async def _fake_stream(req, history=None):
        yield {"type": "meta", "mode": req.mode}
        yield {"type": "structured_output", "schema": f"{req.mode}-schema",
               "data": {"mode": req.mode}}

    monkeypatch.setattr(chat_api, "stream_chat", _fake_stream)

    conv = "conv-multi"
    for mode in ["tutor", "facilitate", "qa", "resume"]:
        req = ChatRequest(message=f"turn {mode}", mode=mode, model="gpt-4o",
                          conversationId=conv)
        async for _ in chat_api.chat_event_gen(req):
            pass

    # 4 user rows + 4 assistant rows, all in the same conversation.
    assistant_rows = [r for r in rows if r["role"] == "assistant"]
    assert [r["metadata"]["mode"] for r in assistant_rows] == [
        "tutor", "facilitate", "qa", "resume"
    ]
    assert all(r["conversation_id"] == conv for r in rows)
```

- [ ] **Step 2: Run, verify it passes (Task 1 already persists mode)**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_per_turn_mode.py -q`
Expected: PASS — each turn persisted with its own mode in one conversation. (If it fails because `chat_event_gen` requires more of the request/store than mocked, inspect the generator and stub the minimum it touches — do not change product code for the test.)

- [ ] **Step 3: Full backend suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: PASS (3 groq skips ok; ignore the known latency flake).

- [ ] **Step 4: Commit**

```bash
git add src/services/chat/tests/test_per_turn_mode.py
git commit -m "test(chat): functional — one conversation holds tutor/facilitate/qa/resume turns

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Backend persists `metadata.mode = req.mode` (normal + cancel) → Task 1. ✔
- Reload reads per-message mode w/ conversation fallback → Task 2. ✔
- Picker one-shot sync per conversation switch (no clobber), last-turn mode → Task 3. ✔
- Per-turn display → already keyed on `msg.mode`; Task 2 makes it correct (no code change needed; Task 4 + manual confirm). ✔
- Functional E2E many-modes-in-one-conversation → Task 4. ✔
- Tests at each layer → Tasks 1-4. ✔

**Placeholder scan:** none. The "match the real input shape" notes (Task 2 Step 1) and the Task 4 Step 2 fallback are concrete contingencies, not deferred work.

**Type consistency:** `metadata.mode` written in Task 1, read in Task 2 (map) and Task 4 (assert). `lastTurnMode(messages, fallback)` defined Task 3 Step 3, used Task 3 Step 5. `lastSyncedConvRef` defined + used in Task 3 Step 5. `pickOpenedMode` reused (validates mode) — unchanged signature. `Message.mode` is the existing `AssistantMessage.mode` field.

**Note:** `pickOpenedMode` (added in the earlier mode-sync fix) is retained as the validator; only its trigger changes (unconditional → one-shot per conversation). The backend dispatch/orchestrator is unchanged — it already routes by `req.mode`.
