# Q&A Rebuild — Storytelling Voice + Wikipedia Grounding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> to implement task-by-task (fresh implementer → spec reviewer → quality reviewer per task).
> Each implementer follows `superpowers:test-driven-development`. Steps use `- [ ]` tracking.

**Goal:** Rebuild Q&A as a flat, deterministic pipeline `scope → retrieve(corpus ∥ wiki) →
write → bind(PURE CODE) → verify` emitting a **storytelling** `QAStoryAnswer{intro, deepening,
conclusion}` with **verbatim-bound** corpus 📕 + wikipedia 🌐 citations. No deepagents, no
subagents, no checker loop.

**Spec:** [`docs/superpowers/specs/2026-06-11-qa-story-wiki-design.md`](../specs/2026-06-11-qa-story-wiki-design.md).

**Base branch:** `feat/component-equation-enforcement` (extend the shipped flat Q&A). Execute in
an isolated worktree (`superpowers:using-git-worktrees`), branched from HEAD.

**Isolation rule (hard):** no imports from `deep_tutor.py`, `orchestrator_workers.py`,
`ow_deepagents.py`, `prompts/deep_tutor.py`, `ow_skills/`. Shared read-only primitives only.

**Tech stack:** Python 3.12, Pydantic v2, `httpx` (wiki), Qdrant hybrid retrieval, FastAPI SSE;
React + Vite + TS + vitest. Implementers on **sonnet**.

**Run tests:** `.venv/bin/python -m pytest <path> -v` (backend); `cd web && npx vitest run <path>` (frontend).

**Trust boundary (carry in every prompt):** the LLM writer NEVER authors citation fields. It
emits prose with inline `[[eid]]` tokens referencing real `Evidence.id`s. Pure-code `qa_bind`
rewrites valid tokens to `[n]` + builds `StoryCitation` verbatim from `Evidence.meta`; invalid
tokens are stripped (prose kept); zero bound markers → one redraft.

---

## File structure

| File | Action | Responsibility |
|---|---|---|
| `src/services/chat/research.py` | **Create** | Extract `Evidence`, `corpus_evidence`, `wiki_evidence`, `_wiki_summary_json`, `_citation`/`_label` from extension_agents (mode-agnostic) |
| `src/services/chat/agents/extension_agents/research.py`,`binder.py` | Modify | thin re-import shims → `research.py` (byte-identical behaviour) |
| `src/services/chat/schemas/output.py` | Modify | `QAScope += wiki_terms`; new `QAStoryDraft`, `QAStoryAnswer` |
| `src/services/chat/schemas/__init__.py` | Modify | re-export new schemas |
| `src/services/chat/prompts/qa.py` | Rewrite | `QA_SCOPE_PROMPT`(+wiki_terms), `QA_STORY_WRITE_PROMPT`, `QA_VERIFY_PROMPT`, `QA_FALLBACK_PROMPT` |
| `src/services/chat/agents/qa.py` | Rewrite | `extract_scope`(+wiki_terms), `retrieve_evidence`, `write_story`, `qa_bind`, `verify_story`, `run_qa`, fallback |
| `web/src/types.ts` | Modify | `QAScope += wiki_terms`; `QAStoryAnswer`; reuse `StoryCitation` |
| `web/src/components/QAAnswerCard.tsx` | Rewrite | intro→deepening→conclusion + 📕/🌐 chips |
| `web/src/data/qaPipeline.ts`,`QAPipelineDiagram.tsx` | Modify | new flat node graph (bind = pure-code node) |
| `web/src/components/MessageThread.tsx` | Modify | progress events + `QAStoryAnswer` branch + legacy discriminator |
| `web/src/data/qaMode.ts`,`modals/QAModeModal.tsx` | Modify | modal copy |
| `docs/common ground/Elements/modes/qa.html` | Modify | HTML doc diagrams (dual surface) |
| `docs/services/chat-features/51-qa-mode.md`,`docs/services/chat.md`,`docs/system/invariants.md`,`docs/system/changelog.md` | Modify | docs lockstep |

