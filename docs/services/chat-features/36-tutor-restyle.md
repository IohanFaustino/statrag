# 36 — Tutor view restyle: red accents, collapsible sources, Claude-Code thinking

## Purpose

Three small UX changes to assistant responses:

1. **Blue → red** in the structured `TutorView`. The component shipped with `#38bdf8` (sky blue) hardcoded as a fallback for `--accent`, so titles, citation pills, source numbers and math borders rendered blue even in dark-red mode.
2. **Sources panel becomes a toggle list**. The `Sources` block at the bottom of a tutor answer is now collapsible (click to expand / click to collapse). Default state is collapsed — the count is shown next to the label.
3. **Claude-Code-style thinking indicator**. The bouncing-dots pill on `Thinking…` is replaced with an italic muted single-line label + ticking ellipsis, matching Claude Code's idle "thinking" affordance.

## Where it lives

- `web/src/styles/tutor.css`
  - `.tutor-view__h2` — fallback color `#38bdf8` → `#E5484D`
  - `.tutor-view__math-block` — background + border swapped to `rgba(229, 72, 77, …)` / `#E5484D`
  - `.tutor-view__pill`, `.tutor-view__pill:hover`, `.tutor-view__pill--hover` — red
  - `.tutor-view__sources-title`, `.tutor-view__src-num` — red
  - `.tutor-view__src--hover` background — `rgba(229, 72, 77, 0.06)`
  - **new**: `.tutor-view__sources-toggle`, `.tutor-view__sources-chevron`, `.tutor-view__sources-chevron--open`, `.tutor-view__sources-count`
- `web/src/components/views/TutorView.tsx`
  - `useState` flag `sourcesOpen` (default `false`)
  - Sources `<h3>` replaced with a `<button>` carrying a `›` chevron that rotates 90° on open, the label `Sources`, and the citation count
  - The `<ol>` list renders only when `sourcesOpen === true`
- `web/src/components/MessageThread.tsx`
  - `msg__pending msg__pending--motion` block (3 dots + uppercase label) replaced with a `msg__thinking` span: italic `Thinking` + 3 sequentially-revealed dots
- `web/src/styles/app.css`
  - **new**: `.msg__thinking`, `.msg__thinking-lbl`, `.msg__thinking-ell`, `@keyframes thinking-ell`
  - Old `.msg__pending--motion` / `.thread__streaming-dot` rules kept (still used elsewhere)

## Scope notes

- Only the **tutor view** is recolored. Theme tokens (`--accent-primary` in light/dark themes) and the rest of the UI are untouched. The light-theme navy `#1E3A8A` is unchanged.
- The sources toggle only affects the structured `TutorAnswer` panel inside an assistant message. The `ContextPanel` side rail and the inline `SourceChip` row are unaffected.
- The new thinking indicator fires for both `status === "pending"` and the `streamingPhase === "thinking"` window of the last assistant message — same trigger logic as before, only the visuals changed.

## Verify

```bash
cd web && npx tsc --noEmit && npx vite build
```

Both pass. Visual check: `./scripts/dev.sh`, ask a tutor-mode question, confirm (a) titles + citation pills + source numbers are red, (b) `› Sources (N)` row toggles the list, (c) the "Thinking" affordance is italic muted text with a ticking ellipsis.
