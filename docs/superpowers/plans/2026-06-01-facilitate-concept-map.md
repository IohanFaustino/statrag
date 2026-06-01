# Facilitate Concept-Map Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-architect `facilitate` into a concept-map-first, two-pass pipeline that teaches by clarifying (short paragraphs + bullets, top key points), flags referenced concepts/step-bearing formulas as clickable anchors backed by adaptive same-author-first sub-retrieval, and shows each anchor's explanation in a modal (footnote on export).

**Architecture:** New `agents/facilitate.py` runs: parse+resolve → ordered-fetch → per section [concept-map → adaptive sub-retrieval for referenced concepts → simplify+key-points teach → verify] → `FacilitateDigest`. `resume` keeps the existing `run_chapter`. A new `fetch_concept_support` retrieval helper implements the same-author→prior-section→other-author escalation. An offline LLM-judge eval harness picks the winning prompts before they ship.

**Tech Stack:** Python 3.12 (FastAPI, pydantic v2, openai async, qdrant-client), pytest; TypeScript + React + Vite, vitest, KaTeX.

**Spec:** `docs/superpowers/specs/2026-06-01-facilitate-concept-map-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/services/chat/schemas/output.py` | `ConceptProvenance`, `ConceptAnchor`, `FacilitateBlock`, `FacilitateDigest` | Modify |
| `src/services/chat/schemas/__init__.py` | re-export | Modify |
| `src/services/chat/retrieval.py` | `fetch_concept_support` adaptive helper | Modify |
| `src/services/chat/prompts/chapter.py` | 4 `FACILITATE_*` prompts | Modify |
| `src/services/chat/agents/facilitate.py` | concept-map / explain / teach / verify / `run_facilitate` | Create |
| `src/services/chat/router.py` | route `facilitate`→`run_facilitate` | Modify |
| `src/services/chat/eval/facilitate_eval.py` | offline LLM-judge variant harness | Create |
| `src/services/chat/tests/test_facilitate.py` | agent + retrieval tests | Create |
| `web/src/types.ts` | concept/facilitate types + SSE variant | Modify |
| `web/src/components/FacilitateDigestCard.tsx` | render key points + body + anchors | Create |
| `web/src/components/ConceptModal.tsx` | anchor modal (explanation + provenance + KaTeX) | Create |
| `web/src/components/MessageThread.tsx` | render FacilitateDigest + own anchor-click state | Modify |
| `web/src/styles/chapter.css` | `.concept-anchor*`, `.concept-modal*` rules | Modify |
| `web/src/lib/exportMarkdown.ts` | concept anchors → footnotes | Modify |
| `web/src/data/chapterPipeline.ts` | facilitate variant nodes (map/retrieve/teach/verify) | Modify |
| `web/src/data/chapterMode.ts` | facilitate copy | Modify |
| docs | feature 53, chat.md, invariants, changelog, Elements/chat.html, CLAUDE.md index | Modify/Create |

---

## Task 1: Concept + facilitate schemas

**Files:**
- Modify: `src/services/chat/schemas/output.py`, `src/services/chat/schemas/__init__.py`
- Test: `src/services/chat/tests/test_facilitate.py` (create)

- [ ] **Step 1: Failing test** — create `src/services/chat/tests/test_facilitate.py`:
```python
from src.services.chat.schemas import (
    ConceptAnchor, ConceptProvenance, FacilitateBlock, FacilitateDigest,
)


def test_facilitate_schemas_construct():
    prov = ConceptProvenance(book_slug="hansen", authors_short="Hansen",
                             section="7.1 INTRODUCTION", page_from=176, page_to=176,
                             chunk_id="x", same_author=True, fallback=False)
    c = ConceptAnchor(id="c1", term="strong assumption of normality",
                      kind="concept", explanation="Assumes the data are normal.",
                      provenance=prov)
    blk = FacilitateBlock(h2_path="7.1 INTRODUCTION", section_id="x",
                          key_points=["a", "b"], body="text [[c1]]", concepts=[c],
                          page_from=176, page_to=176)
    dig = FacilitateDigest(mode="facilitate", scope=None, blocks=[blk])  # type: ignore[arg-type]
    assert dig.blocks[0].concepts[0].kind == "concept"
    assert dig.blocks[0].key_points == ["a", "b"]
```
> `scope=None` will fail validation (ChapterScope required) — fix the test to import `ChapterScope` and pass `ChapterScope(book_slug="hansen", chapter_id="ch07", requested_subtopics=[])`. Use that real value.

- [ ] **Step 2: Run, confirm FAIL** — `.venv/bin/python -m pytest src/services/chat/tests/test_facilitate.py::test_facilitate_schemas_construct -v` → ImportError.

- [ ] **Step 3: Add models** to `src/services/chat/schemas/output.py` (after the chapter schemas; `Literal`, `BaseModel`, `Field` already imported):
```python
class ConceptProvenance(BaseModel):
    book_slug: str = ""
    book_name: str = ""
    authors_short: str = ""
    section: str = ""
    page_from: int = -1
    page_to: int = -1
    chunk_id: str = ""
    same_author: bool = True
    fallback: bool = False


class ConceptAnchor(BaseModel):
    id: str
    term: str
    kind: Literal["concept", "theorem", "formula"] = "concept"
    explanation: str = ""
    provenance: ConceptProvenance = Field(default_factory=ConceptProvenance)


class FacilitateBlock(BaseModel):
    h2_path: str
    section_id: str
    key_points: list[str] = Field(default_factory=list)
    body: str = ""
    concepts: list[ConceptAnchor] = Field(default_factory=list)
    page_from: int = -1
    page_to: int = -1


class FacilitateDigest(BaseModel):
    mode: Literal["facilitate"]
    scope: ChapterScope
    intro: str = ""
    blocks: list[FacilitateBlock] = Field(default_factory=list)
    outro: str = ""
    math_blocks: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict)
```
Re-export all four from `schemas/__init__.py` (`.output` import line + `__all__`).

- [ ] **Step 4: Run, confirm PASS.** Then full suite `.venv/bin/python -m pytest src/services/chat/tests/ -q` (no regressions).

- [ ] **Step 5: Commit**
```bash
git add src/services/chat/schemas/output.py src/services/chat/schemas/__init__.py src/services/chat/tests/test_facilitate.py
git commit -m "feat(chat): concept-anchor + facilitate digest schemas"
```

---

## Task 2: `fetch_concept_support` adaptive retrieval