`_core.py`, `modes.py`, `router.py`: **no change** — regression test only (Task 8).

---

## Task 1 — Extract shared `research.py` (wiki + binder primitives)

**Files:** create `src/services/chat/research.py`; modify `extension_agents/research.py`,
`extension_agents/binder.py`; test `src/services/chat/tests/test_research_shared.py`.

- [ ] **Step 1 — failing test:** assert `from src.services.chat.research import Evidence,
  corpus_evidence, wiki_evidence, _citation` imports; assert `_citation` on a wikipedia Evidence
  yields a `StoryCitation(kind="wikipedia", title=…, url=…)` with fields equal to `Evidence.meta`;
  assert the extension shim still exposes the same names (`from
  src.services.chat.agents.extension_agents.research import wiki_evidence, Evidence`).
- [ ] **Step 2 — run, verify fail** (`research.py` missing).
- [ ] **Step 3 — implement:** move `Evidence`, `_WIKI_*`, `_wiki_summary_json`, `wiki_evidence`,
  `corpus_evidence`, `_seen_lock`, `_logger` verbatim into `research.py`; move `_label` +
  `_citation` (from `binder.py`) in too. In `extension_agents/research.py` replace bodies with
  `from src.services.chat.research import Evidence, corpus_evidence, wiki_evidence  # re-export`.
  In `binder.py` import `_citation`, `_label`, `Evidence` from `research.py`. Keep
  `bind_citations`/`BulletDraft` in `binder.py` (Extension-specific).
- [ ] **Step 4 — run extension suite green:** `pytest src/services/chat/tests/ -k extension -v`
  (byte-identical behaviour) **and** the new test → PASS.
- [ ] **Step 5 — commit** `refactor(chat): extract Evidence + wiki/corpus + _citation into shared research.py`.

---

## Task 2 — Schemas: QAScope.wiki_terms + QAStoryDraft + QAStoryAnswer

**Files:** modify `schemas/output.py`, `schemas/__init__.py`; test `tests/test_qa_schema.py`.

- [ ] **Step 1 — failing test:**
```python
def test_qascope_wiki_terms_default_empty():
    from src.services.chat.schemas import QAScope
    assert QAScope(target_gap="x").wiki_terms == []

def test_qastorydraft_has_no_citation_field():
    from src.services.chat.schemas import QAStoryDraft
    assert "citations" not in QAStoryDraft.model_fields
    d = QAStoryDraft(intro="i", deepening="d", conclusion="c")
    assert d.math_blocks == []

def test_qastoryanswer_three_fields_no_tutor_fields():
    from src.services.chat.schemas import QAStoryAnswer, QAScope, StoryCitation
    a = QAStoryAnswer(intro="i", deepening="d", conclusion="c", scope=QAScope(target_gap="x"))
    f = set(QAStoryAnswer.model_fields)
    assert {"intro","deepening","conclusion"} <= f
    assert {"sections","aspects","figures","text"} & f == set()
    assert a.citations == [] and isinstance(a.grounding, dict)
```
- [ ] **Step 2 — run, verify fail.**
- [ ] **Step 3 — implement** in `output.py` per spec §4: add `wiki_terms` to `QAScope`; add
  `QAStoryDraft` (intro/deepening/conclusion/math_blocks, **no citations**) and `QAStoryAnswer`
  (3 fields + scope + `citations: list[StoryCitation]` + math_blocks + grounding).
  `StoryCitation` already defined (line ~613) — reference it. Do NOT delete legacy
  `QAAnswer`/`QAGenerateOut`/`QAVerifyOut` yet (Task 7 removes from path; legacy renderer).
