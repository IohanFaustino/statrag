# Cancel a Streaming Turn (Stop button) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A ChatGPT-style Stop button that halts the in-flight detached server run and keeps the partial answer (persisted with a "stopped" marker).

**Architecture:** Backend gains `runs.cancel(conv_id)` (cancels the run's asyncio.Task) + `POST /api/chat/{conv_id}/cancel`, and `chat_event_gen` persists the partial assistant text with `metadata={"stopped": true}` on `CancelledError`. Frontend turns the Send button into a Stop button while streaming; Stop aborts the client read, POSTs cancel, and marks the message stopped. Reloaded conversations render the stopped marker.

**Tech Stack:** Python 3.12 (FastAPI, asyncio, pytest), TypeScript/React (vitest).

---

## File Structure

- **Modify** `src/services/chat/runs.py` — add `cancel(conv_id) -> bool`.
- **Modify** `src/services/chat/api.py` — `POST /api/chat/{conv_id}/cancel`; persist partial on cancel in `chat_event_gen`.
- **Modify** `web/src/api/sse.ts` — `cancelRun(convId)`.
- **Modify** `web/src/types.ts` — `stopped?: boolean` on `AssistantMessage`.
- **Modify** `web/src/state/chat.ts` — `STOP` reducer action + `stopStream` + expose it.
- **Modify** `web/src/lib/mapConversationMessages.ts` — map `metadata.stopped`.
- **Modify** `web/src/components/InputBar.tsx` — Stop button while streaming.
- **Modify** `web/src/App.tsx` — pass `isStreaming` + `onStop`.
- **Modify** `web/src/components/MessageThread.tsx` — "Stopped" pill.
- **Tests:** `src/services/chat/tests/test_run_cancel.py`; vitest specs alongside the frontend files.

Run: backend `.venv/bin/python -m pytest <path> -q`; frontend `cd web && npx vitest run <path>`.

---

### Task 1: Backend `runs.cancel` + cancel endpoint

**Files:**
- Modify: `src/services/chat/runs.py`
- Modify: `src/services/chat/api.py`
- Test: `src/services/chat/tests/test_run_cancel.py`

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_run_cancel.py
"""Run cancellation: runs.cancel halts an active detached run."""
from __future__ import annotations

import asyncio

import pytest

from src.services.chat import runs


@pytest.fixture(autouse=True)
def _clean_runs():
    runs._reset_for_tests()
    yield
    runs._reset_for_tests()


@pytest.mark.asyncio
async def test_cancel_active_run_stops_it():
    started = asyncio.Event()

    async def _source():
        yield {"type": "token", "text": "hello"}
        started.set()
        # Never completes until cancelled.
        await asyncio.sleep(3600)
        yield {"type": "token", "text": "never"}

    runs.start_run("c1", _source)
    await asyncio.wait_for(started.wait(), timeout=2)

    assert runs.is_active("c1") is True
    assert runs.cancel("c1") is True

    # Give the event loop a tick to process the cancellation + _drive finally.
    await asyncio.sleep(0.05)
    assert runs.is_active("c1") is False


@pytest.mark.asyncio
async def test_cancel_unknown_run_returns_false():
    assert runs.cancel("nope") is False
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_run_cancel.py -q`
Expected: FAIL — `module 'src.services.chat.runs' has no attribute 'cancel'`.

- [ ] **Step 3: Implement `cancel` in `src/services/chat/runs.py`**

Add (near `is_active` / `status`):
```python
def cancel(conv_id: str) -> bool:
    """Cancel an active run's driving task. Returns True if a live run was
    cancelled, False when there is no run or it already finished.

    The task's ``_drive`` ``finally`` marks the run done and notifies
    subscribers, so callers need do nothing else.
    """
    run = _runs.get(conv_id)
    if run is None or run.done or run.task is None:
        return False
    run.task.cancel()
    return True
```

- [ ] **Step 4: Run, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_run_cancel.py -q`
Expected: PASS (both tests).

- [ ] **Step 5: Add the endpoint to `src/services/chat/api.py`**

After the `chat_status` endpoint (`GET /api/chat/{conv_id}/status`), add:
```python
@app.post("/api/chat/{conv_id}/cancel")
async def chat_cancel(conv_id: str) -> dict:
    """Stop an in-flight detached run (§13). Idempotent — returns
    ``{"cancelled": false}`` when no active run exists."""
    return {"cancelled": runs.cancel(conv_id)}
```
(`runs` is already imported in api.py.)

- [ ] **Step 6: Add an endpoint smoke test**

Append to `test_run_cancel.py`:
```python
def test_cancel_endpoint_unknown_conv_returns_false():
    from fastapi.testclient import TestClient

    from src.services.chat.api import app

    client = TestClient(app)
    r = client.post("/api/chat/does-not-exist/cancel")
    assert r.status_code == 200
    assert r.json() == {"cancelled": False}
```

- [ ] **Step 7: Run + commit**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_run_cancel.py -q`
Expected: PASS (3 tests).
```bash
git add src/services/chat/runs.py src/services/chat/api.py src/services/chat/tests/test_run_cancel.py
git commit -m "feat(runs): cancel(conv_id) + POST /api/chat/{conv_id}/cancel

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Persist the partial answer on cancel

**Files:**
- Modify: `src/services/chat/api.py` (`chat_event_gen`)
- Test: `src/services/chat/tests/test_run_cancel.py` (extend)

CONTEXT — the current persist block (after the `async for ev in stream_chat(...)` loop) is:
```python
        if req.conversationId and (structured_payload or assistant_text_buf):
            if structured_payload is not None:
                content: dict | str = dict(structured_payload)
                if structured_schema:
                    content.setdefault("_schema", structured_schema)
            else:
                content = "".join(assistant_text_buf)
            try:
                store.append_message(
                    conversation_id=req.conversationId, role="assistant",
                    content=content, sources=collected_sources,
                    figures=collected_figures, metadata=collected_meta,
                )
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
        yield {"type": "done"}
```
`CancelledError` is a `BaseException` (not `Exception`), so it bypasses the existing `except Exception`. We add a dedicated handler that persists the partial with a stopped marker, then re-raises so `runs._drive` finalizes.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_chat_event_gen_persists_partial_on_cancel(monkeypatch):
    """Cancelling mid-stream persists the partial assistant text with
    metadata {'stopped': True}."""
    import asyncio as _asyncio

    from src.services.chat import api as chat_api
    from src.services.chat.schemas._core import ChatRequest

    appended: list[dict] = []

    def _fake_append(**kwargs):
        appended.append(kwargs)

    monkeypatch.setattr(chat_api.store, "append_message", _fake_append)
    monkeypatch.setattr(chat_api.store, "get_messages", lambda _c: [])

    started = _asyncio.Event()

    async def _fake_stream(req, history=None):
        yield {"type": "token", "text": "par"}
        yield {"type": "token", "text": "tial"}
        started.set()
        await _asyncio.sleep(3600)

    monkeypatch.setattr(chat_api, "stream_chat", _fake_stream)

    req = ChatRequest(message="hi", mode="tutor", model="gpt-4o",
                      conversationId="conv-x")

    async def _consume():
        async for _ in chat_api.chat_event_gen(req):
            pass

    task = _asyncio.create_task(_consume())
    await _asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(_asyncio.CancelledError):
        await task

    assert appended, "partial was not persisted on cancel"
    row = appended[-1]
    assert row["role"] == "assistant"
    assert row["content"] == "partial"
    assert row["metadata"] == {"stopped": True}
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_run_cancel.py -q -k persists_partial`
Expected: FAIL — nothing appended (CancelledError currently skips persistence).

- [ ] **Step 3: Refactor persistence into a nested helper + add the cancel handler**

In `chat_event_gen`, replace the after-loop persist block AND extend the except chain. Define a nested helper just before the `async for` loop (so it closes over the buffers/`req`), call it after the loop with `stopped=False`, and call it from a new `except asyncio.CancelledError` handler with `stopped=True`. Ensure `import asyncio` is present at the top of api.py (add if missing).

```python
        def _persist_assistant(stopped: bool) -> None:
            if not (req.conversationId and (structured_payload or assistant_text_buf)):
                return
            if structured_payload is not None:
                content: dict | str = dict(structured_payload)
                if structured_schema:
                    content.setdefault("_schema", structured_schema)
            else:
                content = "".join(assistant_text_buf)
            metadata = collected_meta
            if stopped:
                metadata = {**(collected_meta or {}), "stopped": True}
            try:
                store.append_message(
                    conversation_id=req.conversationId, role="assistant",
                    content=content, sources=collected_sources,
                    figures=collected_figures, metadata=metadata,
                )
            except Exception:  # noqa: BLE001
                pass

        async for ev in stream_chat(req, history=history):
            ...  # KEEP the existing accumulation + `yield ev` body unchanged
        _persist_assistant(stopped=False)
    except asyncio.CancelledError:
        _persist_assistant(stopped=True)
        raise
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
        yield {"type": "done"}
```
IMPORTANT:
- The nested `_persist_assistant` must be defined where `structured_payload`,
  `structured_schema`, `assistant_text_buf`, `collected_sources`,
  `collected_figures`, `collected_meta` are already initialised (they are
  declared before the loop today) — read the function and place it accordingly.
- Do NOT change the accumulation logic inside the `async for`.
- The `content`/`metadata` local annotations may trip "redefinition" — if the
  outer scope also annotates `content`, drop the inner annotation (use plain
  assignment) to avoid a mypy/runtime conflict.

- [ ] **Step 4: Run, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_run_cancel.py -q`
Expected: PASS (all, incl. the partial-persist test).

- [ ] **Step 5: Regression — backend chat suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: PASS (3 groq skips ok; ignore the known `test_pipeline_latency_under_2s_when_mocked` timing flake — re-run alone to confirm).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/api.py src/services/chat/tests/test_run_cancel.py
git commit -m "feat(chat): persist partial answer with stopped marker on cancel

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Frontend cancel plumbing (api + reducer + hook + reload mapping)

**Files:**
- Modify: `web/src/api/sse.ts`
- Modify: `web/src/types.ts`
- Modify: `web/src/state/chat.ts`
- Modify: `web/src/lib/mapConversationMessages.ts`
- Test: `web/src/state/chat.test.ts` (extend) or new `web/src/state/stop.test.ts`; `web/src/lib/mapConversationMessages.test.ts` (extend)

- [ ] **Step 1: Add `stopped?: boolean` to the assistant message type**

In `web/src/types.ts`, inside `export interface AssistantMessage { ... }` add:
```ts
  stopped?: boolean;
```

- [ ] **Step 2: Add `cancelRun` to `web/src/api/sse.ts`**

```ts
// Stop an in-flight detached run (§13). Best-effort; resolves cancelled=false
// on any non-OK response so the caller can still abort the client stream.
export async function cancelRun(convId: string): Promise<{ cancelled: boolean }> {
  try {
    const res = await fetch(`/api/chat/${convId}/cancel`, { method: "POST" });
    if (!res.ok) return { cancelled: false };
    return (await res.json()) as { cancelled: boolean };
  } catch {
    return { cancelled: false };
  }
}
```

- [ ] **Step 3: Write the failing reducer test**

Add to `web/src/state/chat.test.ts` (match its existing import of the reducer; it already constructs slice states — mirror the surrounding test style). The reducer slice function and action type live in `chat.ts`; this test drives the `STOP` action:
```ts
it("STOP marks the streaming assistant message stopped and idles the slice", () => {
  // Build a slice with a streaming assistant message, then dispatch STOP.
  // (Use the same slice-builder/helpers the other tests in this file use.)
  const start = sliceReducer(
    streamingSliceWithAssistant(),          // existing helper or inline literal
    { type: "STOP" },
  );
  const last = start.messages[start.messages.length - 1] as AssistantMessage;
  expect(last.stopped).toBe(true);
  expect(last.status).toBe("complete");
  expect(start.status).toBe("idle");
});
```
NOTE: read `chat.test.ts` first and reuse its real helper names / slice-builders and the exact reducer export name. If no helper exists, inline a minimal slice literal with one `status:"streaming"` assistant message. Keep assertions as above.

- [ ] **Step 4: Run, verify FAIL**

Run: `cd web && npx vitest run src/state/chat.test.ts -t STOP`
Expected: FAIL — `STOP` not handled.

- [ ] **Step 5: Implement the `STOP` action + `stopStream`**

In `web/src/state/chat.ts`:
1. Add to the slice action union (near `USER_SENT` / `BEGIN_RESUME`):
```ts
  | { type: "STOP" }
```
2. In the slice reducer `switch`, add a `case "STOP":` mirroring the `"done"` case but marking stopped:
```ts
    case "STOP":
      return {
        ...state,
        status: "idle",
        streamingPhase: "idle",
        messages: updateLastAssistant(state.messages, (msg) => ({
          ...msg,
          status: "complete",
          stopped: true,
        })),
      };
```
3. Add `stopStream` in the hook body (near `sendMessage`), and import `cancelRun`:
```ts
  const stopStream = useCallback(
    (convIdOverride?: string | null) => {
      const convId = convIdOverride ?? (active === DRAFT_KEY ? null : active);
      const convKey = convId ?? DRAFT_KEY;
      abortMap.current.get(convKey)?.abort();
      if (convId) void cancelRun(convId);
      dispatch({ type: "SLICE", convId: convKey, action: { type: "STOP" } });
    },
    [active],
  );
```
4. Add `stopStream` to the hook's returned object.

(Use the existing `import { streamChat, streamResume, fetchRunStatus } from "../api/sse";` line — add `cancelRun` to it.)

- [ ] **Step 6: Map `metadata.stopped` on reload**

In `web/src/lib/mapConversationMessages.ts`, where each assistant message is
built (the `role: "assistant"` branch, around the `status: "complete"` field),
add:
```ts
      stopped: ((m.metadata as { stopped?: boolean } | null)?.stopped) ?? undefined,
```
Add a test to `web/src/lib/mapConversationMessages.test.ts`:
```ts
it("maps metadata.stopped onto the assistant message", () => {
  const out = mapConversationMessages({
    mode: "tutor",
    messages: [
      { role: "user", content: "q" },
      { role: "assistant", content: "partial", metadata: { stopped: true } },
    ],
  } as never);
  const assistant = out.find((m) => m.role === "assistant") as AssistantMessage;
  expect(assistant.stopped).toBe(true);
});
```
(Match the real `mapConversationMessages` input shape used by the other tests in
that file — adjust the literal to satisfy its parameter type.)

- [ ] **Step 7: Run frontend tests**

Run: `cd web && npx vitest run src/state/chat.test.ts src/lib/mapConversationMessages.test.ts`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add web/src/api/sse.ts web/src/types.ts web/src/state/chat.ts web/src/lib/mapConversationMessages.ts web/src/state/chat.test.ts web/src/lib/mapConversationMessages.test.ts
git commit -m "feat(web): cancelRun + STOP action + stopStream + reload stopped mapping

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Stop button UI + wiring + Stopped marker

**Files:**
- Modify: `web/src/components/InputBar.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/MessageThread.tsx`
- Test: `web/src/components/InputBar.test.tsx` (create)

- [ ] **Step 1: Write the failing InputBar test**

```tsx
// web/src/components/InputBar.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import InputBar from "./InputBar";

const baseProps = {
  modes: [{ id: "tutor", label: "Tutor", glyph: "T" }],
  onModeChange: () => {},
  onSend: vi.fn(),
};

describe("InputBar stop button", () => {
  it("shows a Stop button while streaming and calls onStop", () => {
    const onStop = vi.fn();
    render(
      <InputBar {...baseProps} activeMode="tutor" isStreaming onStop={onStop} />,
    );
    const stop = screen.getByRole("button", { name: /stop/i });
    fireEvent.click(stop);
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("shows the Send button when not streaming", () => {
    render(
      <InputBar {...baseProps} activeMode="tutor" isStreaming={false} onStop={() => {}} />,
    );
    expect(screen.getByRole("button", { name: /send message/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /stop/i })).toBeNull();
  });
});
```
(If `@testing-library/react` is not a dependency, check `web/package.json`; other
`*.test.tsx` in `web/src/components` already render components — reuse whatever
they import. If they use a different render util, mirror it.)

- [ ] **Step 2: Run, verify FAIL**

Run: `cd web && npx vitest run src/components/InputBar.test.tsx`
Expected: FAIL — no Stop button / prop not supported.

- [ ] **Step 3: Add Stop to `web/src/components/InputBar.tsx`**

Extend `InputBarProps`:
```ts
  isStreaming?: boolean;
  onStop?(): void;
```
Add `isStreaming = false, onStop` to the destructured params. Replace the send
`<button>` block with a conditional:
```tsx
          {isStreaming ? (
            <button
              className="input-bar__send input-bar__stop is-active"
              type="button"
              aria-label="Stop generating"
              onClick={() => onStop?.()}
            >
              <span className="input-bar__stop-square" aria-hidden="true" />
            </button>
          ) : (
            <button
              className={"input-bar__send" + (hasContent && !disabled ? " is-active" : "")}
              type="button"
              aria-label="Send message"
              disabled={!hasContent || disabled}
              onClick={handleSend}
            >
              <IconSend width={16} height={16} />
            </button>
          )}
```
Keep the textarea editable while streaming (do NOT disable it on `isStreaming`;
the existing `disabled` prop is separate — leave it).

- [ ] **Step 4: Run, verify PASS**

Run: `cd web && npx vitest run src/components/InputBar.test.tsx`
Expected: PASS.

- [ ] **Step 5: Wire App → InputBar**

In `web/src/App.tsx`, the `useChat(...)` destructure already exposes `sendMessage`
etc.; add `stopStream` to it. Then on the `<InputBar ... />` element add:
```tsx
              isStreaming={isStreaming}
              onStop={() => stopStream()}
```
(`isStreaming` is already destructured from `useChat`.)

- [ ] **Step 6: Add the "Stopped" pill in `web/src/components/MessageThread.tsx`**

In `AssistantMessageView`, after the message body render, add a marker gated on
`msg.stopped`:
```tsx
      {msg.stopped && <div className="msg__stopped">Stopped</div>}
```
(Place it inside the assistant message container, after the content blocks.
`msg` is the `AssistantMsg` prop already in scope.)

- [ ] **Step 7: Minimal CSS for the stop square + pill**

Append to the stylesheet that holds `.input-bar__send` (find it: `grep -rl "input-bar__send" web/src`). Add:
```css
.input-bar__stop-square { display:inline-block; width:11px; height:11px; border-radius:2px; background: currentColor; }
.msg__stopped { margin-top:6px; font-size:11px; color: var(--text-muted, #888); font-style: italic; }
```
(Use the existing CSS variable names from neighbouring rules if they differ.)

- [ ] **Step 8: Run full frontend suite + typecheck**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: all green, no type errors.

- [ ] **Step 9: Commit**

```bash
git add web/src/components/InputBar.tsx web/src/App.tsx web/src/components/MessageThread.tsx web/src/components/InputBar.test.tsx web/src
git commit -m "feat(web): Stop button while streaming + Stopped marker on partial answers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Backend `runs.cancel` + `POST /cancel` → Task 1. ✔
- Persist partial w/ `{"stopped": true}` on cancel → Task 2. ✔
- `cancelRun` client → Task 3 Step 2. ✔
- `STOP` reducer + `stopStream` (abort + cancelRun + dispatch) → Task 3 Steps 5. ✔
- `stopped` type + reload mapping → Task 3 Steps 1, 6. ✔
- Stop button (Send↔Stop) → Task 4 Steps 3, 5. ✔
- "Stopped" pill → Task 4 Step 6. ✔
- Tests at each layer → Tasks 1-4. ✔
- Idempotent cancel (unknown conv → false) → Task 1 Steps 6. ✔

**Placeholder scan:** none. The "read the file / match existing helpers" NOTEs
(Task 2 Step 3, Task 3 Steps 3/6, Task 4 Step 1) are precise contingencies with
concrete fallbacks, not deferred work — necessary because exact test-helper and
field names live in files the implementer must match.

**Type consistency:** `stopped?: boolean` defined in Task 3 Step 1, consumed in
Task 3 Step 6 (map), Task 4 Step 6 (render). `STOP` action defined + handled in
Task 3 Step 5. `stopStream` defined Task 3 Step 5, used Task 4 Step 5. `cancelRun`
defined Task 3 Step 2, used Task 3 Step 5. `isStreaming`/`onStop` InputBar props
defined Task 4 Step 3, passed Task 4 Step 5. Backend `cancel(conv_id)->bool`
defined Task 1, used by endpoint Task 1 Step 5.

**Note:** `chat_event_gen` is an async generator; cancelling its consuming task
raises `CancelledError` *inside* it, which the new `except asyncio.CancelledError`
catches to persist before re-raising. The detached-run driver (`runs._drive`)
cancels exactly this task via `run.task.cancel()`, so the path is exercised end
to end (Task 2 test simulates it directly).