**Files:**
- Modify: `src/services/chat/retrieval.py`
- Test: `src/services/chat/tests/test_facilitate.py`

Behaviour: given a `term`, a `book_slug`, and the current `section_id`, run a hybrid query (rerank on) and pick the best supporting chunk under an escalation policy: (1) same book, sections ordered before current, prefer formal-statement chunks; (2) same book anywhere; (3) other books. Return a small dataclass or None.

- [ ] **Step 1: Failing test** (append):
```python
import src.services.chat.retrieval as retrieval
from src.services.chat.schemas import Source


def _src(section, chunkId, text, book="hansen", score=0.5):
    return Source(rank=1, book=book, chapter="ch07", section=section, title=section,
                  excerpt=text[:120], score=score, chunkId=chunkId, chunk=text,
                  book_name="Probability and Statistics for Economists",
                  authors_short="Hansen", page_from=170, page_to=171)


def test_fetch_concept_support_prefers_same_author_prior(monkeypatch):
    # current section id "s5"; a prior formal-statement chunk "s2" should win
    pool = [
        _src("7.5 LATER", "s9", "uses normality again", score=0.9),
        _src("7.2 ASSUMPTIONS", "s2", "Definition: a strong assumption of normality means ...", score=0.6),
    ]
    monkeypatch.setattr(retrieval, "hybrid_search", lambda q, **k: (pool, None))
    # section ordering: provide an index mapping id->order so "before" is computable
    monkeypatch.setattr(retrieval, "_section_order_in_book",
                        lambda slug: {"s2": 2, "s5": 5, "s9": 9})
    sup = retrieval.fetch_concept_support("strong assumption of normality",
                                          book_slug="hansen", before_section_id="s5",
                                          min_score=0.3)
    assert sup is not None
    assert sup.chunk_id == "s2"          # prior + formal beats later
    assert sup.same_author is True
    assert sup.fallback is False


def test_fetch_concept_support_none_when_all_below_min(monkeypatch):
    monkeypatch.setattr(retrieval, "hybrid_search", lambda q, **k: ([], None))
    monkeypatch.setattr(retrieval, "_section_order_in_book", lambda slug: {})
    sup = retrieval.fetch_concept_support("x", book_slug="hansen",
                                          before_section_id="s5", min_score=0.3)
    assert sup is None
```

- [ ] **Step 2: Run, confirm FAIL** — `fetch_concept_support` undefined.

- [ ] **Step 3: Implement** in `retrieval.py`:
```python
from dataclasses import dataclass

_FORMAL_CUES = ("definition", "theorem", "assumption", "lemma", "proposition", "corollary")


@dataclass
class ConceptSupport:
    chunk_id: str
    section: str
    book_slug: str
    book_name: str
    authors_short: str
    page_from: int
    page_to: int
    text: str
    same_author: bool
    fallback: bool


def _section_order_in_book(book_slug: str) -> dict[str, int]:
    """Map section_id -> ordinal position within a book (by page_from then id).

    Uses a chapter-agnostic scroll of the book's chunks. Cheap metadata read.
    """
    order: dict[str, int] = {}
    try:
        for collection in collections_for_books([book_slug]):
            pts, _ = client().scroll(
                collection_name=collection,
                scroll_filter=Filter(must=[FieldCondition(key="book_slug", match=MatchAny(any=[book_slug]))]),
                limit=2000, with_payload=True,
            )
            ranked = sorted(
                pts, key=lambda p: (_safe_int((p.payload or {}).get("page_from")) or 10**9, str(p.id)))
            for i, p in enumerate(ranked):
                order[str(p.id)] = i
    except Exception:  # noqa: BLE001
        logger.exception("_section_order_in_book failed for %r", book_slug)
    return order


def _formal_boost(text: str) -> float:
    low = (text or "").lower()
    return 0.15 if any(cue in low for cue in _FORMAL_CUES) else 0.0


def _best_support(term, candidates, *, order, before_section_id, min_score, formal_pref):
    cur = order.get(before_section_id, 10**9)
    scored = []
    for s in candidates:
        sc = float(s.score or 0.0)
        if formal_pref:
            sc += _formal_boost(s.chunk or s.excerpt or "")
        prior = order.get(s.chunkId, 10**9) < cur
        scored.append((prior, sc, s))
    # prior-section candidates first (True sorts after False, so negate), then score
    scored.sort(key=lambda t: (not t[0], -t[1]))
    for prior, sc, s in scored:
        if sc >= min_score:
            return s
    return None


def fetch_concept_support(
    term: str,
    *,
    book_slug: str,
    before_section_id: str,
    min_score: float = 0.30,
    formal_pref: bool = True,
) -> ConceptSupport | None:
    """Adaptive same-author→prior-section→other-author support for one concept."""
    order = _section_order_in_book(book_slug)
    # (1) same book
    same, _ = hybrid_search(term, book_slugs=[book_slug], rerank=True, rerank_top_n=8)
    hit = _best_support(term, same, order=order, before_section_id=before_section_id,
                        min_score=min_score, formal_pref=formal_pref)
    same_author = True
    if hit is None:
        # (3) other authors (cross-book)
        other, _ = hybrid_search(term, book_slugs=None, rerank=True, rerank_top_n=8)
        other = [s for s in other if s.book != book_slug]
        hit = _best_support(term, other, order={}, before_section_id=before_section_id,
                            min_score=min_score, formal_pref=formal_pref)
        same_author = False
    if hit is None:
        return None
    return ConceptSupport(
        chunk_id=hit.chunkId, section=hit.section or hit.title, book_slug=hit.book,
        book_name=hit.book_name or hit.book, authors_short=hit.authors_short or "",
        page_from=hit.page_from if hit.page_from is not None else -1,
        page_to=hit.page_to if hit.page_to is not None else -1,
        text=(hit.chunk or hit.excerpt or ""), same_author=same_author, fallback=False)
```
> The two-tier (same-book then other-books) covers policy steps 1–3: step 1 (prior-section) and step 2 (anywhere-in-book) are both inside the same-book candidate set, ordered by the `prior` flag in `_best_support`. Confirm `collections_for_books`, `client`, `Filter`, `FieldCondition`, `MatchAny`, `_safe_int` are already imported at top of `retrieval.py` (they are used by `fetch_chapter_sections`).

- [ ] **Step 4: Run, confirm PASS** — `.venv/bin/python -m pytest src/services/chat/tests/test_facilitate.py -k concept_support -v`.

