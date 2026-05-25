# 30 — Stats pill (topbar)

## Purpose

Live indicator in the topbar that surfaces stream progress without opening the context panel. Shows phase, elapsed wall-clock, and a running token-count estimate. Pulses red while a stream is in flight.

## Where it lives

- `web/src/components/Topbar.tsx` — `StatsPill` subcomponent + topbar mount point.
- `web/src/state/chat.ts` — `streamingPhase` field (`"idle" | "thinking" | "writing" | "done"`) on `ChatState`; updated by the reducer.
- Backend: orchestrator emits a `usage` SSE event carrying running token counts; the reducer applies it to `state.usage`.
- Styles: `web/src/styles/app.css` (`.stats-pill`, `.stats-pill--pulse`).

## Phases

| Phase | Trigger | Visible label |
|---|---|---|
| `idle` | no active stream | hidden / neutral |
| `thinking` | `USER_SENT` dispatched, no `token` yet | "thinking…" |
| `writing` | first `token` event arrives | "writing" |
| `done` | `done` event or non-error completion | "done" (fades) |

The pill pulses red (`--accent-danger` glow) during `thinking` + `writing`, then stops on `done`.

## Token + duration

- Duration: `performance.now() - startedAt`, formatted as `Xs` or `M:SS`.
- Tokens: `state.usage.tokens` (from the `usage` SSE event); approximate, updated as new chunks arrive.

## User-facing behavior

- Always visible in the topbar between the books button and the theme toggle.
- One pill per active assistant turn; resets on next user send.
- No interaction — purely informational.
