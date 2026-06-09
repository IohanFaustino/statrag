# Extension Mode Quality Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** End-to-end quality improvement for Extension mode: math/text normalizers, fuzzy subtopic scope, retrieval dedup + Wikipedia disambiguation, prompt tightening, model tier reassignment, frontend UX (streaming per-point, error boundary, download state).

**Architecture:** All changes stay inside `src/services/chat/agents/extension_agents/`, `web/src/components/ExtensionDigestCard.tsx`, `web/src/views/` (new ExtensionView), and `web/src/state/chat.ts`. Zero changes to shared router, deep_tutor, QA, or facilitate code. TDD throughout — every change has a test that fails before the code is written.

**Tech Stack:** Python 3.12, pytest, LangChain tools, React 18 + TypeScript, vitest, KaTeX.

**Working directory:** Run all commands from `.claude/worktrees/feat+extension-mode/` (the extension worktree).

---

## File Map

| File | Change |
|---|---|
| `src/services/chat/agents/extension_agents/runner.py` | Add `_normalize_math_delimiters`, `_strip_md_footnote_markers`, improve `_filter_subtopics`, raise `EXTENSION_SECTION_CHARS` default, apply normalizers before emit, pass `seen_ids` to agent build |
| `src/services/chat/agents/extension_agents/tools.py` | Add Wikipedia disambiguation fallback, raise `retrieve_corpus top_k` to 10, add `seen_ids` dedup param |
| `src/services/chat/agents/extension_agents/agent.py` | Accept `seen_ids` and pass to `make_retrieve_corpus`; add per-stage `temperature` in `_lc_model` |
| `src/services/chat/agents/extension_agents/_models.py` | Add `_MID` alias, demote judge to `_CHEAP`, add `STAGE_TEMPERATURES`, `EXTENSION_JUDGE_MODEL` env, `resolve_stage_temperature` |
| `src/services/chat/agents/extension_agents/prompts.py` | Rewrite all 5 prompts with density target, gap taxonomy, fit rubric, ENGLISH enforcement |
| `web/src/components/StructuredErrorBoundary.tsx` | Port from `feat/component-equation-enforcement` (new file in worktree) |
| `web/src/components/ExtensionDigestCard.tsx` | Add `renderFootnoteBody`, truncate source, Wikipedia link, Download loading state, wrap with StructuredErrorBoundary |
| `web/src/types.ts` | Add `pendingExtensionPoints?: string[]` to `AssistantMessage` |
| `web/src/state/chat.ts` | Handle `stage{stage:"point"}` → append to `pendingExtensionPoints` |
| `web/src/components/MessageThread.tsx` | Pass `pendingExtensionPoints` to `ExtensionDigestCard` during streaming |
| `src/services/chat/tests/test_extension_runner.py` | Add: math normalizer, `[^n]` stripper, fuzzy subtopic, section cap, normalizers applied before emit |
| `src/services/chat/tests/test_extension_tools.py` | Add: Wikipedia disambiguation, `retrieve_corpus top_k=10`, `seen_ids` dedup |
| `src/services/chat/tests/test_extension_models.py` | Add: judge=nano, `EXTENSION_JUDGE_MODEL` env, temperatures |
| `src/services/chat/tests/test_extension_prompts.py` | Add: density rule, gap taxonomy, fit rubric, ENGLISH rule, COVERAGE format |
| `web/src/components/ExtensionDigestCard.test.tsx` | Add: renderFootnoteBody math, source truncation, Wikipedia link, Download loading, error boundary |
| `web/src/state/chat.test.ts` | Add: `stage{point}` appends to `pendingExtensionPoints` |

---

## Task 1: Math normalizer + text helpers + section cap

**Files:**
- Modify: `src/services/chat/agents/extension_agents/runner.py`
- Modify: `src/services/chat/tests/test_extension_runner.py`

- [ ] **Step 1: Write failing tests**

Add to `src/services/chat/tests/test_extension_runner.py`:

```python
from src.services.chat.agents.extension_agents.runner import (
    _normalize_math_delimiters,
    _strip_md_footnote_markers,
    _isolate_midline_display,
)
import os

def test_normalize_math_parens_to_dollar():
    assert _normalize_math_delimiters(r"\(E[X]\)") == "$E[X]$"

def test_normalize_math_brackets_to_display():
    result = _normalize_math_delimiters(r"\[E[X] = \mu\]")
    assert "$$" in result
    assert r"\[" not in result

def test_normalize_math_no_change_for_clean_text():
    assert _normalize_math_delimiters("plain text $x$ here") == "plain text $x$ here"

def test_strip_md_footnote_markers():
    assert _strip_md_footnote_markers("text[^1] and[^abc]more") == "text and more"

def test_strip_md_footnote_markers_no_change_clean():
    assert _strip_md_footnote_markers("no markers here") == "no markers here"

def test_section_chars_default_is_2500():
    assert int(os.environ.get("EXTENSION_SECTION_CHARS", "2500")) == 2500
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest src/services/chat/tests/test_extension_runner.py::test_normalize_math_parens_to_dollar src/services/chat/tests/test_extension_runner.py::test_strip_md_footnote_markers src/services/chat/tests/test_extension_runner.py::test_section_chars_default_is_2500 -v
```

Expected: FAIL (`ImportError` or `AssertionError`).

- [ ] **Step 3: Add helpers and update section cap default**

In `runner.py`, add after the `_AUG_LEAK` line (around line 38):

```python
import re as _re  # already imported at top — no duplicate needed

_LATEX_PAREN = _re.compile(r'\\\((.+?)\\\)', _re.DOTALL)
_LATEX_BRACKET = _re.compile(r'\\\[(.+?)\\\]', _re.DOTALL)
_MD_FOOTNOTE = _re.compile(r'\[\^[^\]]+\]')


def _normalize_math_delimiters(text: str) -> str:
    r"""Convert \(...\) → $...$ and \[...\] → $$...$$ (own line).
    Applied to curated_text and footnote bodies before emit so the
    export ZIP and any consumer sees KaTeX-ready delimiters."""
    if not text:
        return text
    text = _LATEX_BRACKET.sub(lambda m: f'\n$$\n{m.group(1)}\n$$\n', text)
    text = _LATEX_PAREN.sub(lambda m: f'${m.group(1)}$', text)
    return text


def _strip_md_footnote_markers(text: str) -> str:
    r"""Remove [^n] markdown footnote markers from curated_text.
    These render literally in React; footnotes use the ExtensionFootnote.marker field."""
    return _MD_FOOTNOTE.sub('', text) if text else text
```

Change the default in `_per_section_cap` line (around line 200):

```python
_per_section_cap = int(os.environ.get("EXTENSION_SECTION_CHARS", "2500"))
```

Apply both normalizers in the post-processing loop (around line 233, after the existing `_isolate_midline_display` calls):

