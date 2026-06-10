# Feature 54 — Extension Mode (cross-book + Wikipedia footnote augmentation)

**Branch:** `feat/extension-mode`
**Date:** 2026-06-09
**Spec:** [`docs/superpowers/specs/2026-06-09-extension-mode-design.md`](../../superpowers/specs/2026-06-09-extension-mode-design.md)
**Plan:** [`docs/superpowers/plans/2026-06-09-extension-mode.md`](../../superpowers/plans/2026-06-09-extension-mode.md)

---

## Purpose

Extension mode takes a chapter (or named section) of a book **already in the corpus**, follows its formal structure, and **augments** each part with material from other sources — other ingested books (cross-book) and Wikipedia.

The deliverable is **curated to-the-point text + augmented footnotes**. It is NOT a summary. The base concepts are kept as real, direct prose (pruned of exercises and tiny/irrelevant sections, with duplicate sections clustered into one); every piece of new material — including formulas, inline or display LaTeX — lives only in **footnotes**, never woven into the base text (invariant: §Footnote-only augmentation below).

**Core principle (governs all conflicts):**

> The final output is a direct, to-the-point curated text + augmented footnotes. It is not necessarily a summary.

---

## Architecture — Topology C

Extension follows **Topology C**: a deterministic shell wraps an agentic core. The shell (runner) is responsible for scope resolution, the human clarify gate, and the hard-capped round loop; the agentic core (deepagents) owns within-round reasoning.

```mermaid
flowchart TD
  U[User query] --> RES[Resolve + confirm gate]
  RES -->|ambiguous| CLAR[Clarify, stop]
  RES --> FETCH[Fetch ordered sections -> /structure]
  FETCH --> ORC{{Extension deep-agent}}
  subgraph ORC
    A[Analyst x N] --> P[Polish -> /curated]
    P --> Q[Orchestrator: plan queries -> /plan]
    Q --> AUG[Augmentor x N -> /footnotes]
    AUG --> J[Judge: complete?]
    J -->|unfilled & budget| AUG
  end
  ORC --> DIG[ExtensionDigest -> SSE points]
  DIG --> ZIP[/api/export: styled-HTML ZIP]
```