- [ ] **Step 5: Commit**
```bash
git add src/services/chat/retrieval.py src/services/chat/tests/test_facilitate.py
git commit -m "feat(chat): fetch_concept_support adaptive same-author-first retrieval"
```

---

## Task 3: Facilitate prompts (v1 — refined by eval in Task 9)

**Files:** Modify `src/services/chat/prompts/chapter.py`

- [ ] **Step 1: Add four constants** (keep `CHAPTER_MAP_RESUME_PROMPT`; the facilitate path stops using `CHAPTER_MAP_FACILITATE_PROMPT`):
```python
FACILITATE_MAP_PROMPT = """You analyse ONE textbook section for a learner.
Return ONLY JSON:
  "key_points": array of 3-6 short strings — the section's most important points.
  "concepts": array of {"term","kind","status"} where kind is one of
      "concept"|"theorem"|"formula" and status is "explained" (defined in THIS
      section) or "referenced" (named but assumed/not defined here). Mark a
      formula as a concept ONLY if it has derivation steps behind it.
Pick at most 5 concepts, the ones most useful to understand. Do not invent terms.
"""

FACILITATE_EXPLAIN_PROMPT = """Explain the term in 1-3 plain sentences using ONLY
the provided passage. No padding, no restating the question. If the term is a
formula with steps, give the short derivation. Return ONLY the explanation text.
"""

FACILITATE_TEACH_PROMPT = """Rewrite this section for a learner.
Rules:
- SHORT, direct paragraphs (<=2-3 sentences). Prefer a bullet list of the key points.
- Simpler language. Keep ONLY the key points. Do NOT lengthen or add background.
- Any extra/explanatory detail belongs in a concept anchor, NOT the body.
- Insert [[cN]] right after the term where each listed concept first appears
  (use the ids given). Step-bearing formulas also get their [[cN]].
Return ONLY markdown for the body.
"""

FACILITATE_VERIFY_PROMPT = """Check the rewritten body against the section text.
Return ONLY JSON {"ok": bool, "unsupported": [string], "confidence": 0..1}.
ok=false if the body states something the section does not support.
"""
```

- [ ] **Step 2: Commit**
```bash
git add src/services/chat/prompts/chapter.py
git commit -m "feat(chat): facilitate concept-map prompts (v1, tuned by eval)"
```

---

## Task 4: `agents/facilitate.py` + router dispatch

**Files:**
- Create: `src/services/chat/agents/facilitate.py`
- Modify: `src/services/chat/router.py`
- Test: `src/services/chat/tests/test_facilitate.py`

The agent reuses the existing scope/fetch/clarify machinery from `chapter.py`
(import `resolve_book`, `parse_catalog`, `maybe_clarify` from `_scope`, and
`fetch_chapter_sections` from `retrieval`). It adds map/explain/teach/verify.

- [ ] **Step 1: Failing test** (append):
```python
import pytest
from src.services.chat.agents import facilitate as fac
from src.services.chat.schemas import BookResolution, CatalogBook, ChatRequest, Source

_CAT = [CatalogBook(slug="hansen", name="Probability and Statistics for Economists",
                    authors_short="Hansen", field="introduction", chapters=["ch07"])]


def _sec(title, cid, text):
    return Source(rank=1, book="hansen", chapter="ch07", section=title, title=title,
                  excerpt=text[:120], score=0.0, chunkId=cid, chunk=text,
                  book_name="Probability and Statistics for Economists",
                  authors_short="Hansen", page_from=176, page_to=176)


@pytest.mark.asyncio
async def test_run_facilitate_builds_digest_with_anchor(monkeypatch):
    monkeypatch.setattr(fac, "parse_catalog", lambda: _CAT)
    async def fake_resolve(*a, **k):
        return BookResolution(book_slug="hansen", book_confidence=1.0,
                              book_candidates=["hansen"], chapter_id="ch07",
                              requested_subtopics=[])
    monkeypatch.setattr(fac, "resolve_book", fake_resolve)
    monkeypatch.setattr(fac, "fetch_chapter_sections",
                        lambda b, c, **k: [_sec("7.1 INTRODUCTION", "s1",
                                                "Assumes a strong assumption of normality.")])
    # map -> one referenced concept; teach -> body with [[c1]]; verify -> ok
    async def fake_chat(messages, *, model, max_tokens, temperature=0.0):
        sysmsg = messages[0]["content"]
        if "analyse ONE textbook section" in sysmsg:
            return '{"key_points":["pt"],"concepts":[{"term":"strong assumption of normality","kind":"concept","status":"referenced"}]}'
        if "Explain the term" in sysmsg:
            return "It assumes the data are normally distributed."
        if "Rewrite this section" in sysmsg:
            return "- pt\n\nWe rely on the strong assumption of normality [[c1]]."
        if "Check the rewritten body" in sysmsg:
            return '{"ok":true,"unsupported":[],"confidence":0.9}'
        return "{}"
    monkeypatch.setattr(fac, "_chat", fake_chat)
    # referenced concept triggers sub-retrieval
    from src.services.chat import retrieval as r
    monkeypatch.setattr(fac, "fetch_concept_support",
                        lambda term, **k: r.ConceptSupport(
                            chunk_id="s0", section="7.0", book_slug="hansen",
                            book_name="P&S", authors_short="Hansen", page_from=170,
                            page_to=170, text="def", same_author=True, fallback=False))
    req = ChatRequest(message="facilitate ch07 of hansen", mode="facilitate", bookFilter=["hansen"])
    evs = [e async for e in fac.run_facilitate(req)]
    so = next(e for e in evs if e["type"] == "structured_output")
    assert so["schema"] == "FacilitateDigest"
    blk = so["data"]["blocks"][0]
    assert blk["key_points"] == ["pt"]
    assert blk["concepts"][0]["id"] == "c1"
    assert "[[c1]]" in blk["body"]
    assert evs[-1]["type"] == "done"
```

- [ ] **Step 2: Run, confirm FAIL** — module `facilitate` missing.