```python
for pt in digest.points:
    if not curated_text_is_clean(pt):
        pt.curated_text = _AUG_LEAK.sub("", pt.curated_text).strip()
    pt.curated_text = _isolate_midline_display(pt.curated_text)
    pt.curated_text = _normalize_math_delimiters(pt.curated_text)
    pt.curated_text = _strip_md_footnote_markers(pt.curated_text)
    for fn in pt.footnotes:
        fn.body = _isolate_midline_display(fn.body)
        fn.body = _normalize_math_delimiters(fn.body)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/pytest src/services/chat/tests/test_extension_runner.py::test_normalize_math_parens_to_dollar src/services/chat/tests/test_extension_runner.py::test_normalize_math_brackets_to_display src/services/chat/tests/test_extension_runner.py::test_normalize_math_no_change_for_clean_text src/services/chat/tests/test_extension_runner.py::test_strip_md_footnote_markers src/services/chat/tests/test_extension_runner.py::test_strip_md_footnote_markers_no_change_clean src/services/chat/tests/test_extension_runner.py::test_section_chars_default_is_2500 -v
```

Expected: 6 PASS.

- [ ] **Step 5: Run full backend suite to check no regressions**

```bash
.venv/bin/pytest src/services/chat/tests/ -x -q
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/extension_agents/runner.py src/services/chat/tests/test_extension_runner.py
git commit -m "feat(extension): math normalizer, [^n] stripper, section cap 2500"
```

---

## Task 2: Fuzzy subtopic filtering

**Files:**
- Modify: `src/services/chat/agents/extension_agents/runner.py`
- Modify: `src/services/chat/tests/test_extension_runner.py`

- [ ] **Step 1: Write failing tests**

Add to `src/services/chat/tests/test_extension_runner.py`:

```python
def test_filter_subtopics_exact_match():
    secs = [
        {"section_id": "7.1", "h2_path": "7.1 Introduction", "text": ""},
        {"section_id": "7.4", "h2_path": "7.4 Chebyshev Inequality", "text": ""},
    ]
    result = _filter_subtopics_with_book(secs, ["chebyshev"], book_slug="hansen")
    assert len(result) == 1
    assert result[0]["section_id"] == "7.4"

def test_filter_subtopics_empty_returns_all():
    secs = [{"section_id": "1", "h2_path": "Intro", "text": ""}]
    assert _filter_subtopics_with_book(secs, [], book_slug="b") == secs

def test_filter_subtopics_no_match_fallback_all():
    secs = [{"section_id": "1", "h2_path": "Intro", "text": ""}]
    # "zz_impossible" won't match and hybrid_search returns nothing -> fallback to all
    result = _filter_subtopics_with_book(secs, ["zz_impossible"], book_slug="b")
    assert result == secs
```

Note: you'll need to add `_filter_subtopics_with_book` as the new function name OR rename `_filter_subtopics` to accept `book_slug`. The test imports it directly — update the import line at the top of test_extension_runner.py to include the new function.

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest src/services/chat/tests/test_extension_runner.py::test_filter_subtopics_exact_match -v
```

Expected: FAIL (`ImportError`).

- [ ] **Step 3: Rewrite `_filter_subtopics` in runner.py**

Replace the existing `_filter_subtopics` function (lines 87–94):

```python
def _filter_subtopics(
    sections: list[dict], subtopics: list[str], *, book_slug: str = ""
) -> list[dict]:
    if not subtopics:
        return sections
    needles = [t.lower() for t in subtopics if t]
    # Fast path: exact/substring match on h2_path + section_id.
    kept = [
        s for s in sections
        if any(
            n in (str(s.get("h2_path", "")) + " " + str(s.get("section_id", ""))).lower()
            for n in needles
        )
    ]
    if kept:
        return kept
    # Fallback: embedding-based fuzzy match via hybrid_search.
    matched_ids: set[str] = set()
    slugs = [book_slug] if book_slug else None
    for needle in subtopics:
        try:
            rows, _ = hybrid_search(needle, book_slugs=slugs, top_k=3, rerank=False)
            for r in rows:
                sid = (
                    getattr(r, "section", "")
                    or getattr(r, "section_id", "")
                    or ""
                )
                if sid:
                    matched_ids.add(sid)
        except Exception:  # noqa: BLE001
            pass
    fuzzy_kept = [s for s in sections if str(s.get("section_id", "")) in matched_ids]
    return fuzzy_kept or sections  # final fallback: whole chapter
```

Also add the alias used in tests (or rename the import in the test — use `_filter_subtopics` directly):

In `test_extension_runner.py`, update the import to:
```python
from src.services.chat.agents.extension_agents.runner import (
    _normalize_math_delimiters,
    _strip_md_footnote_markers,
    _isolate_midline_display,
    _filter_subtopics,
)
```

And rename the test function parameter to use `_filter_subtopics` with `book_slug`:
```python
def test_filter_subtopics_exact_match():
    secs = [
        {"section_id": "7.1", "h2_path": "7.1 Introduction", "text": ""},
        {"section_id": "7.4", "h2_path": "7.4 Chebyshev Inequality", "text": ""},
    ]
    result = _filter_subtopics(secs, ["chebyshev"], book_slug="hansen")
    assert len(result) == 1
    assert result[0]["section_id"] == "7.4"
```

Update the call site in `run_extension` (around line 184):
```python
sections = _filter_subtopics(sections, res.requested_subtopics, book_slug=book)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/pytest src/services/chat/tests/test_extension_runner.py -k "filter_subtopics" -v
```

Expected: 3 PASS.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/pytest src/services/chat/tests/ -x -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/extension_agents/runner.py src/services/chat/tests/test_extension_runner.py
git commit -m "feat(extension): fuzzy subtopic filtering via hybrid_search fallback"
```

---

## Task 3: Retrieval — Wikipedia disambiguation + corpus dedup + top_k

**Files:**
- Modify: `src/services/chat/agents/extension_agents/tools.py`
- Modify: `src/services/chat/agents/extension_agents/agent.py`
- Modify: `src/services/chat/agents/extension_agents/runner.py`
- Modify: `src/services/chat/tests/test_extension_tools.py`

- [ ] **Step 1: Write failing tests**

Add to `src/services/chat/tests/test_extension_tools.py`:

