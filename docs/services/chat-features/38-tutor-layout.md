# 38 — Tutor view layout: justified text, centered headings, math cleanup, per-section toggle

## Changes

1. **Justified paragraphs** — body text in `TutorView` now uses `text-align: justify` (with `hyphens: auto`) so both edges align.
2. **Centered section titles** — `## H2` headings are horizontally centered with a centered chevron toggle.
3. **Math block cleanup** — removed the inline `<span class="math-block__tag">MATH</span>` and the `.math-block::before` "math" badge. The KaTeX-rendered formula is now centered inside the block via `text-align: center` on the container + `.katex-display`.
4. **Per-section toggle** — every `## H2` section (not only Sources) is collapsible. Click the heading to collapse/expand the body of that section.

> **Update 2026-05-19**: defaults inverted. All sections now render **collapsed** except TL;DR which auto-expands on first mount. Rationale: with the multi-aspect schema (feature 36) and inline figures (feature 39, 40), an all-open default produced a 1500-word wall of text on every answer. TL;DR auto-expand gives an immediate readable signal and preserves the collapse benefit for the deeper aspects.

5. **Section body animation** — body is now always-mounted in a `tutor-view__section-body-wrapper` with `max-height` + `opacity` transitions (220 ms ease-out enter, 220 ms ease-in exit; chevron rotates 0° → 90° over 180 ms). `prefers-reduced-motion: reduce` zeroes transitions per CSS override. UX-validated against `ui-ux-pro-max` skill (timing 150–300 ms; exit-faster-than-enter pattern).

## Where it lives

- `web/src/components/views/TutorView.tsx`
  - `groupSections(blocks)` helper splits the flat block list into `{ title, body }[]` sections at each `h2`.
  - `useState<Set<number>>` of *open* section indices (post-2026-05-19 inversion), seeded with the index of the section whose title is `"TL;DR"` via a lazy initialiser.
  - Each section renders a `<button class="tutor-view__h2 tutor-view__h2--toggle">` with a rotating `▸` chevron; body lives in an always-mounted `<div class="tutor-view__section-body-wrapper">` with inline `max-height` + `opacity` + `transition` style.
  - `useEffect` hashchange handler opens every section when URL hash matches `#fig-N` so inline figures are scrollable.
  - Lead (pre-first-heading) blocks render in a `tutor-view__section--lead` wrapper without a toggle.
- `web/src/components/Math.tsx`
  - Removed the `<span className="math-block__tag">MATH</span>` element.
- `web/src/styles/app.css`
  - `.math-block`: `text-align: center` + `.katex-display { text-align: center }`.
  - Dropped the `.math-block::before { content: "math" }` rule.
- `web/src/styles/tutor.css`
  - `.tutor-view__para`: `text-align: justify; hyphens: auto`.
  - `.tutor-view__h2`: `text-align: center`.
  - New: `.tutor-view__h2--toggle`, `.tutor-view__h2-chevron`, `.tutor-view__h2-chevron--open`, `.tutor-view__h2-text`, `.tutor-view__section`, `.tutor-view__section--lead`, `.tutor-view__section-body`.
  - `@media (prefers-reduced-motion: reduce)` → `.tutor-view__section-body-wrapper` + `.tutor-view__chevron` get `transition-duration: 0ms !important`.

## Verify

```bash
cd web && npx tsc --noEmit && npx vite build
```

In the browser (with dev server on `localhost:5175` via vite HMR), open any tutor answer that has multiple `## H2` sections. Confirm:

- Paragraphs justify on both edges.
- Section titles are centered with a `›` chevron that rotates `90°` when the section is open.
- Clicking a heading collapses/expands only that section's body.
- Math blocks no longer show the word "MATH" or the small "math" badge; the formula sits centered inside the bordered box.
