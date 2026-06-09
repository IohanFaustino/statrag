# Extension Mode — Quality & Performance Rebuild Design

**Date:** 2026-06-09
**Branch:** `worktree-feat+extension-mode`
**Scope:** `src/services/chat/agents/extension_agents/` + `extension_skills/` + `web/src/` Extension components only. Zero changes to shared router, tutor, QA, or facilitate code.

---

## Goal

End-to-end quality improvement for Extension mode across five layers: prompts, math/text processing, retrieval, model tiers, and frontend. The core invariant (footnote-only augmentation) and the topology-C architecture are preserved. No new providers or shared-infra changes.

---

## Layer 1 — Prompts & Agent Behavior

### Problems

| Symptom | Root cause |
|---|---|
| Polish leaked Polish (non-English) in live test | `ENGLISH` rule is one line, no examples, no consequences |
| Only 2/10 footnotes filled | Analyst gaps too vague → orchestrator plans weak queries |
| Augmentor over-rejects candidates | Fit-judgement undefined ("discard if off-topic") |
| Points emitted with 0 footnotes silently | No density target in orchestrator prompt |
| Orphan footnotes (written to FS but not attached to point) lost | Judge/orchestrator has no orphan-merge instruction |
| `COVERAGE: <query> = done\|unfilled` format drifts | No canonical format enforced in prompt |

### Changes

**`ORCHESTRATOR_PROMPT`**
- Add explicit footnote density rule: "Every non-trivial point MUST have ≥ 2 footnotes. A point with 0 footnotes after the augmentor ran is a pipeline failure — re-delegate the augmentor for that point."
- Add orphan-footnote merge step: "Before building the ExtensionDigest, check `/footnotes/*.md` for footnotes whose point title does not match any curated point. Attach them to the nearest point by title similarity."
- Strengthen ENGLISH: add explicit instruction "If source text is not in English, translate every field to English before writing. Do not write any word in any language other than English."
- Add `COVERAGE` format spec: "End every footnote file with `# COVERAGE: <query> = done` or `# COVERAGE: <query> = unfilled`. Exact format, no variation."

**`ANALYST_PROMPT`**
- Replace vague "MISSING:" description with a 4-type gap taxonomy:
  1. **Formal definition absent** — concept named but never formally defined
  2. **Formula derivation missing** — result stated but derivation or intuition absent
  3. **Comparative context** — no comparison to related methods/concepts from other books
  4. **Application example** — no concrete worked example or use case
- Require ≥ 2 gaps per section (or explicitly state "no gaps found" with justification).
- Add example gap entries to prevent vague outputs.

**`AUGMENTOR_PROMPT`**
- Add fit-judgement rubric: "Score relevance 1–5 before writing. Score 1–2: discard. Score 3–5: write footnote. A score of 3 requires at least one concrete formula or factual claim; do not footnote vague overlap."
- Add LaTeX format examples: `$E[X] = \mu$` for inline, `$$\text{Var}(X) = E[X^2] - (E[X])^2$$` for display (own line).
- Add minimum footnote body length: ≥ 40 words; a one-sentence footnote is not useful.
- Reinforce COVERAGE format: "End the file with `# COVERAGE: <query> = done|unfilled` for every query you received."

**`POLISH_PROMPT`**
- Replace "not a summary" emphasis with: "Keep formal structure, definitions, and notation from the source. Curate by removing exercises, worked solutions, and redundant restatements. The result should read as a complete treatment of the concept, not a synopsis."

**`JUDGE_PROMPT`**
- Add orphan-footnote merge step (mirrors orchestrator instruction).
- Add pre-emit ENGLISH check: "Before emitting the ExtensionDigest, verify all `curated_text` and `body` fields are in English. If any field is not, translate it."
- Clarify: judge reads coverage markers, maps to point titles — add explicit mapping instruction.

---

## Layer 2 — Math & Text Processing (`runner.py`)

### Problems

| Issue | Impact |
|---|---|
| `\(…\)` / `\[…\]` LaTeX pass through raw | KaTeX renders them as literal text |
| Markdown `[^n]` markers show as literal `[^1]` | Footnote markers broken in React |
| `_filter_subtopics` exact string match | "Chebyshev" misses "7.4 Chebyshev Inequality" |
| `EXTENSION_SECTION_CHARS=1200` too low | Orchestrator loses section context, produces weaker gap queries |

### Changes