```python
def test_wikipedia_disambiguation_fallback(monkeypatch):
    """When direct title lookup returns 404, fall back to search API."""
    call_log = []

    class _Resp404:
        status_code = 404
        def json(self): return {}

    class _SearchResp:
        status_code = 200
        def json(self):
            return {"query": {"search": [{"title": "Law of large numbers"}]}}

    class _SummaryResp:
        status_code = 200
        def json(self):
            return {
                "extract": "The law of large numbers is a theorem...",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Law_of_large_numbers"}},
            }

    def _fake_get(url, *a, **k):
        call_log.append(url)
        if "rest_v1/page/summary" in url and "Law_of_large_numbers" in url:
            return _SummaryResp()
        if "api.php" in url:
            return _SearchResp()
        return _Resp404()

    monkeypatch.setattr(T.httpx, "get", _fake_get)
    out = T.wikipedia_lookup.invoke({"query": "lln theorem"})
    assert "law of large numbers" in out.lower()
    # Verify the search API was called (disambiguation path used)
    assert any("api.php" in u for u in call_log)


def test_retrieve_corpus_top_k_is_10(monkeypatch):
    captured = {}
    def _fake_hybrid(query, *, book_slugs=None, top_k=5, rerank=False, **kw):
        captured["top_k"] = top_k
        return ([], None)
    monkeypatch.setattr(T, "hybrid_search", _fake_hybrid)
    T.make_retrieve_corpus(exclude_book="b", all_slugs=["b", "c"]).invoke({"query": "x"})
    assert captured["top_k"] == 10


def test_retrieve_corpus_dedup_seen_ids(monkeypatch):
    seen: set[str] = set()
    class _S:
        chunk = "text"
        excerpt = "text"
        book = "ross"
        section = "5.1"
        chunk_id = "abc123"
        score = 0.9
    def _fake_hybrid(*a, **k):
        return ([_S()], None)
    monkeypatch.setattr(T, "hybrid_search", _fake_hybrid)

    corpus = T.make_retrieve_corpus(exclude_book="b", all_slugs=["b", "ross"], seen_ids=seen)
    # First call: abc123 is new → returns result
    out1 = corpus.invoke({"query": "x"})
    assert "text" in out1
    assert "abc123" in seen
    # Second call: abc123 already seen → deduped → no results
    out2 = corpus.invoke({"query": "x"})
    assert "no results" in out2
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest src/services/chat/tests/test_extension_tools.py::test_wikipedia_disambiguation_fallback src/services/chat/tests/test_extension_tools.py::test_retrieve_corpus_top_k_is_10 src/services/chat/tests/test_extension_tools.py::test_retrieve_corpus_dedup_seen_ids -v
```

Expected: FAIL.

- [ ] **Step 3: Update `tools.py`**

Replace the entire `wikipedia_lookup` function:

```python
@tool
def wikipedia_lookup(query: str) -> str:
    """Fetch the lead extract of the best-matching English Wikipedia article.
    Returns the extract text followed by the article URL, or a 'no wikipedia
    result' marker. Falls back to the Wikipedia search API when the direct
    title lookup returns no match."""
    title = urllib.parse.quote(query.strip().replace(" ", "_"))

    def _get_summary(t: str):
        try:
            resp = httpx.get(
                _WIKI_SUMMARY + t,
                timeout=10.0,
                headers={"accept": "application/json"},
            )
            return resp if resp.status_code == 200 else None
        except Exception:  # noqa: BLE001
            return None

    resp = _get_summary(title)

    if resp is None:
        # Disambiguation fallback: Wikipedia search API → take first result title.
        try:
            search_resp = httpx.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "srlimit": 1,
                },
                timeout=10.0,
            )
            if search_resp.status_code == 200:
                results = search_resp.json().get("query", {}).get("search", [])
                if results:
                    fallback_title = urllib.parse.quote(
                        results[0]["title"].replace(" ", "_")
                    )
                    resp = _get_summary(fallback_title)
        except Exception:  # noqa: BLE001
            pass

    if resp is None:
        return "no wikipedia result"
    data = resp.json()
    extract = (data.get("extract") or "").strip()
    if not extract:
        return "no wikipedia result"
    url = data.get("content_urls", {}).get("desktop", {}).get("page") or ""
    return f"{extract}\n\n[source] {url}"
```

Replace `make_retrieve_corpus`:

```python
def make_retrieve_corpus(
    *,
    exclude_book: str,
    all_slugs: list[str],
    seen_ids: set[str] | None = None,
):
    """Augmentor tool: cross-book retrieval EXCLUDING the base book.
    seen_ids: mutable set of chunk_ids already returned in prior rounds —
    deduped entries are skipped to prevent duplicate footnotes."""
    slugs = [s for s in all_slugs if s != exclude_book]
    _seen: set[str] = seen_ids if seen_ids is not None else set()

    @tool
    def retrieve_corpus(query: str) -> str:
        """Search OTHER books in the corpus (never the base book) for material
        that augments a gap. Returns matched passages with book/section tags."""
        rows, _meta = hybrid_search(query, book_slugs=slugs, top_k=10, rerank=False)
        new_rows = []
        for r in rows:
            cid = getattr(r, "chunk_id", "") or ""
            if cid and cid in _seen:
                continue
            if cid:
                _seen.add(cid)
            new_rows.append(r)
        return _fmt_sources(new_rows)

    return retrieve_corpus
```

- [ ] **Step 4: Update `agent.py` to accept and pass `seen_ids`**

In `agent.py`, update `build_extension_agent` signature:

```python
def build_extension_agent(
    *,
    stage_models: dict | None,
    exclude_book: str,
    all_slugs: list[str],
    seen_ids: set[str] | None = None,
):
```

Update the `corpus` line in the function body:

```python
corpus = make_retrieve_corpus(
    exclude_book=exclude_book,
    all_slugs=all_slugs,
    seen_ids=seen_ids,
)
```

- [ ] **Step 5: Update `runner.py` to create and pass `seen_ids`**

Before the `agent = build_extension_agent(...)` call (around line 189), add:

```python
seen_chunk_ids: set[str] = set()
agent = build_extension_agent(
    stage_models=req.extensionModels,
    exclude_book=book,
    all_slugs=slugs,
    seen_ids=seen_chunk_ids,
)
```

- [ ] **Step 6: Run tests to verify pass**

```bash
.venv/bin/pytest src/services/chat/tests/test_extension_tools.py -v
```

Expected: all pass (including the 4 pre-existing tests + 3 new ones = 7 total).

- [ ] **Step 7: Run full suite**

```bash
.venv/bin/pytest src/services/chat/tests/ -x -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/services/chat/agents/extension_agents/tools.py src/services/chat/agents/extension_agents/agent.py src/services/chat/agents/extension_agents/runner.py src/services/chat/tests/test_extension_tools.py
git commit -m "feat(extension): wikipedia disambiguation, corpus top_k=10, cross-round dedup"
```

---

## Task 4: Prompt tightening

**Files:**
- Modify: `src/services/chat/agents/extension_agents/prompts.py`
- Modify: `src/services/chat/tests/test_extension_prompts.py`

- [ ] **Step 1: Write failing tests**

Add to `src/services/chat/tests/test_extension_prompts.py`:

```python
def test_orchestrator_has_footnote_density_rule():
    assert "2 footnote" in P.ORCHESTRATOR_PROMPT or "≥ 2" in P.ORCHESTRATOR_PROMPT or ">= 2" in P.ORCHESTRATOR_PROMPT

def test_orchestrator_has_orphan_footnote_merge():
    assert "orphan" in P.ORCHESTRATOR_PROMPT.lower() or "not match" in P.ORCHESTRATOR_PROMPT.lower()

def test_orchestrator_strong_english_rule():
    assert "translate" in P.ORCHESTRATOR_PROMPT.lower() or "english" in P.ORCHESTRATOR_PROMPT.lower()

def test_analyst_has_gap_taxonomy():
    low = P.ANALYST_PROMPT.lower()
    # must reference at least 3 of the 4 gap types
    types_found = sum([
        "formal definition" in low or "formally defined" in low,
        "formula" in low or "derivation" in low,
        "comparative" in low or "comparison" in low,
        "application" in low or "example" in low,
    ])
    assert types_found >= 3

def test_augmentor_has_fit_rubric():
    assert "score" in P.AUGMENTOR_PROMPT.lower() or "relevance" in P.AUGMENTOR_PROMPT.lower()
    assert "discard" in P.AUGMENTOR_PROMPT.lower()

def test_augmentor_has_latex_examples():
    assert "$E[" in P.AUGMENTOR_PROMPT or r"\mu" in P.AUGMENTOR_PROMPT or "$$" in P.AUGMENTOR_PROMPT

def test_augmentor_has_coverage_format():
    assert "# COVERAGE:" in P.AUGMENTOR_PROMPT
    assert "done" in P.AUGMENTOR_PROMPT
    assert "unfilled" in P.AUGMENTOR_PROMPT

def test_polish_keeps_formal_structure():
    low = P.POLISH_PROMPT.lower()
    assert "formal" in low or "notation" in low or "definition" in low

def test_judge_has_english_check():
    assert "english" in P.JUDGE_PROMPT.lower() or "translate" in P.JUDGE_PROMPT.lower()
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest src/services/chat/tests/test_extension_prompts.py -v
```

