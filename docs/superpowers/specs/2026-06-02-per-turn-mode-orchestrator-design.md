# Per-Turn Mode Orchestrator — Design

**Date:** 2026-06-02
**Status:** Approved (brainstorm)
**Scope:** chat backend (per-turn mode persistence) + frontend (per-message mode, picker behaviour)
**Hindsight:** `docs/superpowers/hindsight/2026-06-02-mode-orchestrator-options.md` (bank claude-code; Gen-AI-LangChain ch.3/5/6, Agentic Patterns ch.14/15)

## Problem

A user starts a conversation in `tutor`, switches the picker to `facilitate`, sends — and it runs `tutor` again. Two causes, both confirmed from the DB (`conversations.mode` is per-conversation; assistant rows show the wrong mode after a switch):

1. **`pickOpenedMode` resets the picker** to the conversation's *creation* mode whenever the conversation is opened/re-selected (sidebar click, `/c/<id>` deep-link, popstate). A deliberate mid-conversation switch gets clobbered back to the original mode, so the next send carries the old mode.
2. **Mode is conversation-level, not per-turn.** Messages have no mode field; `mapConversationMessages` stamps the single `conversation.mode` on every assistant message. A `facilitate` turn 2 reloads displayed (and effectively treated) as the creation mode.

The backend dispatch (`router._V2_DISPATCH`, built in the orchestration-hardening pass) already routes correctly by `req.mode` — the gap is entirely **per-turn mode state + the frontend picker reset**.

## Goal

One conversation can contain turns of different modes (tutor, qa, facilitate, resume). Each turn runs the mode selected at send time, is persisted with that mode, and reloads showing the correct per-turn pipeline. The picker selects the *next* turn's mode and is never silently overridden after the user changes it.

## Approach (chosen) — per-message mode, routed by the existing dispatch table

Grounded in the hindsight digest:
- **Typed-state dispatch** (Agentic ch.15 `LoanGraphState` + conditional edges) ≈ `_V2_DISPATCH` routing by `req.mode` — already in place.
- **Per-turn namespaced state** (Gen-AI-LangChain ch.6 `InMemoryStore`) ≈ persist mode per message.
- **Explicit error edges, no silent fallback** (Agentic ch.15 `check_error`) ≈ the `MODE_NOT_ROUTED` / `MODE_NOT_REGISTERED` loud-fail already shipped.

Rejected: a full LangGraph mode-router node (large refactor; the dispatch table already routes); an auto-classify LLM router (added latency + failure mode; user chose manual per-turn).

## Components

### Backend

**`src/services/chat/api.py::chat_event_gen` — persist the turn's mode.**
The `_persist_assistant(stopped)` helper currently writes `metadata=collected_meta` (or `{**collected_meta, "stopped": True}`). Add the request mode to the persisted metadata in BOTH the normal and cancel paths:
```python
metadata = {**(collected_meta or {}), "mode": req.mode}
if stopped:
    metadata["stopped"] = True
```
`req.mode` is the authoritative pipeline that ran (the dispatch key). This is distinct from any `retrieval_meta.mode` string (which is a human-readable retrieval descriptor, e.g. "hybrid (RRF…) | deep_tutor v2").

### Frontend

**`web/src/lib/mapConversationMessages.ts` — per-message mode on reload.**
Where each assistant message is built, set its mode from the row's own metadata, falling back to the conversation mode for legacy rows:
```ts
mode: ((m.metadata as { mode?: string } | null)?.mode) ?? convMode,
```
(`convMode` is the conversation-level mode already derived in the file.) This replaces the unconditional `convMode` stamp so each turn keeps the mode it actually ran.

**`web/src/App.tsx` — picker syncs once per conversation switch, never clobbers a manual change.**
Replace the current `handleSelectConv` behaviour (`setActiveMode(pickOpenedMode(data.mode, …))` on every open) with a **one-shot sync keyed on conversation identity**:
- Track the last conversation whose mode we synced (`lastSyncedConvRef`).
- When opening a conversation whose id differs from `lastSyncedConvRef.current`, set `activeMode` to that conversation's **last-turn mode** (the mode of its most recent assistant message, falling back to `conversation.mode`), then record the id.
- Opening the *same* conversation again (popstate, re-render, re-select) does NOT re-sync — so a mode the user picked mid-conversation survives.

This keeps the helpful "continue in the same mode" default on a real switch, without fighting deliberate switches. `pickOpenedMode` is repurposed/replaced by this guarded sync (drop the unconditional call).

**Per-turn display** — `MessageThread` already renders each assistant message by `msg.mode` (icon/label + the structured card by schema). With per-message mode now correct, a single thread shows a tutor answer, then a facilitate digest, etc., each with its own header. No new rendering code; verify the existing path.

## Data flow (one conversation, mixed modes)

```
turn N: picker = facilitate → send → body.mode = facilitate (activeMode, unclobbered)
  → router._V2_DISPATCH["facilitate"] → run_facilitate
  → chat_event_gen persists assistant row metadata.mode = "facilitate"
turn N+1: picker = qa → … metadata.mode = "qa"
reload: mapConversationMessages → each assistant msg.mode from its own metadata
open conv: picker synced once to last-turn mode; user may switch freely thereafter
```

## Error handling

- Legacy assistant rows (no `metadata.mode`) fall back to the conversation mode — no crash, correct enough.
- Unknown mode is impossible past the `ModeId` Literal (422 at the API boundary) and is loud-failed in the router/orchestrator (already shipped).
- The one-shot picker sync degrades to the conversation mode if no assistant message exists yet.

## Testing (functional — any provider, incl. kimi/ollama)

**Backend** (`src/services/chat/tests/`):
- `chat_event_gen` persists `metadata["mode"] == req.mode` for a normal turn, and on cancel keeps both `mode` and `stopped`.
- A parametrized check over all `ModeId`s: each mode's persisted metadata carries that mode.

**Frontend** (`web/src`):
- `mapConversationMessages`: an assistant row with `metadata.mode="facilitate"` in a `conversation.mode="tutor"` conversation maps to `msg.mode==="facilitate"`; a legacy row (no metadata.mode) falls back to `convMode`.
- Picker sync: opening a *different* conversation sets the picker to its last-turn mode; opening the *same* one again does not override a user-changed mode (reducer/helper-level unit test of the guarded sync).

**Functional E2E (the "final test", any model):** a scripted sequence against `/api/chat` in ONE conversation — tutor → facilitate → qa → resume — asserting each turn's `meta.mode` echo equals the requested mode and the emitted `structured_output.schema` matches (TutorAnswer / QAAnswer / FacilitateDigest / ChapterDigest). Provider-agnostic (works with kimi/ollama). Proves multi-mode coexistence functionally. (Browser click-through deferred — the Chrome extension is offline.)

## Out of scope (YAGNI)

- Auto mode-classification ("Auto" picker option) — deferred (Approach 3 in the hindsight digest).
- Migrating the chat to a LangGraph `StateGraph` (Approach 2) — the dispatch table already routes.
- Changing the backend routing/dispatch (already correct + hardened).
- Per-stage model overrides, cancel, clarify — untouched.
