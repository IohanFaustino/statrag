# 31 — Streaming motion: pending pill, caret, formatting shimmer

## Purpose

Visual cues that make the SSE pipeline feel alive. Three distinct affordances cover the three phases a streamed assistant turn passes through: waiting for the first token, mid-paragraph streaming, and structured-mode parsing.

## Where it lives

- `web/src/components/MessageThread.tsx` — renders the three states.
- `web/src/styles/app.css` — `msg__pending--motion`, `msg__caret`, `msg__formatting` selectors + keyframes.
- `web/src/state/chat.ts` — `streamingPhase` drives which affordance is active.

## 1. Thinking pill

Before the first `token` event arrives, the assistant bubble shows a small "Thinking…" pill with three bouncing red dots.

```css
.msg__pending--motion .dot { animation: bounce 1.1s infinite; background: var(--accent-danger); }
```

Disappears as soon as the first token is appended to the trailing `p` block.

## 2. Typing caret

Once tokens flow, the currently-streaming paragraph renders a blinking caret (`msg__caret`) at its tail. The caret is appended as an inline element inside the last `p` block while `streamingPhase === "writing"`. It is removed by the reducer when `done` fires.

```css
.msg__caret { display: inline-block; width: 6px; height: 1.05em; background: var(--accent-danger); animation: caret-blink 0.9s steps(2) infinite; }
```

## 3. Formatting shimmer

Structured modes (tutor, quiz, figures, compare, navigate, prereqs, annotate, research, path, roadmap) stream raw JSON tokens that should not be shown to the user. While those modes are running, MessageThread substitutes the trailing `p` block with a shimmer placeholder ("Formatting response…") and hides the raw token stream.

```tsx
const isStructured = STRUCTURED_MODES.has(activeMode);
if (isStructured && !msg.structuredOutput && streamingPhase !== "done") {
  return <div className="msg__formatting">Formatting response…</div>;
}
```

When the `structured_output` SSE event lands, the shimmer is replaced by the appropriate mode view (`views/*`).

## User-facing behavior

- Pre-token wait now reads as deliberate rather than stalled.
- Caret makes streamed prose unambiguously distinct from finished prose.
- Structured modes no longer briefly flash JSON before resolving.