- [ ] **Step 4** — `__init__.py`: add `QAStoryDraft, QAStoryAnswer,` to import + `__all__`.
- [ ] **Step 5 — run, verify pass.**
- [ ] **Step 6 — commit** `feat(qa): QAScope.wiki_terms, QAStoryDraft, QAStoryAnswer schemas`.

---

## Task 3 — Prompts (scope+wiki_terms, storytelling writer, verify, fallback)

**Files:** rewrite `src/services/chat/prompts/qa.py`; test `tests/test_qa_prompts.py`.

- [ ] **Step 1 — failing test:** assert constants exist and carry `<task>`/`</task>`;
  `QA_SCOPE_PROMPT` mentions `wiki_terms`; `QA_STORY_WRITE_PROMPT` mentions `[[`, `intro`,
  `deepening`, `conclusion`, "story"/"narrative", and forbids headings; `QA_FALLBACK_PROMPT`
  returns `intro`/`deepening`/`conclusion`.
- [ ] **Step 2 — run, verify fail.**
- [ ] **Step 3 — implement** `<role>/<task>/<rules>[/<output_format>]`-scaffolded constants:
  - `QA_SCOPE_PROMPT` — extract `target_gap`, `assumed_known`, `answer_form`, **`wiki_terms`**
    (≤2 named entities/eponyms/proper-noun concepts worth a Wikipedia lookup; `[]` if none).
  - `QA_STORY_WRITE_PROMPT` — **storytelling register** over intro→deepening→conclusion;
    rules: answer ONLY `target_gap`, skip `assumed_known`, corpus is primary authority, frame
    wiki as context/history/naming, **cite with inline `[[eid]]` tokens** (eids given in the
    user msg evidence list), **NEVER write citation fields/JSON**, **NO markdown headings**,
    intro ≤1 / deepening ≤3 / conclusion ≤1 paragraphs, conclusion closes (no "next steps"),
    PUNCTUAL not a tutor walkthrough.
  - `QA_VERIFY_PROMPT` — advisory grounding audit over the 3 fields + numbered sources.
  - `QA_FALLBACK_PROMPT` — corpus-only deterministic generate into `{intro,deepening,conclusion,
    math_blocks}` (regression safety).
  Keep module docstring + `from __future__ import annotations`. Remove obsolete
  `QA_GENERATE_PROMPT` only after Task 7 stops importing it.
- [ ] **Step 4 — run, verify pass.**
- [ ] **Step 5 — commit** `feat(qa): storytelling writer prompt (+[[eid]] convention), scope+wiki_terms, verify, fallback`.

---

## Task 4 — `retrieve_evidence` (corpus ∥ wiki gather) + `qa_bind` (pure-code binder)

**Files:** modify `src/services/chat/agents/qa.py`; tests `tests/test_qa_retrieve.py`,
`tests/test_qa_bind.py`.

- [ ] **Step 1 — failing tests:**
  `test_qa_retrieve.py` — monkeypatch `qa.corpus_evidence`/`qa.wiki_evidence`; assert
  `await qa.retrieve_evidence(scope, book_slugs=["hansen"])` calls wiki once for `target_gap`
  plus once per `wiki_terms[:2]` (cap), runs corpus once, returns a flat `list[Evidence]` with
  unique `.id`s; assert `QA_WIKI=0` skips wiki.
  `test_qa_bind.py`:
```python
def test_bind_rewrites_valid_tokens_and_keeps_prose_on_invalid():
    import src.services.chat.agents.qa as qa
    from src.services.chat.research import Evidence
    from src.services.chat.schemas import QAStoryDraft
    e = Evidence(subject_id="qa", kind="wikipedia", text="t",
                 meta={"title":"Chebyshev's inequality","url":"http://x"}, id="w1")
    draft = QAStoryDraft(intro="Named for Chebyshev [[w1]].",
                         deepening="Bound holds [[bad]]. Again [[w1]].", conclusion="Done.")
    ans = qa.qa_bind(draft, [e])
    assert "[1]" in ans.intro and ans.intro.count("[1]") == 1
    assert "[[w1]]" not in ans.deepening and "[1]" in ans.deepening   # reused n
    assert "[[bad]]" not in ans.deepening and ans.grounding["unbound_markers"] == 1
    assert "Bound holds ." not in ans.deepening or "Bound holds" in ans.deepening  # prose kept
    assert len(ans.citations) == 1 and ans.citations[0].kind == "wikipedia"
    assert ans.citations[0].title == "Chebyshev's inequality"   # verbatim from meta

def test_bind_strips_headings():
    import src.services.chat.agents.qa as qa
    from src.services.chat.schemas import QAStoryDraft
    ans = qa.qa_bind(QAStoryDraft(intro="## Overview\nHi", deepening="d", conclusion="c"), [])
    assert "##" not in ans.intro and "Overview" not in ans.intro.split("\n")[0] or "Hi" in ans.intro
```
- [ ] **Step 2 — run, verify fail.**
- [ ] **Step 3 — implement** in `qa.py`:
  - import `from src.services.chat.research import Evidence, corpus_evidence, wiki_evidence`;
    add `_QA_WIKI`, `_QA_WIKI_TERMS_MAX` env reads; `import re`, `import asyncio`.
  - `async def retrieve_evidence(scope, *, book_slugs)` — build wiki query list
    `[target_gap, *wiki_terms[:max]]` (skip if `_QA_WIKI` off), corpus query = `target_gap`;
    `asyncio.gather` the wiki calls (`to_thread(wiki_evidence, q, subject_id="qa")`) + one
    `to_thread(corpus_evidence, target_gap, subject_id="qa", exclude_book="", all_slugs=book_slugs
    or [], seen_ids=set(), top_n=_QA_TOP_K)`; flatten; return `list[Evidence]`.
  - `def qa_bind(draft, evidence) -> QAStoryAnswer` — per spec §5: regex `\[\[([^\]]+)\]\]`;
    shared first-appearance numbering across intro→deepening→conclusion; verbatim `_citation`;
    strip invalid tokens + count; strip `^#{1,6}\s` headings; mid-line `$$`→`$` normalization;
    paragraph caps → `grounding["lints"]`. Return `QAStoryAnswer` (grounding seeded with
    `unbound_markers`, `lints`).
- [ ] **Step 4 — run, verify pass.**
- [ ] **Step 5 — commit** `feat(qa): retrieve_evidence (corpus∥wiki gather) + pure-code qa_bind`.

---

## Task 5 — `extract_scope` emits wiki_terms + `write_story` (one writer call)

**Files:** modify `qa.py`; tests `tests/test_qa_scope.py`, `tests/test_qa_write.py`.

- [ ] **Step 1 — failing tests:** scope test — monkeypatch `qa._chat` to return JSON w/
  `wiki_terms:["Chebyshev"]` → `QAScope.wiki_terms == ["Chebyshev"]`; fail-open (`_chat` raises)
  → `wiki_terms == []`, whole query as gap. write test — monkeypatch `qa._chat` to return a
  `QAStoryDraft` JSON with `[[c1]]` tokens; assert `write_story` builds the evidence-id list into
  the user message (each Evidence rendered as `eid | kind | text-preview`) and returns a
  `QAStoryDraft`.
- [ ] **Step 2 — run, verify fail.**
- [ ] **Step 3 — implement:** extend `extract_scope` to parse `wiki_terms` (≤`_QA_WIKI_TERMS_MAX`,
  strings, fail-open `[]`); add `async def write_story(scope, evidence, *, model)` — render an
  evidence block listing each `Evidence.id` + kind + truncated text, call `_chat` with
  `QA_STORY_WRITE_PROMPT` + `QAStoryDraft` schema, parse defensively into `QAStoryDraft`.
- [ ] **Step 4 — run, verify pass.**
- [ ] **Step 5 — commit** `feat(qa): scope emits wiki_terms; write_story single storytelling call`.