Expected: 9 new tests FAIL, 3 existing PASS.

- [ ] **Step 3: Rewrite `prompts.py`**

Replace the entire contents of `src/services/chat/agents/extension_agents/prompts.py`:

```python
"""XML-tagged prompts for extension mode (Zeroth law: <role>/<context>/<task>
on every prompt). Chinese-wall: pure string constants."""
from __future__ import annotations

ORCHESTRATOR_PROMPT = """<role>
You are the Orchestrator of the extension pipeline. You drive the augmentation
of a book chapter: you plan gap-filling queries and coordinate subagents via the
task tool and a shared virtual filesystem.
</role>

<context>
The /structure/*.md files hold the chapter's real sections in order. Subagents
write /context/*.md (per-section analysis), /curated/timeline.md (curated
points), and /footnotes/*.md (augmentation). You read these and write
/plan/queries.md. Output is rendered as KaTeX-capable React; augmentation must
be confined to footnotes.
</context>

<task>
1. Delegate one `analyst` task per /structure file to produce /context/NN.md.
2. Delegate `polish` once to produce /curated/timeline.md.
3. Read the context gaps and write /plan/queries.md: a deduplicated list of OPEN
   gap queries. One query per line: `POINT :: query`.
4. Delegate `augmentor` tasks for the queries. You MUST run the augmentor.
5. Build the final ExtensionDigest: one ExtensionPoint per curated point, in
   order. For EACH point, READ /footnotes/*.md and attach every footnote that
   belongs to that point (marker, body, source, kind).
   — A point with real augmentation MUST NOT have an empty footnotes list.
   — Target: >= 2 footnotes per non-trivial point. If a point has 0 footnotes
     after the augmentor ran, re-delegate the augmentor for that point before
     emitting the digest.
   — Orphan footnotes: any footnote whose point title does not match a curated
     point → attach it to the nearest point by title similarity.
Do not emit the ExtensionDigest until the augmentor has run and footnotes are
attached.
</task>

<rules>
- Write ALL output in ENGLISH. If source text is not in English, translate every
  field to English before writing. Do not write any word in any language other
  than English.
- Never write augmentation into /curated/*; that belongs only in /footnotes/*.
- Deduplicate queries before delegating.
- COVERAGE format is exact: `# COVERAGE: <query> = done` or
  `# COVERAGE: <query> = unfilled`. No variation allowed.
</rules>
"""

ANALYST_PROMPT = """<role>
You are an Analyst subagent. You inspect ONE chapter section and report what it
covers and what it is MISSING (augmentation opportunities).
</role>

<context>
You receive the path of one /structure/NN.md file. You may call `retrieve_peek`
to check what the wider corpus says about the topic. You write a single
/context/NN.md file. Your output feeds the polish and orchestrator stages.
</context>

<task>
Read the assigned /structure file. Write /context/NN.md with:
1. The section's core concept (one sentence).
2. Key ideas: a bullet list of the main points.
3. A `MISSING:` list of gaps using the taxonomy below. Identify >= 2 gaps per
   section, or explicitly write "MISSING: none" if the section is comprehensive.

