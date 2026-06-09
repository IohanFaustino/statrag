# Extension Mode — Design Spec

**Date:** 2026-06-09
**Status:** design, pending build
**Author:** feature_Agent session
**Mode id:** `extension`

## 1. Purpose

A new chat mode that takes a chapter (or named section) of a book **already in
the RAG corpus**, follows its formal structure, and **augments** each part with
material from *other* sources — other ingested books (cross-book) and Wikipedia.

The deliverable is **curated to-the-point text + augmented footnotes**. It is NOT
a summary. The base concepts are kept as real, direct prose (pruned of exercises
and tiny/irrelevant sections, with duplicate sections clustered into one); every
piece of *new* material — including formulas, inline or display — lives only in
**footnotes**, never woven into the base text.

### Core principle (user-stated, governs all conflicts)

> The final output is a direct, to-the-point curated text + augmented footnotes.
> It is not necessarily a summary.

When any sub-decision conflicts with this, this principle wins.

## 2. Decisions (locked with user)

| Decision | Choice |
|---|---|
| Augmentation source | Cross-book corpus (exclude base book) **+ Wikipedia only** (no general web) |
| Base text origin | A chapter already in the corpus; resolved from metadata |
| Base text treatment | Curated (prune exercises/tiny, cluster dupes, order intro→conclusion) — **not** a summary; augmentation only as footnotes |
| Agentic paradigm | **deepagents** (`deepagents==0.6.8`, already a prod dep), fresh design — NOT a clone of the qa-deepagent roster |
| Topology | **C — deterministic shell wraps an agentic core** |
| Scope granularity | Chapter **or** named section(s) (reuse chapter-mode resolve) |
| Wikipedia tool | Public REST API (`en.wikipedia.org/api/rest_v1`), no key |
| Confirm gate | Common-ground the book + chapter **before** the deepagent runs (no agentic spend until user confirms) |
| Isolation | Own package `extension_agents/` + `extension_skills/`; zero imports from tutor/qa |

## 3. Architecture — topology C

```
USER query ──► RUNNER (deterministic, no LLM agency)
   parse-scope ─ resolve book + chapter + section(s)    [reuse _scope.py + chapter parse/resolve]
   └─ CLARIFY GATE: confirm book + chapter with user     ◄── common-ground BEFORE any agentic spend
   fetch sections (order fixed by metadata)              [reuse fetch_chapter_sections]
        writes /structure/NN_<section_id>.md  (real section text, in order)
                       │
                       ▼
   EXTENSION DEEP-AGENT (the only agentic part — deepagents harness, shared virtual FS)
        analyst batch → polish → orchestrator query-gen → augmentor batch → judge (loop)
                       │
                       ▼
   RUNNER stitches /curated/timeline.md + /footnotes/* ─► ExtensionDigest ─► SSE stream
```

The structural fetch is deterministic and order-fixed *before any LLM runs*,
matching how chapter mode already works (the chapter's section order determines
the answer order; embedding retrieval is only for fuzzy subtopic→section
resolution, never for main-content fetch). Agentic spend + the judge
re-delegation loop are reserved for the genuinely open work: gap-query planning
and augmentation.

## 4. The deepagent roster

One top-level orchestrator + 3 custom subagents, communicating through the
deepagents shared **virtual filesystem** (StateBackend / in-memory, ephemeral
per request) and the `write_todos` planning tool.

| Agent | Reads | Writes | Tools |
|---|---|---|---|
| **orchestrator** (top) | `/structure/*`, `/context/*`, `/curated/*`, `/footnotes/*` | `/plan/queries.md`, todos | `write_todos`, `task`, fs |
| **analyst** (subagent, batched per section) | `/structure/NN.md` | `/context/NN.md` — what concept, key ideas, and what is *missing* (gaps to augment) | fs, `retrieve_peek` (read-only) |
| **polish** (subagent) | `/context/*` | `/curated/timeline.md` — cluster duplicate sections into one, drop exercises + tiny/irrelevant sections, order intro→conclusion, curated to-the-point text (NOT a summary) | fs |
| **augmentor** (subagent, batched per query) | `/plan/queries.md`, `/curated/timeline.md` | `/footnotes/<point>.md` | fs, `retrieve_corpus` (cross-book, excludes base book), `wikipedia_lookup` |