---

## Task 6 — `verify_story` (advisory) + `_fallback_story` (regression safety)

**Files:** modify `qa.py`; tests `tests/test_qa_verify.py`, `tests/test_qa_fallback.py`.

- [ ] **Step 1 — failing tests:** verify test — monkeypatch `_chat` → `{ok:false,
  unsupported:["claim"],confidence:0.4}`; assert `verify_story(ans, sources)` merges into
  `grounding` without changing the 3 prose fields, and fail-open (raise → advisory pass).
  fallback test — `_fallback_story(scope, sources)` returns a `QAStoryAnswer` w/ non-empty
  `intro` from a corpus-only generate (monkeypatch `_chat`).
- [ ] **Step 2 — run, verify fail.**
- [ ] **Step 3 — implement** `verify_story` (advisory grounding audit, merges `ok`/`unsupported`/
  `confidence` into `grounding`, never edits prose, fail-open) and `_fallback_story` (corpus-only
  nano generate via `QA_FALLBACK_PROMPT` → `QAStoryAnswer`, `grounding={"ok":True,…,
  "confidence":0.6}`).
- [ ] **Step 4 — run, verify pass.**
- [ ] **Step 5 — commit** `feat(qa): advisory verify_story + deterministic _fallback_story`.

---

## Task 7 — Wire `run_qa` (pipeline + redraft + degradation + progress + SSE)

**Files:** rewrite `run_qa` in `qa.py`; remove legacy `generate_scoped`/`verify_grounding`/
`retrieve_for_gap` from the path; tests `tests/test_qa_run.py` (rewrite),
`tests/test_qa_degradation.py`.

- [ ] **Step 1 — failing tests:** `test_qa_run.py` — monkeypatch `extract_scope`,
  `retrieve_evidence`, `write_story`, `verify_story`, `resolve_book`/`maybe_clarify`/
  `parse_catalog`; assert the event stream is `meta → progress* → structured_output{schema:
  "QAStoryAnswer"} → sources_full → retrieval_meta → usage → done`, and `data` has
  `intro`/`deepening`/`conclusion`. `test_qa_degradation.py` — (a) `write_story` returns a draft
  with zero valid tokens → assert ONE redraft fired (write called twice) and stream still
  completes; (b) `retrieve_evidence` returns `[]` → honest "cannot answer" `QAStoryAnswer`,
  `grounding["ok"]==False`, `citations==[]`; (c) `write_story` raises → `_fallback_story` used.
- [ ] **Step 2 — run, verify fail.**
- [ ] **Step 3 — implement** `run_qa` per spec §2/§7/§8: keep `meta` + book-resolve/clarify;
  `scope` (gated `QA_SCOPE`); `retrieve_evidence`; emit `progress{retrieving}`; if no evidence →
  honest answer + full SSE tail; else `progress{writing}` → `write_story` →
  `progress{binding}` → `qa_bind`; if `len(citations)==0` → `progress{redraft}` + ONE re-`write_story`
  (explicit cite instruction appended) + re-`qa_bind`, ship regardless; set `corpus_weak`/
  `wiki_unavailable` from the evidence kinds; `verify_story` (gated `QA_VERIFY`); wrap the
  write/bind block so any exception → `_fallback_story`; emit `structured_output{schema:
  "QAStoryAnswer"}` + `sources_full` (corpus Source rows only) + `retrieval_meta` + `usage` +
  `done`. Update `_model_for` stage keys to `scope`/`write`/`verify`.
- [ ] **Step 4 — run, verify pass** (repair any `test_qa_*` that referenced old `text`/generate).
- [ ] **Step 5 — commit** `feat(qa): wire flat story pipeline — retrieve→write→bind→verify, redraft, degradation, SSE`.

---

## Task 8 — Backend suite green + isolation grep + dispatch regression

**Files:** test `tests/test_qa_isolation.py`; clean obsolete `test_qa_*` referencing removed paths.