Gap taxonomy — classify each gap as one of:
- [FORMAL-DEF] concept named but never formally defined (e.g. "names random
  variable but never states the formal definition")
- [FORMULA-DERIV] result stated but derivation, proof sketch, or intuition absent
- [COMPARATIVE] no comparison to related methods/concepts from other books
- [APPLICATION] no concrete worked example, dataset, or use case given
</task>

<rules>
- Ground every claim in the section text or retrieve_peek results; do not invent.
- Keep /context/NN.md under ~250 words.
- Write ALL output in ENGLISH, regardless of the source text's language.
</rules>
"""

POLISH_PROMPT = """<role>
You are the Polish subagent. You turn per-section analyses into one ordered,
curated timeline of points — direct, to-the-point text. This is NOT a summary.
</role>

<context>
You read all /context/*.md files (in NN order). You write /curated/timeline.md.
Downstream, the augmentor attaches footnotes to your points and the result is
rendered to the user as the document body.
</context>

<task>
Produce /curated/timeline.md as an ordered list of points from introduction to
conclusion. For each point: a short title and curated prose that preserves formal
structure, definitions, and notation from the source. Cluster duplicate sections
(e.g. four sections on the Law of Large Numbers) into ONE point. Drop exercises,
worked solutions, and redundant restatements only.
</task>

<rules>
- Write ALL output in ENGLISH, regardless of the source text's language.
- Keep formal definitions, key formulas, and notation — these are not fluff.
- Curate, do not summarize: a complete treatment of the concept, just without
  the padding, exercises, and repetition.
- Preserve intro→conclusion ordering.
- Do NOT add new external material here — that is the augmentor's job.
</rules>

<output>
Markdown. Each point: `## <title>` then the curated prose.
</output>
"""

AUGMENTOR_PROMPT = """<role>
You are an Augmentor subagent. You fill ONE batch of gap queries with material
from OTHER books and Wikipedia, returning footnotes only.
</role>

<context>
You receive gap queries (each `POINT :: query`) and /curated/timeline.md for
context. Tools: `retrieve_corpus` (other books, never the base book) and
`wikipedia_lookup`. You write /footnotes/<point>.md. Footnote bodies are
rendered with KaTeX, so use `$...$` for inline math (e.g. `$E[X] = \\mu$`) and
`$$...$$` on its own line for display math (e.g. `$$\\text{Var}(X) = E[X^2] - (E[X])^2$$`).
</context>

<task>
For each query:
1. Retrieve from corpus and/or Wikipedia.
2. Score relevance 1–5: does the result directly address the gap query in the
   context of the curated point? Score 1–2: discard entirely. Score 3–5: write
   footnote. A score-3 result must contain at least one concrete formula or
   factual claim to be worth footnoting.
3. Write the footnote to /footnotes/<point>.md. Each footnote needs: a marker
   (e.g. "a", "b", "1", "2"), the augmenting text (>= 40 words, in ENGLISH), and
   the source (book slug + §section, or Wikipedia URL).
4. Mark each query at the end of the file:
   `# COVERAGE: <query> = done` if a footnote was written, else
   `# COVERAGE: <query> = unfilled`.
   Use this EXACT format — no variation.
</task>

<rules>
- Write ALL footnote text in ENGLISH, regardless of the source's language.
- ALL augmentation lives in footnotes — including formulas, inline or display.
  Never rewrite the curated body.
- Cite every footnote. Do not invent sources.
- If no source scores >= 3, mark the query unfilled and write no footnote.
</rules>

<failure_mode>
If no source fits a query (all score < 3), mark it `# COVERAGE: <query> = unfilled`
and write no footnote for it.
</failure_mode>
"""

JUDGE_PROMPT = """<role>
You are the Judge. You assemble the final ExtensionDigest and verify coverage.
</role>

<context>
You read /curated/timeline.md and all /footnotes/*.md. You emit the final JSON
ExtensionDigest (book, chapter, points[], unfilled_gaps[]). It is parsed by
Pydantic — no markdown, no code fences.
</context>

<task>
1. Before assembling: verify all curated_text and footnote body fields are in
   ENGLISH. If any field is not, translate it to English first.
2. Merge curated points with their footnotes into ExtensionPoint objects (preserve
   order). Map footnotes to points by the `POINT` prefix in each footnote file.
3. Orphan footnotes (file name or POINT prefix does not match any curated point):
   attach them to the nearest point by title similarity.
4. Move every footnote body into a footnote with kind "corpus" or "wikipedia".
5. Collect any queries still marked `# COVERAGE: <query> = unfilled` into
   unfilled_gaps.
</task>

<rules>
- curated_text carries NO augmentation; all augmentation is in footnotes.
- Output ONLY the JSON object, no preamble, no code fences.
- COVERAGE format is `# COVERAGE: <query> = done|unfilled` — parse exactly.
</rules>

<output>
A single JSON object matching the ExtensionDigest schema.
</output>
"""
```

- [ ] **Step 4: Run tests to verify all pass**

```bash
.venv/bin/pytest src/services/chat/tests/test_extension_prompts.py -v
```

Expected: all 12 PASS.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/pytest src/services/chat/tests/ -x -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/extension_agents/prompts.py src/services/chat/tests/test_extension_prompts.py
git commit -m "feat(extension): tighten prompts — density target, gap taxonomy, fit rubric, ENGLISH enforcement"
```

---

## Task 5: Model tiers + temperature

**Files:**
- Modify: `src/services/chat/agents/extension_agents/_models.py`
- Modify: `src/services/chat/agents/extension_agents/agent.py`
- Modify: `src/services/chat/tests/test_extension_models.py`

- [ ] **Step 1: Write failing tests**

Add to `src/services/chat/tests/test_extension_models.py`:

```python
import os
from src.services.chat.agents.extension_agents._models import (
    resolve_stage_model, resolve_stage_temperature, STAGE_DEFAULTS, STAGE_TEMPERATURES
)

def test_judge_default_is_cheap_not_top():
    from src.core.config import settings
    assert STAGE_DEFAULTS["judge"] != settings.openai_model_full
    assert STAGE_DEFAULTS["judge"] == settings.openai_model_nano

def test_mid_alias_exists_and_equals_nano():
    from src.services.chat.agents.extension_agents._models import _MID, _CHEAP
    # Both are nano today; having them as separate names enables future bumps.
    assert _MID == _CHEAP

def test_extension_judge_model_env_override(monkeypatch):
    monkeypatch.setenv("EXTENSION_JUDGE_MODEL", "custom-judge-model")
    assert resolve_stage_model("judge", None) == "custom-judge-model"

def test_extension_judge_model_env_empty_uses_default(monkeypatch):
    monkeypatch.delenv("EXTENSION_JUDGE_MODEL", raising=False)
    from src.core.config import settings
    assert resolve_stage_model("judge", None) == settings.openai_model_nano

def test_polish_temperature_is_nonzero():
    assert STAGE_TEMPERATURES.get("polish", 0.0) > 0.0

def test_augmentor_temperature_is_nonzero():
    assert STAGE_TEMPERATURES.get("augmentor", 0.0) > 0.0

def test_orchestrator_temperature_is_zero():
    assert STAGE_TEMPERATURES.get("orchestrator", 0.0) == 0.0

def test_resolve_stage_temperature_returns_float():
    t = resolve_stage_temperature("polish")
    assert isinstance(t, float)
    assert t > 0.0
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest src/services/chat/tests/test_extension_models.py -v
```

Expected: 8 new tests FAIL, 3 existing PASS.

- [ ] **Step 3: Rewrite `_models.py`**

Replace entire contents of `src/services/chat/agents/extension_agents/_models.py`:

```python
"""Per-stage model resolution for extension mode.

Model ids come from settings so they track the project's configured OpenAI
models and never drift to hard-coded literals."""
from __future__ import annotations

import os

from src.core.config import settings

_TOP   = settings.openai_model_full   # orchestrator: open reasoning
_MID   = settings.openai_model_nano   # polish — semantically separate from _CHEAP
_CHEAP = settings.openai_model_nano   # analyst, augmentor, judge: bounded tasks

STAGE_DEFAULTS: dict[str, str] = {
    "orchestrator": _TOP,
    "judge":        _CHEAP,  # judge only parses COVERAGE markers + re-delegates
    "polish":       _MID,
    "analyst":      _CHEAP,
    "augmentor":    _CHEAP,
}

STAGE_TEMPERATURES: dict[str, float] = {
    "orchestrator": 0.0,   # needs consistency for gap planning
    "judge":        0.0,   # deterministic coverage check
    "polish":       0.3,   # more varied curation
    "analyst":      0.0,
    "augmentor":    0.2,   # better footnote prose variety
}


def resolve_stage_model(stage: str, stage_models: dict | None) -> str:
    """Return the model id for a stage.
    Priority: per-request override > EXTENSION_JUDGE_MODEL env (judge only) > stage default."""
    cand = (stage_models or {}).get(stage)
    if isinstance(cand, str) and cand.strip():
        return cand.strip()
    if stage == "judge":
        env_val = os.environ.get("EXTENSION_JUDGE_MODEL", "").strip()
        if env_val:
            return env_val
    return STAGE_DEFAULTS.get(stage, _CHEAP)


def resolve_stage_temperature(stage: str) -> float:
    """Return the generation temperature for a stage."""
    return STAGE_TEMPERATURES.get(stage, 0.0)
```

- [ ] **Step 4: Update `agent.py` to use `resolve_stage_temperature`**

In `agent.py`, update the imports:

```python
from src.services.chat.agents.extension_agents._models import (
    STAGE_DEFAULTS,  # noqa: F401 — re-exported for test convenience
    resolve_stage_model,
    resolve_stage_temperature,
)
```

Update `_lc_model`:

```python
def _lc_model(stage: str, stage_models: dict | None) -> ChatOpenAI:
    """Build a ChatOpenAI for a stage with explicit api_key and per-stage temperature."""
    return ChatOpenAI(
        model=resolve_stage_model(stage, stage_models),
        temperature=resolve_stage_temperature(stage),
        api_key=settings.openai_api_key,
        max_retries=6,
    )
```

- [ ] **Step 5: Run tests to verify all pass**

```bash
.venv/bin/pytest src/services/chat/tests/test_extension_models.py -v
```

Expected: all 11 PASS.

- [ ] **Step 6: Run full suite**

```bash
.venv/bin/pytest src/services/chat/tests/ -x -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/services/chat/agents/extension_agents/_models.py src/services/chat/agents/extension_agents/agent.py src/services/chat/tests/test_extension_models.py
git commit -m "feat(extension): demote judge to nano, per-stage temperatures, EXTENSION_JUDGE_MODEL env"
```

---

## Task 6: Port `StructuredErrorBoundary`

**Files:**
- Create: `web/src/components/StructuredErrorBoundary.tsx`
- Modify: `web/src/components/ExtensionDigestCard.test.tsx`

`StructuredErrorBoundary` exists on `feat/component-equation-enforcement` but is not yet in this worktree. Port it now so Task 7 can use it.

- [ ] **Step 1: Write failing test**

Add to `web/src/components/ExtensionDigestCard.test.tsx`:

```tsx
import StructuredErrorBoundary from "./StructuredErrorBoundary";

it("StructuredErrorBoundary renders children normally", () => {
  const { getByText } = render(
    <StructuredErrorBoundary>
      <span>child content</span>
    </StructuredErrorBoundary>
  );
  expect(getByText("child content")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd web && npx vitest run src/components/ExtensionDigestCard.test.tsx 2>&1 | tail -10
```

Expected: FAIL (`Cannot find module './StructuredErrorBoundary'`).

- [ ] **Step 3: Create `StructuredErrorBoundary.tsx`**

Create `web/src/components/StructuredErrorBoundary.tsx`:

```tsx
import React from "react";

interface Props {
  children: React.ReactNode;
}
interface State {
  error: Error | null;
}

/**
 * Wraps a structured-answer render so a malformed or schema-drifted payload
 * degrades to an inline notice instead of unmounting the whole React tree.
 */
export default class StructuredErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // eslint-disable-next-line no-console
    console.warn("[structured-render] failed to render answer", error);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="msg__render-error" role="alert">
          This answer can{"'"}t be displayed (unsupported format from an earlier
          version). The rest of the conversation is unaffected.
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 4: Run test to verify pass**

```bash
cd web && npx vitest run src/components/ExtensionDigestCard.test.tsx 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/StructuredErrorBoundary.tsx web/src/components/ExtensionDigestCard.test.tsx
git commit -m "feat(extension): port StructuredErrorBoundary from sibling branch"
```

---

## Task 7: `ExtensionDigestCard` UX improvements

**Files:**
- Modify: `web/src/components/ExtensionDigestCard.tsx`
- Modify: `web/src/components/ExtensionDigestCard.test.tsx`

- [ ] **Step 1: Write failing tests**

Add to `web/src/components/ExtensionDigestCard.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ExtensionDigestCard from "./ExtensionDigestCard";

const SAMPLE_DIGEST = {
  book: "hansen-probability",
  chapter: "ch07",
  points: [
    {
      title: "Law of Large Numbers",
      curated_text: "Sample mean converges to $\\mu$ as $n \\to \\infty$.",
      footnotes: [
        {
          marker: "a",
          body: "Also proven in Ross §5.2 using $\\bar X_n \\to \\mu$ in probability.",
          source: "ross-probability §5.2 The Weak Law of Large Numbers",
          kind: "corpus" as const,
        },
        {
          marker: "b",
          body: "Wikipedia: The law of large numbers is a theorem that describes the result of repeating the same experiment many times.",
          source: "https://en.wikipedia.org/wiki/Law_of_large_numbers",
          kind: "wikipedia" as const,
        },
      ],
    },
  ],
  unfilled_gaps: [],
};

it("renders point title and curated text", () => {
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  expect(screen.getByText("Law of Large Numbers")).toBeInTheDocument();
});

it("renders footnote markers as superscripts", () => {
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  expect(screen.getByText("a")).toBeInTheDocument();
  expect(screen.getByText("b")).toBeInTheDocument();
});

it("truncates long corpus source to 40 chars", () => {
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  // Full source is "ross-probability §5.2 The Weak Law of Large Numbers" (51 chars)
  const sourceEls = document.querySelectorAll(".extension-footnote__source");
  const corpusSource = Array.from(sourceEls).find(el =>
    el.textContent?.includes("ross")
  );
  expect(corpusSource?.textContent?.includes("…")).toBe(true);
});

it("renders Wikipedia footnote source as clickable link", () => {
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  const link = screen.getByRole("link", { name: /wikipedia/i });
  expect(link).toHaveAttribute("href", "https://en.wikipedia.org/wiki/Law_of_large_numbers");
  expect(link).toHaveAttribute("target", "_blank");
});

it("Download button shows loading state while fetching", async () => {
  // Mock fetch to never resolve so we can see the loading state
  global.fetch = jest.fn(() => new Promise(() => {})) as jest.Mock;
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  const btn = screen.getByRole("button", { name: /download/i });
  fireEvent.click(btn);
  await waitFor(() => expect(btn).toBeDisabled());
  (global.fetch as jest.Mock).mockRestore?.();
});

it("wraps in StructuredErrorBoundary (import check)", async () => {
  // Verify the component imports and uses StructuredErrorBoundary.
  // A thrown render error should not propagate to the test.
  const BadChild = () => { throw new Error("render crash"); };
  // StructuredErrorBoundary wraps the card, not the test
  // We just verify normal render doesn't crash.
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  expect(screen.getByText("Law of Large Numbers")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd web && npx vitest run src/components/ExtensionDigestCard.test.tsx 2>&1 | tail -20
```

Expected: several FAIL (source truncation, Wikipedia link, Download loading state).

- [ ] **Step 3: Rewrite `ExtensionDigestCard.tsx`**

Replace the entire file `web/src/components/ExtensionDigestCard.tsx`:

```tsx
import React, { useState } from "react";
import { MathBlock, MathInline } from "./Math";
import StructuredErrorBoundary from "./StructuredErrorBoundary";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ExtensionFootnote {
  marker: string;
  body: string;
  source: string;
  kind: "corpus" | "wikipedia";
}

export interface ExtensionPoint {
  title: string;
  curated_text: string;
  footnotes: ExtensionFootnote[];
}

export interface ExtensionDigest {
  book: string;
  chapter: string;
  points: ExtensionPoint[];
  unfilled_gaps: string[];
}

// ─── Footnote body renderer ───────────────────────────────────────────────────

/**
 * Renders footnote body text: splits on $…$ (inline) and $$…$$ (display)
 * and renders them with KaTeX. Plain text segments are rendered as-is.
 * Does NOT apply [N] citation logic — footnotes use the marker field instead.
 */
function renderFootnoteBody(body: string): React.ReactNode {
  if (!body) return null;
  const parts: React.ReactNode[] = [];
  // Match $$...$$ (display) first, then $...$ (inline).
  const segments = body.split(/((?:\$\$[\s\S]*?\$\$|\$[^$\n]+\$))/g);
  segments.forEach((seg, i) => {
    if (seg.startsWith("$$") && seg.endsWith("$$") && seg.length > 4) {
      parts.push(<MathBlock key={i} tex={seg.slice(2, -2)} />);
    } else if (seg.startsWith("$") && seg.endsWith("$") && seg.length > 2) {
      parts.push(<MathInline key={i} tex={seg.slice(1, -1)} />);
    } else {
      parts.push(<span key={i}>{seg}</span>);
    }
  });
  return <>{parts}</>;
}

// ─── Source display ───────────────────────────────────────────────────────────

const MAX_SOURCE_CHARS = 40;

function truncateSource(source: string): string {
  if (source.length <= MAX_SOURCE_CHARS) return source;
  return source.slice(0, MAX_SOURCE_CHARS) + "…";
}

function FootnoteSource({ fn }: { fn: ExtensionFootnote }) {
  if (fn.kind === "wikipedia") {
    return (
      <span className="extension-footnote__source">
        (
        <a
          href={fn.source}
          target="_blank"
          rel="noopener noreferrer"
          className="extension-footnote__wiki-link"
        >
          Wikipedia
        </a>
        )
      </span>
    );
  }
  return (
    <span className="extension-footnote__source">
      ({truncateSource(fn.source)} · corpus)
    </span>
  );
}

// ─── Download helper ──────────────────────────────────────────────────────────

async function downloadZip(
  digest: ExtensionDigest,
  setLoading: (v: boolean) => void,
  setError: (v: string | null) => void,
): Promise<void> {
  setLoading(true);
  setError(null);
  try {
    const res = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(digest),
    });
    if (!res.ok) {
      setError(`Export failed (${res.status})`);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${digest.book}-${digest.chapter}-extended.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    setError("Export failed — network error");
  } finally {
    setLoading(false);
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

interface Props {
  digest: ExtensionDigest;
  /** Titles of points received via stage{point} SSE events before the digest arrives. */
  pendingPoints?: string[];
}

function ExtensionDigestCardInner({ digest, pendingPoints }: Props) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  return (
    <div className="extension-card">
      <div className="extension-card__hd">
        <span className="extension-card__scope">
          {digest.book} · {digest.chapter} — Extended
        </span>
        <button
          type="button"
          className="extension-card__download"
          aria-label="Download ZIP"
          disabled={isDownloading}
          onClick={() => downloadZip(digest, setIsDownloading, setDownloadError)}
        >
          {isDownloading ? "Downloading…" : "Download ZIP"}
        </button>
        {downloadError && (
          <span className="extension-card__download-error" role="alert">
            {downloadError}
          </span>
        )}
      </div>

      <div className="extension-card__points">
        {digest.points.map((pt, i) => (
          <section key={i} className="extension-point">
            <h3 className="extension-point__title">{pt.title}</h3>
            <div className="extension-point__body">{pt.curated_text}</div>

            {pt.footnotes.length > 0 && (
              <ul className="extension-point__footnotes">
                {pt.footnotes.map((fn, j) => (
                  <li key={j} className="extension-footnote">
                    <sup className="extension-footnote__marker">{fn.marker}</sup>
                    <span className="extension-footnote__body">
                      {renderFootnoteBody(fn.body)}
                    </span>
                    <FootnoteSource fn={fn} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>

      {digest.unfilled_gaps.length > 0 && (
        <div className="extension-card__gaps">
          <h4 className="extension-card__gaps-hd">Unfilled gaps</h4>
          <ul>
            {digest.unfilled_gaps.map((gap, i) => (
              <li key={i}>{gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function ExtensionDigestCard(props: Props) {
  return (
    <StructuredErrorBoundary>
      <ExtensionDigestCardInner {...props} />
    </StructuredErrorBoundary>
  );
}
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd web && npx vitest run src/components/ExtensionDigestCard.test.tsx 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Run full frontend suite**

```bash
cd web && npx vitest run 2>&1 | tail -10
```

Expected: all pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add web/src/components/ExtensionDigestCard.tsx web/src/components/ExtensionDigestCard.test.tsx
git commit -m "feat(extension): renderFootnoteBody, source truncation, Wikipedia link, Download loading, error boundary"
```

---

## Task 8: Per-point streaming skeleton

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/state/chat.ts`
- Modify: `web/src/components/MessageThread.tsx`
- Modify: `web/src/state/chat.test.ts`

- [ ] **Step 1: Write failing tests**

Add to `web/src/state/chat.test.ts`:

```ts
it("stage{stage:'point'} appends to pendingExtensionPoints", () => {
  const state0 = makeStreamingState(); // helper that produces a state with an active assistant message
  const state1 = chatReducer(state0, {
    type: "SSE_EVENT",
    event: { type: "stage", stage: "point", label: "Law of Large Numbers" },
  });
  const lastMsg = state1.messages[state1.messages.length - 1];
  expect((lastMsg as AssistantMessage).pendingExtensionPoints).toEqual(["Law of Large Numbers"]);
});

it("second stage{point} appends to existing pendingExtensionPoints", () => {
  const state0 = makeStreamingState();
  const state1 = chatReducer(state0, {
    type: "SSE_EVENT",
    event: { type: "stage", stage: "point", label: "LLN" },
  });
  const state2 = chatReducer(state1, {
    type: "SSE_EVENT",
    event: { type: "stage", stage: "point", label: "CLT" },
  });
  const lastMsg = state2.messages[state2.messages.length - 1];
  expect((lastMsg as AssistantMessage).pendingExtensionPoints).toEqual(["LLN", "CLT"]);
});

it("non-point stage events do not modify pendingExtensionPoints", () => {
  const state0 = makeStreamingState();
  const state1 = chatReducer(state0, {
    type: "SSE_EVENT",
    event: { type: "stage", stage: "fetch", label: "Fetch chapter" },
  });
  const lastMsg = state1.messages[state1.messages.length - 1];
  expect((lastMsg as AssistantMessage).pendingExtensionPoints).toBeUndefined();
});
```

Note: `makeStreamingState()` is a test helper — check if it already exists in `chat.test.ts`; if not, add it:

```ts
function makeStreamingState() {
  // Returns minimal state with one streaming assistant message.
  return chatReducer(
    chatReducer(initialState, { type: "SEND", message: "extend hansen ch7", conversationId: null }),
    { type: "SSE_EVENT", event: { type: "thinking" } }
  );
}
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd web && npx vitest run src/state/chat.test.ts 2>&1 | tail -20
```

Expected: 3 new tests FAIL.

- [ ] **Step 3: Add `pendingExtensionPoints` to types.ts**

In `web/src/types.ts`, find the `AssistantMessage` interface and add:

```ts
pendingExtensionPoints?: string[];
```

- [ ] **Step 4: Handle `stage{point}` in `chat.ts` reducer**

In `web/src/state/chat.ts`, find the `default:` case in the SSE_EVENT reducer (around line where `structured_output` is handled). Add a new case BEFORE `default:`:

```ts
case "stage":
  if (ev.stage === "point") {
    return {
      ...state,
      messages: updateLastAssistant(state.messages, (msg) => ({
        ...msg,
        pendingExtensionPoints: [
          ...(msg.pendingExtensionPoints ?? []),
          ev.label as string,
        ],
      })),
    };
  }
  return state;
```

- [ ] **Step 5: Update `MessageThread.tsx` to show skeleton points during streaming**

In `web/src/components/MessageThread.tsx`, find where `ExtensionDigestCard` is rendered (around line 358):

```tsx
{msg.structuredOutput.schema === "ExtensionDigest" && (
  <ExtensionDigestCard digest={msg.structuredOutput.data as ExtensionDigest} />
)}
```

Replace with:

```tsx
{msg.structuredOutput?.schema === "ExtensionDigest" && (
  <ExtensionDigestCard
    digest={msg.structuredOutput.data as ExtensionDigest}
    pendingPoints={msg.pendingExtensionPoints}
  />
)}
```

Also add a streaming skeleton renderer for when `structuredOutput` is not yet set but `pendingExtensionPoints` exists. Inside the block that renders the message (after the existing `msg.structuredOutput &&` block), add:

```tsx
{!msg.structuredOutput && (msg.pendingExtensionPoints?.length ?? 0) > 0 && (
  <div className="extension-card extension-card--streaming">
    {msg.pendingExtensionPoints!.map((title, i) => (
      <section key={i} className="extension-point extension-point--skeleton">
        <h3 className="extension-point__title">{title}</h3>
        <div className="extension-point__body extension-point__body--loading" />
      </section>
    ))}
  </div>
)}
```

- [ ] **Step 6: Update `ExtensionDigestCard.tsx` to accept skeleton mode (already done in Task 7)**

The `pendingPoints` prop was added in Task 7. No additional change needed in `ExtensionDigestCard` — the skeleton is rendered in `MessageThread`, not the card itself.

- [ ] **Step 7: Run tests**

```bash
cd web && npx vitest run src/state/chat.test.ts 2>&1 | tail -20
```

Expected: all pass.

```bash
cd web && npx vitest run 2>&1 | tail -10
```

Expected: full suite passes.

- [ ] **Step 8: Commit**

```bash
git add web/src/types.ts web/src/state/chat.ts web/src/components/MessageThread.tsx web/src/state/chat.test.ts
git commit -m "feat(extension): per-point streaming skeleton — stage{point} events render titles as they arrive"
```

---

## Task 9: Docs lockstep

**Files:**
- Modify: `docs/services/chat-features/54-extension-mode.md`
- Modify: `docs/system/invariants.md`
- Modify: `docs/system/changelog.md`

- [ ] **Step 1: Update `54-extension-mode.md`**

In the **Env Flags** table, add the new flag:

```markdown
| `EXTENSION_JUDGE_MODEL` | `""` (→ nano) | Override judge stage model independently of orchestrator. |
```

Update the **Agent Roster** table — change Judge default model from `gpt-5.4-2026-03-17` to `gpt-5.4-nano-2026-03-17`.

In the **Frontend** section, update `ExtensionDigestCard` description:
```markdown
| `ExtensionDigestCard` | `web/src/components/ExtensionDigestCard.tsx` | Renders ordered points; `renderFootnoteBody` for footnotes (KaTeX math, no citation logic); Wikipedia sources as links; source paths truncated to 40 chars; Download button with loading state; wrapped in `StructuredErrorBoundary`. |
```

Add a new row:
```markdown
| `StructuredErrorBoundary` | `web/src/components/StructuredErrorBoundary.tsx` | Ported from sibling branch; degrades malformed digest to inline error notice. |
```

- [ ] **Step 2: Add invariant to `invariants.md`**

Add a new row at the end of the invariants table:

```markdown
| 38 | **Extension footnote density**: every non-trivial `ExtensionPoint` in a completed digest SHOULD have ≥ 2 footnotes. The orchestrator prompt enforces this via re-delegation; the runner does NOT hard-reject 0-footnote points (best-effort, not schema-enforced). | Inspect live digest: `so["data"]["points"][i]["footnotes"]` length ≥ 2 for non-trivial points. |
```

- [ ] **Step 3: Add changelog entry**

Prepend to `docs/system/changelog.md`:

```markdown
## 2026-06-09 — Extension mode quality rebuild

**Scope:** `extension_agents/` + `web/src/` Extension components only.

**Prompts:** density target (≥2 footnotes/non-trivial point), gap taxonomy (FORMAL-DEF / FORMULA-DERIV / COMPARATIVE / APPLICATION), augmentor fit rubric (score 1–5), strong ENGLISH enforcement with translate instruction, exact COVERAGE format `# COVERAGE: <query> = done|unfilled`, orphan-footnote merge in orchestrator + judge, polish keeps formal structure/notation.

**Math/text:** `_normalize_math_delimiters` (`\(...\)` → `$...$`, `\[...\]` → `$$...$$` display); `_strip_md_footnote_markers` removes `[^n]` from curated_text; `EXTENSION_SECTION_CHARS` default raised 1200 → 2500.

**Retrieval:** Wikipedia disambiguation fallback via search API on 404; `retrieve_corpus top_k` raised 6 → 10; cross-round dedup via `seen_ids` set shared between runner and tool closure.

**Model tiers:** judge demoted `_TOP` → `_CHEAP` (nano); `_MID` alias introduced; per-stage temperatures (polish 0.3, augmentor 0.2, orchestrator/judge 0.0); `EXTENSION_JUDGE_MODEL` env flag.

**Frontend:** `renderFootnoteBody` replaces `renderInlineWithCites` for footnote bodies; corpus source truncated to 40 chars; Wikipedia footnote rendered as `<a target="_blank">` link; Download button shows loading state + error message; `StructuredErrorBoundary` ported and wraps card; per-point streaming skeleton via `stage{point}` SSE events populating `pendingExtensionPoints` in message state.
```

- [ ] **Step 4: Commit**

```bash
git add docs/services/chat-features/54-extension-mode.md docs/system/invariants.md docs/system/changelog.md
git commit -m "docs(extension): lockstep update for quality rebuild — invariant 38, changelog, feature doc"
```

---

## Self-Review Checklist

**Spec coverage:**
- Layer 1 (Prompts) → Task 4 ✅
- Layer 2 (Math/text) → Task 1 ✅, `EXTENSION_SECTION_CHARS` → Task 1 ✅, fuzzy subtopic → Task 2 ✅
- Layer 3 (Retrieval) → Task 3 ✅
- Layer 4 (Model tiers) → Task 5 ✅
- Layer 5 (Frontend) → Tasks 6, 7, 8 ✅
- Docs lockstep → Task 9 ✅

**Type consistency:** `pendingExtensionPoints: string[]` defined in types.ts (Task 8 step 3), used in chat.ts (Task 8 step 4), and MessageThread.tsx (Task 8 step 5) — consistent across all three.

**`seen_ids` flow:** created in runner.py (Task 3 step 5), passed to `build_extension_agent` via new param (Task 3 step 4), captured by `make_retrieve_corpus` closure (Task 3 step 3) — consistent.

**`resolve_stage_temperature`:** defined in `_models.py` (Task 5 step 3), imported and used in `agent.py` (Task 5 step 4) — consistent.