### Phase order inside the deep-agent

1. **analyst batch** — one analyst task per structure file → `/context/NN.md`.
2. **polish** — reads all context → writes `/curated/timeline.md` (the curated,
   clustered, ordered points).
3. **orchestrator query-gen** — reads timeline + context gaps → writes
   `/plan/queries.md` (open gap queries, e.g. "talks about random variables but
   not distributions"). **Dedups** queries before delegating.
4. **augmentor batch** — one augmentor task per (batch of) queries → RAG corpus
   + Wikipedia, **judges fit** before footnoting → `/footnotes/<point>.md`.
5. **judge** (orchestrator) — see §5.

## 5. Judge loop + termination

The judge is the orchestrator re-reading `/plan/queries.md` against
`/footnotes/*`. Each query is marked `done` or `unfilled`. If any are `unfilled`
and budget remains → re-delegate a fresh augmentor batch for the unfilled
queries only.

- **Env cap:** `EXTENSION_MAX_ROUNDS` (default `3`).
- Hard stop on cap → return the partial result and explicitly note which gaps
  were left unfilled. Never loop unbounded.

## 6. Tools (custom, in `extension_agents/`)

- `retrieve_peek(query) -> str` — read-only corpus peek for the analyst to judge
  what's present/missing. Wraps `hybrid_search`. Remember: under `rerank=True`
  result count = `rerank_top_n`, so pass it explicitly to narrow.
- `retrieve_corpus(query, exclude_book) -> list[Source]` — augmentor's
  cross-book retrieval; **excludes the base book's slug**.
- `wikipedia_lookup(title_or_query) -> str` — public REST API
  (`en.wikipedia.org/api/rest_v1/page/summary/...`), no key; returns the clean
  extract. Augmentor judges fit before turning it into a footnote.

## 7. Output schema + footnotes

New Pydantic models in `src/services/chat/schemas/output.py`:

```
ExtensionFootnote: { marker: str, body: str, source: str, kind: "corpus" | "wikipedia" }
ExtensionPoint:    { title: str, curated_text: str, footnotes: list[ExtensionFootnote] }
ExtensionDigest:   { book: str, chapter: str, points: list[ExtensionPoint], unfilled_gaps: list[str] }
```

- **Footnote rule (hard invariant):** all augmentation — including formulas,
  inline or display LaTeX — appears only in `footnotes`. `curated_text` carries
  no new material. A test guard enforces this.
- OpenAI strict structured outputs forbid open-keyed `dict` fields and truncate
  on length. All models above are closed-key lists — strict-safe. Guard with a
  schema test.

## 8. Frontend (system_Agent portion)

- `web/src/views/ExtensionView.tsx` — renders ordered points; footnote markers as
  superscripts; footnote bodies render KaTeX (reuse the tutor math render path;
  honour the mid-line `$$`→`$` rule, [[tutorview-midline-display-math]]).
- `web/src/components/ExtensionPipelineDiagram.tsx` + `web/src/data/` node data —
  the modal card users see; must match the reference graph.
- Streaming: emit each curated point (with its footnotes) as it is finalized, so
  the user sees the document build in order (like chapter mode's per-block
  streaming).

## 9. Isolation + Chinese wall

- New package `src/services/chat/agents/extension_agents/` (agent builders,
  tools, runner) + `src/services/chat/agents/extension_skills/` (SKILL.md dirs:
  `curate-structure`, `gap-augment`, `judge-coverage`).
- Imports **only** `src.core.*` and shared chat infra (`_scope`, `retrieval`,
  `llm.router`, `schemas`). **Zero** imports from `agents/deep_tutor*`,
  `agents/qa*`, `agents/ow_*`.
- Every prompt is XML-tagged with `<role>` + `<context>` + `<task>` minimum, plus
  `<rules>`/`<examples>`/`<output>`/`<failure_mode>` as needed (Zeroth law). The
  `test_prompt_schema.py` CI guard must pass for the new prompt module.

## 10. Interconnect artifacts (lockstep — all must ship together)

| Aspect | Where |
|---|---|
| Mode id | `ModeId` Literal in `schemas/_core.py` += `"extension"` |
| Request knobs | `schemas/_core.py` (e.g. `extensionMaxRounds`) |
| Response schema | `schemas/output.py` — `ExtensionDigest` et al. |
| Router branch | `src/services/chat/router.py` → `extension_agents.runner.run_extension` |
| Backend logic | `extension_agents/` (runner + agent builders + tools) |
| Prompts | `extension_agents/` prompt module (XML-tagged) |
| Skills | `extension_skills/{curate-structure,gap-augment,judge-coverage}/SKILL.md` |
| Env flag | `EXTENSION_MAX_ROUNDS` + env table in `docs/services/chat-features/54-extension-mode.md` |
| Modal card | `web/src/components/ExtensionPipelineDiagram.tsx` + node data |
| Frontend view | `web/src/views/ExtensionView.tsx` |
| Per-feature doc | new `docs/services/chat-features/54-extension-mode.md` (mermaid graph) |
| Reference graph | `docs/common ground/Elements/features/modes/extension.html` (+ Features index entry) |
| Invariants + changelog | `docs/system/invariants.md` (footnote-only-augmentation + judge-cap), `docs/system/changelog.md` |
| CLAUDE.md | recent-docs pointer += `54`; mode list |
| Tests | see §11 |

## 11. Test matrix

Backend (`src/services/chat/tests/`):
- scope/resolve → correct book+chapter+section, closest-match.
- clarify gate fires when book/chapter ambiguous; no agentic spend before confirm.
- structure fetch writes ordered `/structure/*` files (order = metadata order).
- analyst / polish / augmentor phase units — monkeypatch a single `_chat` seam
  (mirror chapter.py's seam discipline).
- polish clusters duplicate sections (4 LLN → 1) and drops exercise sections.
- query-gen dedups queries.
- **judge loop**: re-delegates on unfilled, stops at `EXTENSION_MAX_ROUNDS`,
  returns partial + `unfilled_gaps`.
- **footnote-only-augmentation guard**: no augmentation text/formula leaks into
  `curated_text`.
- ExtensionDigest strict-structured-output safe (no open-key dict, regression
  guard).
- prompt schema guard passes for the new prompt module.

Frontend (`web/`):
- `ExtensionView.test.tsx` — renders points, superscript markers, KaTeX in
  footnotes.
- `ExtensionPipelineDiagram.test.tsx` — nodes/edges match the reference graph.

## 12. Verification (feature_Agent definition of done)

- `pytest src/services/chat/tests/ -q` green; new tests + regression guards.
- `cd web && npx tsc --noEmit && npx vitest run` green.
- `rag-verify` passes (retrieval tools touched).
- Browser-verify on **:5175**: select extension mode, write a query, confirm the
  clarify gate, watch points stream, read real footnotes (corpus + Wikipedia),
  confirm formulas render in footnotes and not in base text. Modal card matches
  `extension.html`. Monitor services for errors during the run.

## 13. Out of scope (YAGNI)

- General web search (Wikipedia only).
- Persistent cross-session memory / Store backend (ephemeral per-request FS).
- HITL approval inside the deep-agent (the only human gate is the pre-run
  book/chapter confirm).
- Rewriting / summarizing base text (curated, not summarized; footnotes only).
```