**Add `_normalize_math_delimiters(text: str) -> str`**
- `\(...\)` → `$...$` (inline)
- `\[...\]` → `$$...$$` placed on its own line
- Applied to every `curated_text` and footnote `body` before emit (same position as existing `_isolate_midline_display` call — chain after it)

**Add `_strip_md_footnote_markers(text: str) -> str`**
- Remove `[^N]` marker syntax (renders as literal in React — footnotes have their own `marker` field)
- Applied to `curated_text` only (footnote bodies don't use `[^N]`)

**Improve `_filter_subtopics`**
- Current: simple `any(needle in h2_path.lower())` string match
- New: try string match first; if no match found, fall back to `hybrid_search(subtopic, book_slugs=[book], top_k=3)` and keep sections whose `section_id` appears in results. If still no match, return all sections (existing fallback preserved).

**Raise `EXTENSION_SECTION_CHARS` default**
- 1200 → 2500 chars. Still truncates to avoid TPM blowout on 15-section chapters, but gives the orchestrator meaningful context per section.

---

## Layer 3 — Retrieval Quality (`tools.py`)

### Problems

| Issue | Impact |
|---|---|
| `wikipedia_lookup` uses blocking `httpx.get` | Blocks asyncio event loop inside worker thread |
| Wikipedia title encoding: exact match only | Multi-word or non-canonical queries → 404, no fallback |
| `retrieve_corpus top_k=6` small candidate set | Augmentor sees few candidates, over-rejects |
| No cross-round dedup | Same passage returned in round 2+, duplicate footnotes |

### Changes

**`wikipedia_lookup`**
- Replace `httpx.get` with `asyncio.to_thread(httpx.get, …)` (tool is called inside a worker thread already; `to_thread` ensures it doesn't block the LangChain executor)
- Add disambiguation fallback: if first title 404s, retry with `Special:Search` REST endpoint (`/w/api.php?action=query&list=search&srsearch=<query>&format=json`) — take the first result's title and re-fetch summary

**`retrieve_corpus`**
- Raise `top_k` 6 → 10
- Accept optional `seen_ids: set[str]` param — filter out `chunk_id`s already seen in prior rounds before returning results
- `_fmt_sources` already formats correctly; dedup is purely at the ID level

**Runner integration for dedup**
- `run_extension` maintains a `seen_chunk_ids: set[str]` per request
- Passes it into `make_retrieve_corpus(…, seen_ids=seen_chunk_ids)` on each round
- `retrieve_corpus` tool closure captures the mutable set — additions in round 1 are visible in round 2

---

## Layer 4 — Model Tiers (`_models.py`, `agent.py`)

**Scoped to `extension_agents/` only. No changes to shared router or other modes.**

### Problems

| Stage | Current model | Issue |
|---|---|---|
| Judge | `_TOP` (`gpt-5.4-2026-03-17`) | Overkill — judge only parses COVERAGE markers + re-delegates |
| Polish | `_CHEAP` (`nano`), temp=0.0 | Mechanical, repetitive curation |
| Augmentor | `_CHEAP` (`nano`), temp=0.0 | Flat, formulaic footnote prose |

### Changes

**`_models.py`**
- Introduce `_MID = settings.openai_model_nano` alias (same model today, but semantically separated from `_CHEAP` so a future bump only changes one line)
- Judge default: `_TOP` → `_CHEAP` (nano) — parsing COVERAGE lines + re-delegating is a bounded task
- Polish: keep nano, raise temperature `0.0` → `0.3` in `_lc_model`
- Augmentor: keep nano, raise temperature `0.0` → `0.2`
- Orchestrator: stays `_TOP`, temperature stays `0.0` (open reasoning, needs consistency)

**New env flag: `EXTENSION_JUDGE_MODEL`**
- Overrides judge stage model independently of orchestrator
- Default: `""` → resolves to `_CHEAP`
- Useful for A/B testing judge quality without touching orchestrator

**`agent.py`**
- Pass temperature per-stage in `_lc_model` — add `temperature` param

---

## Layer 5 — Frontend Streaming + UX

### Problems

| Issue | Impact |
|---|---|
| `stage{point}` SSE events exist but ignored | All points appear at once — no incremental feedback |
| `renderInlineWithCites` used for footnote bodies | Designed for tutor `[N]` citations; mismatch |
| `fn.source` untruncated | Long section paths are visual noise |
| Download button: no loading/error feedback | Silent failure on network error |
| No error boundary | Malformed digest crashes the whole view |
| Wikipedia URL not clickable | User can't navigate to source |

### Changes

**`ExtensionView.tsx`**
- Listen to `stage{point}` events during streaming → render placeholder skeleton cards in arrival order
- When `structured_output{schema:"ExtensionDigest"}` fires → hydrate all skeleton cards with real content in place
- Result: user sees points building progressively, not all at once

**`ExtensionDigestCard.tsx`**
- Add dedicated `renderFootnoteBody(body: string)` — handles `$…$` / `$$…$$` via KaTeX, plain text; no `[N]` citation logic
- Replace `renderInlineWithCites` call on footnote bodies with `renderFootnoteBody`
- Truncate `fn.source` display to 40 chars with `…` suffix
- Wikipedia footnote (`kind === "wikipedia"`): render `fn.source` as clickable `<a href={fn.source} target="_blank" rel="noopener">` link
- Download button: add `isDownloading: boolean` state; show spinner during fetch; show error toast on non-OK response

**Error boundary**
- `StructuredErrorBoundary` exists on `feat/component-equation-enforcement` but is NOT yet in this worktree. Port it: copy `web/src/components/StructuredErrorBoundary.tsx` from the sibling branch before use. Wrap `ExtensionDigestCard` with it.

---

## Invariant Impact

| Invariant | Affected? | Action |
|---|---|---|
| #28 Zeroth-law XML prompts | Yes | All updated prompts keep `<role>/<context>/<task>` |
| #14 footnote-only augmentation | Unchanged | Prompt changes reinforce it |
| Chinese wall | Unchanged | All changes stay inside `extension_agents/` and `web/src/` Extension components |

---

## Test Impact

Every changed module gets corresponding test updates:

| Module | Test file | New/updated tests |
|---|---|---|
| `prompts.py` | `test_extension_prompts.py` | English-rule present, density-rule present, gap-taxonomy in analyst, fit-rubric in augmentor, COVERAGE format in augmentor |
| `runner.py` | `test_extension_runner.py` | `_normalize_math_delimiters` round-trips, `_strip_md_footnote_markers` removes `[^n]`, fuzzy subtopic falls back to search, section-cap default is 2500 |
| `tools.py` | `test_extension_tools.py` | `retrieve_corpus` dedup by `seen_ids`, `retrieve_corpus top_k=10`, wikipedia disambiguation fallback |
| `_models.py` | `test_extension_models.py` | Judge default = nano, `EXTENSION_JUDGE_MODEL` override applies, temperature params present |
| `agent.py` | `test_extension_agent.py` | Per-stage temperature set on `_lc_model` call |
| `ExtensionDigestCard.tsx` | `ExtensionDigestCard.test.tsx` | `renderFootnoteBody` called for footnote bodies, Download button shows loading state, Wikipedia link is `<a>` element, source truncated |
| `ExtensionView.tsx` | `ExtensionView.test.tsx` | `stage{point}` events produce skeleton cards; `structured_output` hydrates them |

---

## Synced Artifacts Checklist

Logic changes are incomplete without all of these updated:

| Artifact | Changes |
|---|---|
| `extension_agents/prompts.py` | All 5 prompts revised |
| `extension_agents/runner.py` | Math normalizer, footnote marker cleaner, fuzzy subtopic, section cap |
| `extension_agents/tools.py` | Wikipedia async+fallback, corpus dedup+top_k |
| `extension_agents/_models.py` | Judge default, `_MID` alias, `EXTENSION_JUDGE_MODEL` flag, temperature params |
| `extension_agents/agent.py` | Per-stage temperature |
| `web/src/components/ExtensionDigestCard.tsx` | `renderFootnoteBody`, truncated source, Download loading, Wikipedia link, error boundary |
| `web/src/views/ExtensionView.tsx` | Per-point streaming skeleton hydration |
| `docs/services/chat-features/54-extension-mode.md` | Update env flags table, agent roster table, frontend section |
| `docs/system/invariants.md` | Add extension footnote-density invariant (≥2 per non-trivial point) |
| `docs/system/changelog.md` | Entry for this rebuild |
| Tests (all modules above) | Updated in lockstep |

---

## Out of Scope

- Analyst call parallelisation (deepagents parallel task API exploration — separate task)
- Provider expansion (Groq/DeepSeek for extension) — would require changes to shared `_lc_model` infrastructure
- Export HTML math delimiter fix (KaTeX CDN config in `export.py` — separate follow-up)
- Persist/reload verification (already fixed in `c8f52a3`, needs live verify only)
- QA card bug port (separate from this rebuild)
