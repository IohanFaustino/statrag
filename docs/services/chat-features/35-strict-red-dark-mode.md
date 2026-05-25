# 35 — Strict-red dark mode + IconBook swap

## Purpose

Dark theme previously mixed an electric blue (`#3FA9FF`) accent with red highlights, which read as inconsistent. Dark mode is now uniformly red. Light theme is unchanged (cobalt navy retained).

## Where it lives

- `web/src/styles/neon.css` — every `rgba(63, 169, 255, …)` swapped for `rgba(229, 72, 77, …)`.
- `web/src/styles/app.css` — same global swap; also includes border/glow/hover states.
- `web/src/components/ContextPanel.tsx` — inline color literals updated.
- `web/src/components/MessageThread.tsx` — inline color literals updated.
- `web/src/components/Topbar.tsx` — books button icon: `IconLogo` replaced with `IconBook` (matches the `Books` semantics; logo SVG no longer rendered inline next to a label that already says "Books").

## Swap rule

```
rgba(63, 169, 255, X)  →  rgba(229, 72, 77, X)
```

Applied across all opacities (`0.10`, `0.26`, `0.45`, `0.15`, …). The light-theme branch in `tokens.css` is untouched.

## What stays blue

- Nothing in dark mode.
- Light-theme cobalt navy (`#001F3F`) is preserved per the design's "financial paper" mood.

## User-facing behavior

- Borders, glows, focus rings, link hovers, and ContextPanel/MessageThread chrome are now red in dark mode.
- The books button in the topbar shows a book icon (open book glyph) instead of the statrag logo mark.
- Light mode looks identical to before.
