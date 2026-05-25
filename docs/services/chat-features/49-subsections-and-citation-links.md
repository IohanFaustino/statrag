# 49 · Subsection headers + citation hyperlinks

**Status:** ✓ Complete (2026-05-22)
**Common ground:** `docs/common ground/Elements/index.html` §12

## Problem

Three refinements after §11/§48:
1. **References didn't connect to the Sources panel.** Up to 6 references rendered, but clicking a `[N]` marker didn't reliably open/scroll the Sources panel.
2. **Bullets instead of subsections.** Aspect bodies used bullet lists; the user wants left-aligned subsection headers (no toggle), one per perspective — e.g. Definition → concepts + formulas, then an "MSE" header tying everything to the error term.
3. **Active model switched to deepseek.**

## Block F — citation hyperlinks

Two root causes:
- Clicking a `[N]` pill set `location.hash = #cite-N`; a *repeat* click fired no `hashchange`, so the listener never re-opened/scrolled.
- Under-citing models (especially via the deepseek router) emitted inline `[N]` markers with no matching `citations` entry → the pill's `present` check failed → nothing happened.

Fixes:
- **Server** `_ensure_marker_citations(text, enriched, sources)` (`deep_tutor.py`): scans the assembled text for `[N]` markers and guarantees each has a citation entry with `index==N`, synthesizing missing ones from `sources` in marker-appearance order (clamped to the last source). Runs after `_reconcile_citations` in `_convert_to_tutor_answer`.
- **Frontend** (`TutorView.tsx`): the `[N]` pill now has an explicit `onClick` (`onCite`) that opens the Sources panel, syncs the hash via `replaceState`, and scrolls/highlights `#cite-N` — independent of hash state. Threaded through all `renderInlineWithCites` call sites.
- Router parse hardened (§48 carry-over) to salvage partial payloads.

## Block G — left-aligned subsection headers

- **Prompt** (`prompts/deep_tutor.py`): `<structure>` rewritten — aspect bodies use `### ` subsection headers, NOT bullet lists; each header names one perspective. Definition spec mandates `### <component>` per named component + a required `### MSE` (central quantity: decomposition + how each component affects the error term). Applications → `### <cited case>`; example_intuition → `### ` per case + `### The intuition`.
- **Frontend** (`TutorView.tsx`): `splitIntoBlocks` parses `### ` → `h3` block; `renderBlock` renders it as a left-aligned `<h3 className="tutor-view__h3">` (no toggle). `groupSections` keeps `h3` in the section body — only `## ` (h2) starts a collapsible section.

## deepseek note

User set the active model to `deepseek-v4-pro`. In this environment that id is **unreachable** at the live deepseek API — the draft stream returns empty / hangs (~120s timeout), falling back (or erroring for the single workflow). Both refinements are prompt + frontend, **provider-independent**, and were verified on the working OpenAI model. To actually run on deepseek, set `DEEPSEEK_MODEL` to a reachable id (e.g. `deepseek-chat` / `deepseek-reasoner`).

## Verification (2026-05-22)

Browser on :5175 (bias-variance): Definition rendered `### Bias / ### Variance / ### MSE` with `MSE = bias²+variance+σ²`; Example & Intuition rendered per-case subsections + "The intuition here is…"; Applications rendered cited cases (Ridge vs. OLS on the prostate data, smoothing-spline on the wage data, double descent). Clicking `[1]` opened the Sources panel and highlighted reference [1]. Inline markers 1-4 all had matching citations.

Tests: backend `test_ensure_marker_citations_fills_gaps`/`_noop_without_sources`, `test_structure_requires_subsection_headers`, updated `test_definition_framing_and_buildup_contract`; frontend `splitIntoBlocks — §12 ### subsection headers`. 551 backend / tsc / 40 vitest green. Invariant 24.