- [ ] **Step 1 — implement isolation test:** assert `qa.py` + `prompts/qa.py` source contains
  none of `deep_tutor|orchestrator_workers|ow_deepagents|ow_skills`; assert mode `"qa"` still
  routes (regression: `router`/`modes` unchanged).
- [ ] **Step 2 — full backend suite + grep:**
```bash
.venv/bin/python -m pytest src/services/chat/tests/ -k "qa or extension or mode_routing or mode_parity" -v
grep -rn "deep_tutor\|orchestrator_workers\|ow_deepagents\|ow_skills" src/services/chat/agents/qa.py src/services/chat/prompts/qa.py src/services/chat/research.py
```
  Expected: tests PASS; grep empty (exit 1).
- [ ] **Step 3 — commit** `test(qa): isolation grep + dispatch regression + obsolete-test cleanup`.

---

## Task 9 — Frontend lockstep (card + types + diagram + thread + modal)

**Files:** `web/src/types.ts`, `QAAnswerCard.tsx`, `data/qaPipeline.ts`, `QAPipelineDiagram.tsx`,
`MessageThread.tsx`, `data/qaMode.ts`, `modals/QAModeModal.tsx`; tests `types.qa.test.ts`,
`qaPipeline.test.ts`, `QAPipelineDiagram.test.tsx`, `QAAnswerCard.test.tsx`.

- [ ] **Step 1 — failing tests:** `types.qa.test.ts` — `QAStoryAnswer{intro,deepening,conclusion,
  scope(+wiki_terms),citations:StoryCitation[],math_blocks,grounding}` typechecks; `qaPipeline.test.ts`
  — node ids include `scope`,`retrieve`,`write`,`bind`,`verify`; `bind` node is data/pure-code
  (no model); `QAAnswerCard.test.tsx` — renders intro/deepening/conclusion, a corpus 📕 chip and
  a wiki 🌐 chip from `citations`, and the legacy `{text}` payload still renders via the legacy
  branch.
- [ ] **Step 2 — run, verify fail.**
- [ ] **Step 3 — `types.ts`** — `QAScope += wiki_terms: string[]`; add `QAStoryAnswer`; reuse the
  existing `StoryCitation` TS type (from extension types).
- [ ] **Step 4 — `QAAnswerCard.tsx`** — render intro (lead `<p>`), deepening via
  `renderInlineWithCites` + `MathBlock`, conclusion; citation chips borrowed from
  `StoryDigestCard.tsx` (📕 corpus / 🌐 wiki, wiki chip links `url`); grounding badge; "N corpus +
  M wikipedia sources" hint; **legacy discriminator**: payload with `text` → existing legacy render.
- [ ] **Step 5 — `qaPipeline.ts` + `QAPipelineDiagram.tsx`** — nodes `scope → retrieve → write →
  bind → verify` (+ `clarify`); `bind` is a pure-code node (no model dropdown); model dropdowns on
  scope/write/verify (`defaultModel: nano`); edges incl. the corpus∥wiki parallel hint on
  `retrieve`. Update diagram test-ids/order.
- [ ] **Step 6 — `MessageThread.tsx`** — `progress` (`retrieving`→"Retrieving…",
  `writing`→"Writing…", `binding`→"Binding citations…", `redraft`→"Re-drafting…"); branch
  `schema==="QAStoryAnswer"` → `<QAAnswerCard>`; legacy `QAAnswer` still routes to the card.
- [ ] **Step 7 — `qaMode.ts` + `QAModeModal.tsx`** — copy → storytelling + wiki pipeline.
- [ ] **Step 8 — run frontend tests** → PASS; `cd web && npx tsc --noEmit` clean.
- [ ] **Step 9 — commit** `feat(qa-web): storytelling card + 📕/🌐 chips, QAStoryAnswer types, flat diagram, progress, legacy guard`.

---

## Task 10 — Docs lockstep (dual surface + modal) + browser verify

