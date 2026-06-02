# Cancel a Streaming Turn (Stop button) — Design

**Date:** 2026-06-02
**Status:** Approved (brainstorm)
**Scope:** chat backend (detached run cancel + partial persist) + frontend (Stop button)

## Problem

After sending a prompt there is no way to stop generation. The send runs as a
**detached server run** (`runs.start_run`), so even closing the tab keeps the
server generating and persisting the full answer. Users want a ChatGPT-style
**Stop** button that actually halts generation and keeps whatever was produced
so far.

## Decisions (approved)

- **Full cancel** — stop server generation too (not just the client stream).
- **Keep the partial** — persist the partial answer with a "stopped" marker.

## Architecture

```
Stop button (while streaming)
  → client: abort the conversation's AbortController (stops reading SSE)
  → client: POST /api/chat/{conv_id}/cancel
       → runs.cancel(conv_id): run.task.cancel()
            → CancelledError propagates into chat_event_gen's stream loop
            → chat_event_gen persists the PARTIAL assistant text with
              metadata {"stopped": true}, then the run finalizes (done)
  → client: mark the in-flight assistant message stopped (keep partial tokens)
On reload: persisted partial renders with a "Stopped" marker.
```

## Components

### Backend

**1. `src/services/chat/runs.py` — `cancel(conv_id) -> bool`**
```python
def cancel(conv_id: str) -> bool:
    """Cancel an active run's task. Returns True if a live run was cancelled."""
    run = _runs.get(conv_id)
    if run is None or run.done or run.task is None:
        return False
    run.task.cancel()
    return True
```
(`_drive`'s existing `finally` already sets `run.done` + emits `_DONE` to
subscribers when the task is cancelled — no change needed there.)

**2. `src/services/chat/api.py` — `POST /api/chat/{conv_id}/cancel`**
```python
@app.post("/api/chat/{conv_id}/cancel")
async def chat_cancel(conv_id: str) -> dict:
    """Stop an in-flight detached run. Idempotent: returns cancelled=False when
    no active run exists."""
    return {"cancelled": runs.cancel(conv_id)}
```

**3. `src/services/chat/api.py::chat_event_gen` — persist partial on cancel**

Today persistence happens once after the `async for ev in stream_chat(...)`
loop. Factor the persist block into a local helper and call it from BOTH the
normal path and a `CancelledError` handler, tagging the cancelled case:

```python
def _persist(stopped: bool) -> None:
    if not (req.conversationId and (structured_payload or assistant_text_buf)):
        return
    md = {"stopped": True} if stopped else None
    content = structured_payload if structured_payload else "".join(assistant_text_buf)
    store.append_message(
        conversation_id=req.conversationId, role="assistant",
        content=content, sources=..., figures=..., metadata=md,
    )  # mirror the existing append_message call's args exactly

try:
    async for ev in stream_chat(req, history=history):
        ...accumulate as today...
        yield ev
except asyncio.CancelledError:
    _persist(stopped=True)
    raise          # let runs._drive finalize the run
else:
    _persist(stopped=False)
```
The exact `append_message` argument shape (sources/figures serialization) must
match the current call — read it and reuse verbatim; only `metadata` and the
call site change. Persistence stays best-effort (existing `try/except`).

NOTE: the implementer must confirm whether the current code persists the
structured payload vs the text buffer and replicate that logic in `_persist`.

### Frontend

**4. `web/src/api/sse.ts` — `cancelRun`**
```ts
export async function cancelRun(convId: string): Promise<{ cancelled: boolean }> {
  const res = await fetch(`/api/chat/${convId}/cancel`, { method: "POST" });
  if (!res.ok) return { cancelled: false };
  return res.json();
}
```

**5. `web/src/state/chat.ts`**
- New reducer action `STOP` (slice): set the streaming assistant message
  `stopped = true`, its `status = "complete"`, and the slice `status = "complete"`.
- `stopStream(convIdOverride?)`: resolve the conv key, `abortMap.current.get(key)?.abort()`,
  fire-and-forget `cancelRun(realConvId)` (skip when key is the draft / no conv),
  dispatch `STOP`. Expose `stopStream` from the hook return.
- `LOAD_CONVERSATION` / `mapConversationMessages`: read `metadata.stopped` →
  set message `stopped`.

**6. `web/src/types.ts`** — add `stopped?: boolean` to the assistant message type.

**7. `web/src/components/InputBar.tsx`** — accept `isStreaming: boolean` and
`onStop(): void`. While `isStreaming`, render a **Stop** button (square glyph)
in place of Send that calls `onStop()`; the textarea stays editable so the user
can immediately retype. (Today the send button is merely disabled while
streaming.)

**8. `web/src/App.tsx`** — pass `isStreaming={isStreaming}` and
`onStop={stopStream}` to `InputBar`.

**9. `web/src/components/MessageThread.tsx`** — when an assistant message has
`stopped`, render a small muted "Stopped" pill under its content.

## Data flow / states

- Streaming → user clicks Stop → client aborts read + POSTs cancel + marks msg
  stopped (keeps partial already received). Server cancels task, persists the
  server-side partial with `{"stopped": true}`.
- Idempotent: clicking Stop when nothing is active, or a race where the run just
  finished, returns `cancelled=false` and the client STOP is a harmless no-op.

## Error handling

- `cancelRun` network failure → ignored; the client already aborted locally, so
  the UI still stops. (Worst case the server finishes; acceptable — the button
  still gives immediate UI feedback.)
- `CancelledError` persist is best-effort inside the existing `try/except`; a
  persist failure never breaks cancellation.
- No new SSE event types; cancel uses a separate POST, not the stream.

## Testing

**Backend** (`src/services/chat/tests/`):
- `runs.cancel`: active run → task cancelled + returns True; no/finished run →
  False. (Drive a controllable async source, cancel mid-stream, assert
  `run.done` and `is_active` False.)
- `chat_event_gen` cancel path: feed a source that yields a couple of tokens
  then awaits forever; cancel the driving task; assert `store.append_message`
  was called with `metadata={"stopped": True}` and the partial content.
- `POST /api/chat/{conv_id}/cancel` returns `{"cancelled": false}` for an
  unknown conv (endpoint smoke via FastAPI TestClient).

**Frontend** (`web/src`):
- reducer `STOP` marks the streaming assistant message `stopped` and sets slice
  status complete.
- `InputBar` renders a Stop button while `isStreaming` and calls `onStop`
  (not `onSend`); renders Send otherwise.
- `cancelRun` POSTs to `/api/chat/{id}/cancel`.
- `mapConversationMessages` maps `metadata.stopped` → message `stopped`.
- `MessageThread` shows the "Stopped" pill when `stopped`.

## Out of scope (YAGNI)

- Regenerate/retry button (separate feature).
- Cancelling the connection-bound (no-conversationId) path — it is already
  request-coupled, so the client abort stops it; no backend cancel needed there.
- Keyboard shortcut for stop.