- [ ] **Step 3: Implement `src/services/chat/agents/facilitate.py`:**
```python
"""Facilitate mode: concept-map-first teaching pipeline.

Per section, in order: build a concept map (key points + concepts), sub-retrieve
explanations for referenced concepts (same-author-first), rewrite the section as
short/clear key points with [[cN]] anchors, then verify grounding. Emits the v1
SSE schema with structured_output schema "FacilitateDigest".

Chinese-wall: imports only src.core.* and sibling src.services.chat.*.
"""
from __future__ import annotations

import json, logging, os, time
from typing import AsyncIterator

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.agents._scope import maybe_clarify, resolve_book
from src.services.chat.books import parse_catalog
from src.services.chat.llm.router import aclient_for
from src.services.chat.prompts.chapter import (
    FACILITATE_EXPLAIN_PROMPT, FACILITATE_MAP_PROMPT,
    FACILITATE_TEACH_PROMPT, FACILITATE_VERIFY_PROMPT,
)
from src.services.chat.retrieval import fetch_chapter_sections, fetch_concept_support
from src.services.chat.schemas import (
    ChapterScope, ConceptAnchor, ConceptProvenance, FacilitateBlock,
    FacilitateDigest, Source,
)

logger = logging.getLogger(__name__)

_MAX_SECTIONS = int(os.environ.get("CHAPTER_MAX_SECTIONS", "30"))
_MAX_CONCEPTS = int(os.environ.get("FACILITATE_MAX_CONCEPTS", "5"))
_MAX_KEYPOINTS = int(os.environ.get("FACILITATE_MAX_KEYPOINTS", "6"))
_MIN_SCORE = float(os.environ.get("CONCEPT_MIN_SCORE", "0.30"))
_SUBRETRIEVAL = os.environ.get("FACILITATE_SUBRETRIEVAL", "1") == "1"
_CLARIFY = os.environ.get("CHAPTER_CLARIFY", "1") == "1"
_GROUND = os.environ.get("CHAPTER_GROUND", "1") == "1"
_PREVIEW = 1500


def _model_for(stage: str, req) -> str:
    sm = req.stageModels if req else None
    if sm and isinstance(sm.get(stage), str) and sm[stage].strip():
        return sm[stage].strip()
    env = os.environ.get(f"FACILITATE_{stage.upper()}_MODEL", "").strip()
    if env:
        return env
    return settings.openai_model_nano


async def _chat(messages, *, model, max_tokens, temperature=0.0) -> str:
    oa = aclient_for(model)
    resp = await oa.chat.completions.create(
        model=model, messages=messages, temperature=temperature,
        max_completion_tokens=max_tokens)
    return resp.choices[0].message.content or ""


async def _map_section(s: Source, *, model: str) -> tuple[list[str], list[dict]]:
    user = f"heading: {s.title}\n\nsection text:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}"
    try:
        raw = await _chat([{"role": "system", "content": FACILITATE_MAP_PROMPT},
                           {"role": "user", "content": user}], model=model, max_tokens=500)
        data = json.loads(strip_fences(raw))
        kps = [str(x).strip() for x in (data.get("key_points") or []) if str(x).strip()][:_MAX_KEYPOINTS]
        concepts = []
        for c in (data.get("concepts") or [])[:_MAX_CONCEPTS]:
            term = str(c.get("term", "")).strip()
            if not term:
                continue
            concepts.append({"term": term,
                             "kind": c.get("kind", "concept") if c.get("kind") in ("concept", "theorem", "formula") else "concept",
                             "status": "referenced" if c.get("status") == "referenced" else "explained"})
        return kps, concepts
    except Exception:  # noqa: BLE001
        logger.exception("facilitate._map_section failed at %s", s.chunkId)
        excerpt = (s.excerpt or "")[:200]
        return ([excerpt] if excerpt else []), []


async def _explain(term: str, passage: str, *, model: str) -> str:
    try:
        return (await _chat([{"role": "system", "content": FACILITATE_EXPLAIN_PROMPT},
                             {"role": "user", "content": f"term: {term}\n\npassage:\n{passage[:_PREVIEW]}"}],
                            model=model, max_tokens=200)).strip()
    except Exception:  # noqa: BLE001
        logger.exception("facilitate._explain failed for %s", term)
        return passage[:200]


async def _build_concepts(s: Source, concept_dicts: list[dict], *, explain_model: str) -> list[ConceptAnchor]:
    anchors: list[ConceptAnchor] = []
    for i, c in enumerate(concept_dicts, 1):
        cid = f"c{i}"
        term, kind, status = c["term"], c["kind"], c["status"]
        if status == "referenced" and _SUBRETRIEVAL:
            sup = fetch_concept_support(term, book_slug=s.book, before_section_id=s.chunkId, min_score=_MIN_SCORE)
            if sup is not None:
                expl = await _explain(term, sup.text, model=explain_model)
                anchors.append(ConceptAnchor(id=cid, term=term, kind=kind, explanation=expl,
                    provenance=ConceptProvenance(book_slug=sup.book_slug, book_name=sup.book_name,
                        authors_short=sup.authors_short, section=sup.section, page_from=sup.page_from,
                        page_to=sup.page_to, chunk_id=sup.chunk_id, same_author=sup.same_author, fallback=False)))
                continue
        # explained-in-section OR no acceptable retrieval → in-section gloss
        expl = await _explain(term, (s.chunk or s.excerpt or ""), model=explain_model)
        anchors.append(ConceptAnchor(id=cid, term=term, kind=kind, explanation=expl,
            provenance=ConceptProvenance(book_slug=s.book, book_name=s.book_name or s.book,
                authors_short=s.authors_short or "", section=s.title,
                page_from=s.page_from if s.page_from is not None else -1,
                page_to=s.page_to if s.page_to is not None else -1, chunk_id=s.chunkId,
                same_author=True, fallback=(status == "referenced"))))
    return anchors


async def _teach(s: Source, key_points: list[str], anchors: list[ConceptAnchor], *, model: str) -> str:
    ids = "; ".join(f"{a.id}={a.term}" for a in anchors)
    user = (f"heading: {s.title}\nconcept ids: {ids}\nkey points: {key_points}\n\n"
            f"section text:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}")
    try:
        body = await _chat([{"role": "system", "content": FACILITATE_TEACH_PROMPT},
                            {"role": "user", "content": user}], model=model, max_tokens=700)
        return body.strip() or "\n".join(f"- {k}" for k in key_points)
    except Exception:  # noqa: BLE001
        logger.exception("facilitate._teach failed at %s", s.chunkId)
        return "\n".join(f"- {k}" for k in key_points)


async def _verify(body: str, s: Source, *, model: str) -> dict:
    if not _GROUND:
        return {"ok": True, "unsupported": [], "confidence": 1.0}
    try:
        raw = await _chat([{"role": "system", "content": FACILITATE_VERIFY_PROMPT},
                           {"role": "user", "content": f"section:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}\n\nbody:\n{body}"}],
                          model=model, max_tokens=200)
        d = json.loads(strip_fences(raw))
        return {"ok": bool(d.get("ok", False)),
                "unsupported": [str(x) for x in (d.get("unsupported") or [])],
                "confidence": float(d.get("confidence", 0.5))}
    except Exception:  # noqa: BLE001
        return {"ok": False, "unsupported": [], "confidence": 0.5}


async def run_facilitate(req) -> AsyncIterator[dict]:
    t0 = time.time()
    message = req.message or ""
    bf = req.bookFilter
    book_slugs = list(bf) if isinstance(bf, list) and bf else None

    yield {"type": "meta", "mode": "facilitate", "books": book_slugs or [],
           "sourceCount": 0, "latencyMs": 0, "model": req.model}

    yield {"type": "stage", "stage": "parse", "label": "Parse + resolve scope"}
    catalog = parse_catalog()
    res = await resolve_book(message, selected_slugs=book_slugs, catalog=catalog, model=_model_for("map", req))
    scope = ChapterScope(book_slug=res.book_slug, chapter_id=res.chapter_id, requested_subtopics=res.requested_subtopics)
    if _CLARIFY:
        clar = maybe_clarify(res, catalog)
        if clar is not None:
            yield clar
            yield {"type": "done"}
            return

    yield {"type": "stage", "stage": "fetch", "label": "Fetch chapter"}
    try:
        sections = fetch_chapter_sections(scope.book_slug, scope.chapter_id, max_sections=_MAX_SECTIONS) \
            if scope.book_slug and scope.chapter_id else []
    except Exception:  # noqa: BLE001
        sections = []
    # subtopic filter (reuse resume's resolver semantics: numeric/title match)
    if scope.requested_subtopics:
        wanted = [t.lower() for t in scope.requested_subtopics]
        filt = [s for s in sections if any(w in s.title.lower() for w in wanted)]
        sections = filt or sections

    if not sections:
        dig = FacilitateDigest(mode="facilitate", scope=scope, blocks=[],
            intro="Chapter not found in the selected books. Pick a book and name a chapter (e.g. 'ch02').",
            grounding={"ok": True, "unsupported": [], "confidence": 1.0})
        yield {"type": "structured_output", "schema": "FacilitateDigest", "data": dig.model_dump()}
        yield {"type": "sources_full", "sources": []}
        yield {"type": "usage", "durationMs": int((time.time()-t0)*1000), "promptChars": len(message),
               "completionChars": len(dig.intro), "estTokens": 0}
        yield {"type": "done"}
        return

    blocks: list[FacilitateBlock] = []
    for s in sections:
        yield {"type": "stage", "stage": "map", "label": f"Map · {s.title}"}
        key_points, concept_dicts = await _map_section(s, model=_model_for("map", req))
        for c in concept_dicts:
            if c["status"] == "referenced":
                yield {"type": "stage", "stage": "retrieve", "label": f"Retrieve · {c['term']}"}
        anchors = await _build_concepts(s, concept_dicts, explain_model=_model_for("explain", req))
        yield {"type": "stage", "stage": "teach", "label": f"Teach · {s.title}"}
        body = await _teach(s, key_points, anchors, model=_model_for("teach", req))
        blocks.append(FacilitateBlock(
            h2_path=s.title, section_id=s.chunkId, key_points=key_points, body=body,
            concepts=anchors, page_from=s.page_from if s.page_from is not None else -1,
            page_to=s.page_to if s.page_to is not None else -1))

    yield {"type": "stage", "stage": "verify", "label": "Verify"}
    joined = "\n".join(b.body for b in blocks)
    grounding = await _verify(joined, sections[0], model=_model_for("verify", req))

    dig = FacilitateDigest(mode="facilitate", scope=scope, blocks=blocks, grounding=grounding)
    yield {"type": "structured_output", "schema": "FacilitateDigest", "data": dig.model_dump()}
    yield {"type": "sources_full", "sources": [s.model_dump() for s in sections]}
    yield {"type": "usage", "durationMs": int((time.time()-t0)*1000), "promptChars": len(message),
           "completionChars": len(joined), "estTokens": (len(message)+len(joined))//4}
    yield {"type": "done"}
```