**Files:** rewrite `docs/services/chat-features/51-qa-mode.md`; modify
`docs/common ground/Elements/modes/qa.html`, `docs/services/chat.md`,
`docs/system/invariants.md`, `docs/system/changelog.md`.

- [ ] **Step 1 — markdown doc:** rewrite `51-qa-mode.md` — architecture (scope→retrieve(corpus∥
  wiki)→write→bind→verify), mermaid matching `qaPipeline.ts`, the anti-tutor refusal table (spec
  §1), wiki strategy (§6), the verbatim-binder trust boundary (§5), env table (§8), SSE +
  progress, isolation note, lockstep checklist.
- [ ] **Step 2 — HTML doc (dual surface):** update both Q&A diagrams in
  `docs/common ground/Elements/modes/qa.html` to the new flat pipeline (must match the modal).
- [ ] **Step 3 — changelog:** dated entry — "Q&A rebuilt: storytelling intro→deepening→conclusion
  voice + Wikipedia grounding (shared `research.py`); pure-code verbatim citation binder (📕/🌐);
  flat pipeline, no deepagents; anti-tutor guarantee tightened to 3 fixed fields + heading lint;
  legacy `QAAnswer{text}` convs keep legacy render." Reference spec + plan.
- [ ] **Step 4 — invariant:** add — "Q&A emits only `QAStoryAnswer{intro,deepening,conclusion}`
  (no `text`/`sections`/`aspects`/`figures`); Q&A citations are bound by pure code from real
  `Evidence.meta` (never model-authored); Q&A never imports tutor modules." Include the grep.
- [ ] **Step 5 — `chat.md`:** update the Q&A row.
- [ ] **Step 6 — full suites + browser verify** —
```bash
.venv/bin/python -m pytest src/services/chat/tests/ -q
cd web && npx vitest run && npx tsc --noEmit
```
  Then `./scripts/dev.sh` → `http://localhost:5175`, Q&A, scope a book with a wiki-friendly topic:
  1. "why does Chebyshev's inequality bound the tail probability?" → intro→deepening→conclusion
     storytelling prose; **both** a 📕 corpus chip and a 🌐 wikipedia chip render; wiki chip opens
     the article; no headings; grounding badge; **no tutor scaffolding**; 0 console errors.
  2. Corpus-miss topic → honest "cannot answer" in the 3-field shape, no fabricated citation.
  3. Open the Q&A `(i)` modal → new flat node graph; matches `Elements/modes/qa.html`.
  Diagnose with nano (OpenAI), not Groq, to avoid JSON flakiness masking logic.
- [ ] **Step 7 — commit** `docs(qa): lockstep — feature 51, qa.html, changelog, invariant, chat.md for story+wiki Q&A`.

---

## Self-review

- **Spec coverage:** shared research.py (T1); schemas (T2); prompts (T3); retrieve∥wiki + binder
  (T4); scope wiki_terms + writer (T5); verify + fallback (T6); pipeline+redraft+degradation+SSE
  (T7); isolation+suite (T8); frontend incl. 📕/🌐 chips + legacy guard (T9); dual-surface docs +
  browser verify (T10). All spec §§ mapped.
- **Trust boundary:** writer schema has no citations (T2); `qa_bind` builds them verbatim (T4);
  property tests assert verbatim-meta + marker↔citation bijection (T4).
- **Anti-tutor:** 3 fixed fields (T2 schema test), heading strip (T4), isolation grep (T8),
  invariant (T10).
- **No regression:** `_fallback_story` guarantees a `QAStoryAnswer` even if the writer fails (T6/T7).
- **Isolation:** T1 extracts into the shared chat module (intra-service, wall-compliant); T8 grep
  proves no tutor imports; no task touches a tutor file.
- **Test seam:** every LLM call goes through `qa._chat`; retrieve/wiki monkeypatched; no live LLM
  or network in units.