The structural fetch is deterministic and order-fixed before any LLM runs — matching how chapter mode works (the chapter's section order determines the answer order; embedding retrieval is only for fuzzy subtopic→section resolution, never for main-content fetch). Agentic spend and the judge re-delegation loop are reserved for the genuinely open work: gap-query planning and augmentation.

---

## Agent Roster

| Agent | Default model | Reads | Writes | Tools |
|---|---|---|---|---|
| **orchestrator** (top-level) | `gpt-5.4-2026-03-17` (top) | `/structure/*`, `/context/*`, `/curated/*`, `/footnotes/*` | `/plan/queries.md`, todos | `write_todos`, `task`, fs |
| **analyst** (batched per section) | `gpt-5.4-nano-2026-03-17` (cheap) | `/structure/NN.md` | `/context/NN.md` — concept, key ideas, gaps | fs, `retrieve_peek` (read-only) |
| **polish** (once) | `gpt-5.4-nano-2026-03-17` (cheap) | `/context/*` | `/curated/timeline.md` — clustered, ordered, curated prose (NOT a summary) | fs |
| **augmentor** (batched per query) | `gpt-5.4-nano-2026-03-17` (cheap) | `/plan/queries.md`, `/curated/timeline.md` | `/footnotes/<point>.md` | fs, `retrieve_corpus` (cross-book, excludes base book), `wikipedia_lookup` |
| **judge** (= orchestrator re-reading) | `gpt-5.4-nano-2026-03-17` (cheap) | `/plan/queries.md`, `/footnotes/*` | re-delegation todos | fs |

The orchestrator and judge default to a top model because they own open reasoning (structure understanding, gap-query planning, coverage judgement). Analyst, augmentor, and polish handle bounded extraction/retrieval tasks → nano by default.

### Phase order inside the deep-agent

1. **Analyst fan-out (parallel)** — ALL analyst task calls issued in a single orchestrator message (one `task` call per `/structure` file); LangGraph `ToolNode` executes them concurrently via `asyncio.gather` → each writes `/context/NN.md`.
2. **Polish** — reads all context → writes `/curated/timeline.md` (curated, clustered, ordered points).
3. **Orchestrator query-gen** — reads timeline + context gaps → writes `/plan/queries.md` (deduplicated open gap queries, format `POINT :: query`).
4. **Augmentor batch** — one augmentor task per (batch of) queries → RAG corpus + Wikipedia, judges fit before footnoting → `/footnotes/<point>.md`.
5. **Judge** (orchestrator) — reads `/plan/queries.md` against `/footnotes/*`. Marks each query `done` or `unfilled`. If any are `unfilled` and budget remains → re-delegates a fresh augmentor batch for the unfilled queries only.

---

## Judge Loop + Termination

The judge is the orchestrator re-reading `/plan/queries.md` against `/footnotes/*`. Each augmentor file ends with `# COVERAGE: <query> = done|unfilled` lines that the runner parses.

- **Env cap:** `EXTENSION_MAX_ROUNDS` (default `3`).
- Hard stop on cap → return the partial result and explicitly report which gaps were left unfilled in `ExtensionDigest.unfilled_gaps`. Never loops unbounded.

---

## Tools

| Tool | Location | Purpose |
|---|---|---|
| `retrieve_peek(query)` | `extension_agents/tools.py` | Read-only corpus peek for the analyst to judge what is present or missing. Wraps `hybrid_search`. |
| `make_retrieve_corpus(exclude_book, all_slugs)` | `extension_agents/tools.py` | Augmentor's cross-book retrieval factory; **excludes the base book's slug**. Under `rerank=True` result count = `rerank_top_n` — passed explicitly to narrow. |
| `wikipedia_lookup(query)` | `extension_agents/tools.py` | Public REST API (`en.wikipedia.org/api/rest_v1/page/summary/...`), no key. Returns the lead extract + article URL. Augmentor judges fit before footnoting. |

---

## Output Schema

```python
# src/services/chat/schemas/output.py
class ExtensionFootnote(BaseModel):
    marker: str
    body: str          # augmenting text; may contain $…$ / $$…$$ LaTeX
    source: str        # corpus slug+section or Wikipedia URL
    kind: Literal["corpus", "wikipedia"]

class ExtensionPoint(BaseModel):
    title: str
    curated_text: str  # carries NO augmentation; only base content
    footnotes: list[ExtensionFootnote]

class ExtensionDigest(BaseModel):
    book: str
    chapter: str
    points: list[ExtensionPoint]
    unfilled_gaps: list[str]   # gap queries not filled within EXTENSION_MAX_ROUNDS
```

**Strict-safe**: all fields are closed-key lists — no open-keyed `dict` fields anywhere. Safe for OpenAI strict structured outputs.

---

## Footnote-only Invariant (hard rule)

ALL augmentation — including formulas (inline `$…$` or display `$$…$$`) — appears **only in `footnotes`**. `curated_text` carries no new material, no URLs, no source tags. This is enforced at both prompt level (augmentor prompt `<rules>`) and code level (`curated_text_is_clean` in `runner.py`, which strips leaked URLs before emit). Test guard: `test_extension_invariant.py::test_curated_text_has_no_augmentation_markers` + `curated_text_is_clean`.

---

## Env Flags

| Flag | Default | Meaning |
|---|---|---|
| `EXTENSION_MAX_ROUNDS` | `3` | Hard cap on judge re-delegation rounds. Override per-request via `extensionMaxRounds` (int, 1–6). |
| `EXTENSION_JUDGE_MODEL` | `""` (→ nano) | Override judge stage model independently of orchestrator. |

---

## Request Knobs (`ChatRequest`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `extensionMaxRounds` | `int \| None` | `None` → env default (`3`) | Cap the judge re-delegation loop for this request (1–6). |
| `extensionModels` | `dict[str, str] \| None` | `None` → all stage defaults | Per-stage model overrides. Keys: `"orchestrator"`, `"analyst"`, `"polish"`, `"augmentor"`, `"judge"`. Values = model ids. Unknown stage/model → stage default. |

### `extensionModels` stage defaults

| Stage key | Default model | Rationale |
|---|---|---|
| `orchestrator` | `gpt-5.4-2026-03-17` | Open reasoning — gap planning + structure understanding |
| `judge` | `gpt-5.4-2026-03-17` | Coverage judgement |
| `polish` | `gpt-5.4-nano-2026-03-17` | Bounded curation task |
| `analyst` | `gpt-5.4-nano-2026-03-17` | Bounded extraction |
| `augmentor` | `gpt-5.4-nano-2026-03-17` | Bounded retrieval + footnote writing |

---

## SSE Event Sequence

```
stage{parse} → stage{fetch} → stage{augment · round N} (per round)
  → stage{point · <title>} (per point) → structured_output{schema:"ExtensionDigest"}
  → sources_full{sources:[]} → usage → done
```

Clarify-gate path (book/chapter ambiguous):

```
stage{parse} → clarify{type:"clarify", options:[…]} → usage{inputTokens:0} → done
```

---

## Export Endpoint

`POST /api/export` — accepts an `ExtensionDigest` JSON body, returns a ZIP (`application/zip`) with:

- **`extension.html`** — self-contained styled HTML: curated points, footnotes rendered with KaTeX (CDN linked), embedded CSS, opens standalone in any browser.
- **`sources.json`** — footnote provenance array: `[{point, marker, source, kind}, …]`.

`Content-Disposition`: `attachment; filename="<book>-<chapter>-extended.zip"`.

Test: `test_extension_export.py::test_zip_contains_html_and_sources` + `test_html_is_self_contained`.

---

## Frontend

| Component | Path | Role |
|---|---|---|
| `ExtensionDigestCard` | `web/src/components/ExtensionDigestCard.tsx` | Renders ordered points; `renderFootnoteBody` for footnotes (KaTeX math, no citation logic); Wikipedia sources as links; source paths truncated to 40 chars; Download button with loading state; wrapped in `StructuredErrorBoundary`. |
| `StructuredErrorBoundary` | `web/src/components/StructuredErrorBoundary.tsx` | Ported from sibling branch; degrades malformed digest to inline error notice. |
| `ExtensionPipelineDiagram` | `web/src/components/ExtensionPipelineDiagram.tsx` | Modal pipeline card — topology C nodes matching the reference graph (`modes/extension.html`). |
| `ExtensionView` | `web/src/views/ExtensionView.tsx` | Mode view wired into `MessageThread` on `schema === "ExtensionDigest"`. |
| `ModePicker` | `web/src/components/ModePicker.tsx` | Extension chip: label "Extension", description "Extend a chapter with cross-book + Wikipedia footnotes". |

Streaming: each curated point (with its footnotes) is emitted as a `stage{point}` event as it is finalized, so the user watches the document build in order.

---

## Isolation (Chinese wall)

- Package: `src/services/chat/agents/extension_agents/` (runner, agent, tools, scope, prompts, export, model resolver).
- Skills: `src/services/chat/agents/extension_skills/{curate-structure,gap-augment,judge-coverage}/SKILL.md`.
- Imports **only** `src.core.*` and shared chat infra (`_scope`, `retrieval`, `books`, `llm.router`, `schemas`, `_fences`). **Zero** imports from `deep_tutor*`, `qa*`, `ow_*`.
- All prompts XML-tagged with `<role>/<context>/<task>` minimum, plus `<rules>/<failure_mode>/<output>` per stage (invariant 28). Guard: `test_extension_prompts.py::test_every_prompt_is_xml_tagged`.

---

## Synced-Artifacts Checklist

A logic change to extension mode is incomplete until **all** of these reflect it:

| Aspect | Path |
|---|---|
| Mode id | `src/services/chat/schemas/_core.py` (`ModeId` Literal) |
| Request knobs | `src/services/chat/schemas/_core.py` (`extensionMaxRounds`, `extensionModels`) |
| Response schema | `src/services/chat/schemas/output.py` (`ExtensionDigest` et al.) |
| Router branch | `src/services/chat/router.py` → `_V2_DISPATCH["extension"]` |
| Export endpoint | `src/services/chat/api.py` → `POST /api/export` |
| Backend logic | `extension_agents/runner.py`, `agent.py`, `tools.py`, `scope.py`, `export.py` |
| Prompts | `extension_agents/prompts.py` (XML-tagged constants) |
| Per-stage model resolver | `extension_agents/_models.py` (`STAGE_DEFAULTS`, `resolve_stage_model`) |
| Skills | `extension_skills/{curate-structure,gap-augment,judge-coverage}/SKILL.md` |
| Env flag | `EXTENSION_MAX_ROUNDS` |
| Modal card | `web/src/components/ExtensionPipelineDiagram.tsx` |
| Frontend view | `web/src/views/ExtensionView.tsx` + `ExtensionDigestCard.tsx` |
| ModePicker | `web/src/components/ModePicker.tsx` |
| Reference graph | `docs/common ground/Elements/modes/extension.html` (+ features/index.html entry) |
| Invariants + changelog | `docs/system/invariants.md`, `docs/system/changelog.md` |
| CLAUDE.md | mode list + recent-docs pointer |
| Tests | `test_extension_schema.py`, `test_extension_models.py`, `test_extension_tools.py`, `test_extension_scope.py`, `test_extension_prompts.py`, `test_extension_skills.py`, `test_extension_agent.py`, `test_extension_runner.py`, `test_extension_invariant.py`, `test_extension_export.py`; `ExtensionDigestCard.test.tsx`, `ExtensionPipelineDiagram.test.tsx` |

---

## Test Coverage

**Backend** (`src/services/chat/tests/`):

- `test_extension_schema.py` — `ModeId` accepts `"extension"`; knobs default / accept values; `ExtensionDigest` shape; strict-safe schema (no open-keyed dict).
- `test_extension_models.py` — stage defaults (orchestrator/judge = top, analyst/augmentor = cheap); override applies; unknown override falls back.
- `test_extension_tools.py` — `wikipedia_lookup` returns extract + URL, handles missing; `retrieve_corpus` excludes base book; `retrieve_peek` read-only.
- `test_extension_scope.py` — structure files are ordered with `NN_` prefix; resolve returns clarify dict when ambiguous.
- `test_extension_prompts.py` — every prompt has `<role>/<context>/<task>`; augmentor states footnote-only rule; polish states curate-not-summarize.
- `test_extension_skills.py` — three SKILL.md files with YAML frontmatter (`name:`, `description:`).
- `test_extension_agent.py` — builder wires analyst/polish/augmentor subagents; orchestrator model = top default; skills paths present.
- `test_extension_runner.py` — clarify gate stops before agent build; happy path streams `structured_output{schema:"ExtensionDigest"}`; round loop caps at `extensionMaxRounds`.
- `test_extension_invariant.py` — `curated_text_is_clean` returns `True` for clean body, `False` for URL-leaked body.
- `test_extension_export.py` — ZIP contains `extension.html` + `sources.json`; HTML is self-contained (embedded CSS, KaTeX, no external files).

**Frontend** (`web/src/`):

- `ExtensionDigestCard.test.tsx` — renders points, titles, curated text, footnotes; shows Download button.
- `ExtensionPipelineDiagram.test.tsx` — topology C stage labels all present.