- [ ] **Step 4: Router dispatch** — in `src/services/chat/router.py` replace the `("facilitate","resume")` block:
```python
    if req.mode == "facilitate":
        from src.services.chat.agents.facilitate import run_facilitate  # noqa: PLC0415
        async for event in run_facilitate(req):
            yield event
        return
    if req.mode == "resume":
        from src.services.chat.agents.chapter import run_chapter  # noqa: PLC0415
        async for event in run_chapter(req):
            yield event
        return
```

- [ ] **Step 5: Run, confirm PASS** — `.venv/bin/python -m pytest src/services/chat/tests/test_facilitate.py -v`, then full suite `.venv/bin/python -m pytest src/services/chat/tests/ -q` (fix any resume test that assumed facilitate routed to run_chapter — resume still does; facilitate tests are new).

- [ ] **Step 6: Commit**
```bash
git add src/services/chat/agents/facilitate.py src/services/chat/router.py src/services/chat/tests/test_facilitate.py
git commit -m "feat(chat): facilitate concept-map agent + router dispatch"
```

---

## Task 5: Live smoke on hansen ch07 (manual gate before frontend)

**Files:** none (verification)

- [ ] **Step 1:** ensure dev backend running (`./scripts/dev.sh`), then:
```bash
curl -sN -X POST http://localhost:8766/api/chat -H "Content-Type: application/json" \
  -d '{"message":"facilitate chapter 7 sections 7.1 to 7.4 of hansen probability","mode":"facilitate","bookFilter":"ALL"}' \
  --max-time 180 | grep -E "schema|key_points|concepts|\[\[c" | head
```
Expected: `structured_output.schema == "FacilitateDigest"`, blocks with `key_points`, `concepts` anchors, `[[cN]]` markers in bodies. If a body is a long essay or has no anchors, note it — Task 9 (eval) tunes the prompts.

---

## Task 6: Frontend types + SSE variant

**Files:** Modify `web/src/types.ts`; Test `web/src/state/chat.test.ts`

- [ ] **Step 1: Add types** to `web/src/types.ts`:
```ts
export interface ConceptProvenance {
  book_slug: string; book_name: string; authors_short: string; section: string;
  page_from: number; page_to: number; chunk_id: string;
  same_author: boolean; fallback: boolean;
}
export interface ConceptAnchor {
  id: string; term: string; kind: "concept" | "theorem" | "formula";
  explanation: string; provenance: ConceptProvenance;
}
export interface FacilitateBlock {
  h2_path: string; section_id: string; key_points: string[]; body: string;
  concepts: ConceptAnchor[]; page_from: number; page_to: number;
}
export interface FacilitateDigest {
  mode: "facilitate"; scope: ChapterScope; intro: string;
  blocks: FacilitateBlock[]; outro: string; math_blocks: string[];
  grounding: { ok?: boolean; unsupported?: string[]; confidence?: number };
}
```
Add to `StructuredOutputEvent` (before the catch-all):
```ts
  | { type: "structured_output"; schema: "FacilitateDigest"; data: FacilitateDigest }
```

- [ ] **Step 2: Test** (append to `web/src/state/chat.test.ts`) asserting a `structured_output` with schema `"FacilitateDigest"` attaches to the last assistant message (mirror the existing ChapterDigest test). Run `cd web && npx vitest run src/state/chat.test.ts` (it already routes structured_output generically — this is a type-coverage test).

- [ ] **Step 3: Commit**
```bash
git add web/src/types.ts web/src/state/chat.test.ts
git commit -m "feat(web): FacilitateDigest types + SSE variant"
```

---

## Task 7: ConceptModal component

**Files:** Create `web/src/components/ConceptModal.tsx`, `web/src/components/ConceptModal.test.tsx`

- [ ] **Step 1: Failing test** (`// @vitest-environment jsdom` first line):
```tsx
// @vitest-environment jsdom
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ConceptModal from "./ConceptModal";
import type { ConceptAnchor } from "../types";

const anchor: ConceptAnchor = {
  id: "c1", term: "strong assumption of normality", kind: "concept",
  explanation: "Assumes the data are normally distributed.",
  provenance: { book_slug: "hansen", book_name: "P&S", authors_short: "Hansen",
    section: "7.2 ASSUMPTIONS", page_from: 172, page_to: 172, chunk_id: "x",
    same_author: true, fallback: false },
};

describe("ConceptModal", () => {
  it("shows term, explanation, provenance", () => {
    render(<ConceptModal anchor={anchor} onClose={() => {}} />);
    expect(screen.getByText(/strong assumption of normality/)).toBeInTheDocument();
    expect(screen.getByText(/normally distributed/)).toBeInTheDocument();
    expect(screen.getByText(/Hansen/)).toBeInTheDocument();
  });
  it("calls onClose on overlay click", () => {
    const onClose = vi.fn();
    render(<ConceptModal anchor={anchor} onClose={onClose} />);
    fireEvent.click(screen.getByTestId("concept-modal-overlay"));
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Implement** `web/src/components/ConceptModal.tsx`:
```tsx
import React, { useEffect } from "react";
import type { ConceptAnchor } from "../types";
import { MathBlock } from "./Math";

interface Props { anchor: ConceptAnchor; onClose: () => void; }

// formula explanations may contain LaTeX between $...$ or $$...$$; render the
// whole explanation via MathBlock when kind === "formula", else plain text.
export default function ConceptModal({ anchor, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const p = anchor.provenance;
  const prov = [p.authors_short, p.section, p.page_from > 0 ? `p. ${p.page_from}` : ""]
    .filter(Boolean).join(" · ");
  return (
    <div className="concept-modal__overlay" data-testid="concept-modal-overlay" onClick={onClose}>
      <div className="concept-modal" role="dialog" aria-label={anchor.term}
           onClick={(e) => e.stopPropagation()}>
        <div className="concept-modal__hd">
          <span className={`concept-modal__kind concept-modal__kind--${anchor.kind}`}>{anchor.kind}</span>
          <h3 className="concept-modal__term">{anchor.term}</h3>
          <button className="concept-modal__close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="concept-modal__body">
          {anchor.kind === "formula"
            ? <MathBlock tex={anchor.explanation} />
            : <p>{anchor.explanation}</p>}
        </div>
        {prov && (
          <p className="concept-modal__prov">
            {prov}
            {p.fallback && <span className="concept-modal__note"> · from this section</span>}
            {!p.same_author && <span className="concept-modal__note"> · other author</span>}
          </p>
        )}
      </div>
    </div>
  );
}
```
> If `MathBlock` throws on non-LaTeX text, wrap in try or render plain text when `anchor.explanation` has no `$`. Check the `Math` component's tolerance; if strict, only use MathBlock when explanation contains `$`.

- [ ] **Step 4: Run, confirm PASS** + `cd web && npx tsc --noEmit`.

- [ ] **Step 5: Commit**
```bash
git add web/src/components/ConceptModal.tsx web/src/components/ConceptModal.test.tsx
git commit -m "feat(web): ConceptModal (explanation + provenance + KaTeX)"
```

---

## Task 8: FacilitateDigestCard + anchor rendering + CSS

**Files:** Create `web/src/components/FacilitateDigestCard.tsx`, `.test.tsx`; Modify `web/src/styles/chapter.css`

- [ ] **Step 1: Failing test** (`// @vitest-environment jsdom`):
```tsx
// @vitest-environment jsdom
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import FacilitateDigestCard from "./FacilitateDigestCard";
import type { FacilitateDigest } from "../types";

const digest: FacilitateDigest = {
  mode: "facilitate",
  scope: { book_slug: "hansen", chapter_id: "ch07", requested_subtopics: [], resolution: [] } as any,
  intro: "", outro: "", math_blocks: [], grounding: { ok: true, confidence: 0.9 },
  blocks: [{
    h2_path: "7.1 INTRODUCTION", section_id: "s1", page_from: 176, page_to: 176,
    key_points: ["Sample means converge."],
    body: "We rely on the strong assumption of normality [[c1]].",
    concepts: [{ id: "c1", term: "strong assumption of normality", kind: "concept",
      explanation: "Assumes normal data.",
      provenance: { book_slug: "hansen", book_name: "P&S", authors_short: "Hansen",
        section: "7.2", page_from: 172, page_to: 172, chunk_id: "x",
        same_author: true, fallback: false } }],
  }],
};

describe("FacilitateDigestCard", () => {
  it("renders key points and a clickable concept anchor that opens a modal", () => {
    render(<FacilitateDigestCard digest={digest} />);
    expect(screen.getByText(/Sample means converge/)).toBeInTheDocument();
    const anchor = screen.getByRole("button", { name: /strong assumption of normality/ });
    fireEvent.click(anchor);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Assumes normal data/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Implement** `web/src/components/FacilitateDigestCard.tsx`. Render: header (reuse chapter-card header classes), per block: `h`/pages, a "Key points" bulleted list, then the body with `[[cN]]` replaced by clickable `<button class="concept-anchor concept-anchor--<kind>">term</button>`. Maintain `const [active, setActive] = useState<ConceptAnchor | null>(null)`; clicking sets it; render `<ConceptModal>` when set.
```tsx
import React, { useState } from "react";
import type { FacilitateDigest, ConceptAnchor, FacilitateBlock } from "../types";
import ConceptModal from "./ConceptModal";

const ANCHOR_RE = /\[\[(c\d+)\]\]/g;

function renderBody(block: FacilitateBlock, onPick: (a: ConceptAnchor) => void) {
  const byId = new Map(block.concepts.map((c) => [c.id, c]));
  const out: React.ReactNode[] = [];
  let last = 0, m: RegExpExecArray | null, k = 0;
  ANCHOR_RE.lastIndex = 0;
  while ((m = ANCHOR_RE.exec(block.body))) {
    if (m.index > last) out.push(block.body.slice(last, m.index));
    const c = byId.get(m[1]);
    if (c) out.push(
      <button key={`a${k++}`} type="button"
        className={`concept-anchor concept-anchor--${c.kind}`}
        onClick={() => onPick(c)}>{c.term}</button>);
    else out.push(m[0]);
    last = m.index + m[0].length;
  }
  if (last < block.body.length) out.push(block.body.slice(last));
  return out;
}

export default function FacilitateDigestCard({ digest }: { digest: FacilitateDigest }) {
  const [active, setActive] = useState<ConceptAnchor | null>(null);
  const conf = digest.grounding?.confidence ?? 0;
  const grounded = digest.grounding?.ok === true && conf >= 0.7;
  return (
    <div className="chapter-card chapter-card--facilitate">
      <div className="chapter-card__hd">
        <span className="chapter-card__mode">Facilitate</span>
        <span className="chapter-card__scope">{digest.scope.book_slug} · {digest.scope.chapter_id}</span>
        <span className={`chapter-card__badge ${grounded ? "is-ok" : "is-partial"}`}>
          {grounded ? "✓ grounded" : "⚠ partial"}</span>
      </div>
      {digest.intro && <p className="chapter-card__intro">{digest.intro}</p>}
      <div className="chapter-card__blocks">
        {digest.blocks.map((b, i) => (
          <section key={`${b.section_id}-${i}`} className="chapter-block">
            <h3 className="chapter-block__h">{b.h2_path}</h3>
            {b.page_from > 0 && <span className="chapter-block__pages">pp. {b.page_from}{b.page_to > b.page_from ? `–${b.page_to}` : ""}</span>}
            {b.key_points.length > 0 && (
              <ul className="facilitate-keypoints">
                {b.key_points.map((k, j) => <li key={j}>{k}</li>)}
              </ul>)}
            <div className="chapter-block__body">{renderBody(b, setActive)}</div>
          </section>
        ))}
      </div>
      {digest.outro && <p className="chapter-card__outro">{digest.outro}</p>}
      {active && <ConceptModal anchor={active} onClose={() => setActive(null)} />}
    </div>
  );
}
```

- [ ] **Step 4: CSS** — append to `web/src/styles/chapter.css`: `.facilitate-keypoints` (tight bulleted list), `.concept-anchor` (inline pill button, accent-tinted, underline-on-hover, kind variants `--concept`/`--theorem`/`--formula` using `--accent-primary`/`--accent-secondary`/`--accent-tertiary`), `.concept-modal__overlay` (fixed, centered, dim backdrop), `.concept-modal` (elevated surface, max-width 460px, `--shadow-elev`), `.concept-modal__hd/__term/__kind/__close/__body/__prov/__note`. Token-only; works light+dark; respect `prefers-reduced-motion`.

- [ ] **Step 5: Run, confirm PASS** + `cd web && npx tsc --noEmit && npx vitest run`.

- [ ] **Step 6: Commit**
```bash
git add web/src/components/FacilitateDigestCard.tsx web/src/components/FacilitateDigestCard.test.tsx web/src/styles/chapter.css
git commit -m "feat(web): FacilitateDigestCard with clickable concept anchors"
```

---

## Task 9: Wire into MessageThread + eval-tuned prompts

**Files:** Modify `web/src/components/MessageThread.tsx`; (eval) `src/services/chat/eval/facilitate_eval.py`

- [ ] **Step 1: Render branch** — in `MessageThread.tsx` add next to ChapterDigest:
```tsx
{msg.structuredOutput.schema === "FacilitateDigest" && (
  <FacilitateDigestCard data={msg.structuredOutput.data as FacilitateDigest} />
)}
```
> Match the prop name used by the card (the card above takes `digest`, not `data` — use `digest={...}`). Import `FacilitateDigestCard` and the `FacilitateDigest` type.

- [ ] **Step 2: Build eval harness** `src/services/chat/eval/facilitate_eval.py` — a pytest module marked `@pytest.mark.facilitate_eval` (register the marker in `pyproject`/`pytest.ini` if markers are strict). It: (a) fetches hansen ch07 §7.1–7.4 once via `fetch_chapter_sections`; (b) runs ≥2 prompt variants of the teach node (e.g. current vs a stricter "bullets-only, ≤120 words" variant) through `_teach`; (c) scores each output with an LLM-judge call (a local function calling `_chat` with a rubric returning JSON scores for clarity/faithfulness/keypoint_coverage/non_expansion/concept_id 1–5); (d) runs 3× per variant, averages, and writes a ranked table to `docs/superpowers/eval/2026-06-01-facilitate-variants.md`.

- [ ] **Step 3: Run the eval** (manual, needs live LLM):
```bash
.venv/bin/python -m pytest src/services/chat/eval/facilitate_eval.py -m facilitate_eval -s
```
Read the ranked table; set the **winning teach prompt wording** as `FACILITATE_TEACH_PROMPT` in `prompts/chapter.py` (and any other node whose variant won). Commit the table + the final prompts.

- [ ] **Step 4: Verify** `cd web && npx vitest run && npx tsc --noEmit`.

- [ ] **Step 5: Commit**
```bash
git add web/src/components/MessageThread.tsx src/services/chat/eval/facilitate_eval.py "docs/superpowers/eval/2026-06-01-facilitate-variants.md" src/services/chat/prompts/chapter.py
git commit -m "feat(chat): wire FacilitateDigestCard + eval-tuned facilitate prompts"
```

---

## Task 10: Markdown export footnotes

**Files:** Modify `web/src/lib/exportMarkdown.ts`; extend its test

- [ ] **Step 1: Failing test** — add a case to the export test: a message with a `FacilitateDigest` structuredOutput exports each block's body with `[[cN]]` replaced by `[^cN]`, and appends `[^cN]: <term> — <explanation> (<authors_short>, <section>, p.<page>)`.

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Implement** — in `exportMarkdown.ts`, when a message's `structuredOutput.schema === "FacilitateDigest"`, render: intro, then per block the heading, key points as `- ` bullets, the body with `[[cN]]`→`[^cN]`, and collect footnote definitions; append all footnote defs at the end.

- [ ] **Step 4: Run, confirm PASS** + `npx tsc --noEmit`.

- [ ] **Step 5: Commit**
```bash
git add web/src/lib/exportMarkdown.ts web/src/lib/exportMarkdown.test.ts
git commit -m "feat(web): markdown export — concept anchors as footnotes"
```

---

## Task 11: Pipeline diagram + mode copy

**Files:** Modify `web/src/data/chapterPipeline.ts`, `web/src/data/chapterMode.ts`, `web/src/data/chapterPipeline.test.ts`

- [ ] **Step 1: Failing test** (append) — facilitate diagram must include `map`, `retrieve`, `teach`, `verify` nodes:
```ts
it("facilitate pipeline has map, retrieve, teach, verify nodes", () => {
  const ids = FACILITATE_PIPELINE.nodes.map((n) => n.id);
  expect(ids).toEqual(expect.arrayContaining(["parse", "fetch", "map", "retrieve", "teach", "verify"]));
});
```

- [ ] **Step 2: Run, confirm FAIL** — `FACILITATE_PIPELINE` undefined.

- [ ] **Step 3: Implement** — add a `FACILITATE_PIPELINE` export in `chapterPipeline.ts` (same `ChapterNode`/`ChapterEdge` shape) with nodes: parse(+resolve) → fetch → map (LLM) → retrieve (data, "adaptive same-author-first") → teach (LLM) → verify (LLM), plus the `clarify` branch from parse. Keep `CHAPTER_PIPELINE` (used by resume). Update `chapterMode.ts` `FACILITATE_MODE` description + features to the new behaviour (concept map, key points, clickable concepts, simplify-not-expand). Have the facilitate modal use `FACILITATE_PIPELINE` (check `ChapterPipelineDiagram`/`ChapterFacilitateModal` — pass the facilitate pipeline when mode is facilitate).

- [ ] **Step 4: Run** `cd web && npx vitest run src/data/ && npx tsc --noEmit`.

- [ ] **Step 5: Commit**
```bash
git add web/src/data/chapterPipeline.ts web/src/data/chapterMode.ts web/src/data/chapterPipeline.test.ts
git commit -m "feat(web): facilitate pipeline diagram + mode copy"
```

---

## Task 12: Docs (lockstep)

**Files:** Create `docs/services/chat-features/53-facilitate-concept-map.md`; Modify `docs/services/chat.md`, `docs/system/invariants.md`, `docs/system/changelog.md`, `docs/common ground/Elements/chat.html`, `CLAUDE.md`

- [ ] **Step 1: Feature doc 53** — purpose (facilitate now teaches by clarifying), the pipeline + mermaid (from spec §3), the adaptive sub-retrieval policy, the schemas, the concept-anchor/modal/footnote UX, the env table (`FACILITATE_MAX_CONCEPTS`, `FACILITATE_MAX_KEYPOINTS`, `CONCEPT_MIN_SCORE`, `FACILITATE_SUBRETRIEVAL`), and the eval-harness note. Link the eval table.

- [ ] **Step 2: chat.md** — note `facilitate` emits `structured_output.schema="FacilitateDigest"` and the new `stage` keys (map/retrieve/teach/verify); resume still emits `ChapterDigest`.

- [ ] **Step 3: invariants.md** — add: "facilitate teaches by clarifying — body never longer than source; extra detail lives only in concept anchors; block order == section order; sub-retrieval prefers same author + prior section, escalating only below CONCEPT_MIN_SCORE."

- [ ] **Step 4: changelog.md** — dated entry (2026-06-01).

- [ ] **Step 5: Elements/chat.html** — add the facilitate concept-map flow to the Chat page.

- [ ] **Step 6: CLAUDE.md** — add `53 facilitate-concept-map` to the chat-features index row.

- [ ] **Step 7: Commit**
```bash
git add "docs/services/chat-features/53-facilitate-concept-map.md" docs/services/chat.md docs/system/invariants.md docs/system/changelog.md "docs/common ground/Elements/chat.html" CLAUDE.md
git commit -m "docs(chat): facilitate concept-map (feature 53 + sse + invariants)"
```

---

## Task 13: Full verification

**Files:** none

- [ ] **Step 1: Backend** `.venv/bin/python -m pytest src/services/chat/tests/ -q` — all pass.
- [ ] **Step 2: Frontend** `cd web && npx vitest run && npx tsc --noEmit && npm run build` — all green.
- [ ] **Step 3: Browser on :5175** — facilitate, send "facilitate chapter 7 sections 7.1 to 7.4 of hansen probability": expect short paragraphs + a Key points list + colored clickable concept anchors; click an anchor → modal with explanation + provenance; a step-bearing formula anchor shows KaTeX steps. Open the facilitate (i) modal → diagram shows map/retrieve/teach/verify. Compare against `docs/common ground/Elements/chat.html`.
- [ ] **Step 4: Final commit** (if verify fixes).

---

## Notes for the implementer
- **Chinese wall:** `facilitate.py` imports only `src.core.*` + `src.services.chat.*`. `fetch_concept_support` lives in `retrieval.py` (chat sibling).
- **Fail-open everywhere:** map/explain/teach/verify each degrade to a safe default; the digest never has a hole.
- **No new `ChatRequest` fields.** `FacilitateDigest` rides the existing `structuredOutput` rendering path (schema `"FacilitateDigest"`).
- **resume/qa/tutor untouched.** Only the `facilitate` route changes.
- The eval harness (Task 9) is the "keep testing until best combination" loop — run it before finalizing prompts; keep it in-repo for future tuning.
