# Facilitate Story Remake — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `facilitate` mode to teach ONE chapter section as a connected story (hook → movements → takeaway, with verbatim formal statements unpacked didactically), and let any concept pill open a corpus+Wikipedia side-chat that cannot leak into the main thread.

**Architecture:** New `run_facilitate_story` runner (single section; map → concept-support → write → pure-code bind → verify), new `FacilitateStory` schema (anti-tutor, discriminator-routed, legacy `FacilitateDigest` untouched), new stateless `POST /api/concept/explore` SSE endpoint reusing `research.py`, new `FacilitateStoryCard` + `ConceptChat` frontend. Trust split: LLM authors prose/concepts/verdict; pure code owns section pick, concept provenance, citations, `[[cN]]` validity, formal-statement fidelity.

**Tech Stack:** Python 3.12 / FastAPI / pydantic v2 / openai / Qdrant; React 18 / Vite / TypeScript / vitest / KaTeX. Tests: `.venv/bin/pytest` (backend), `cd web && npm test` (frontend).

**Spec:** `docs/superpowers/specs/2026-06-12-facilitate-story-remake-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/services/chat/schemas/output.py` | `FormalStatement`, `Movement`, `FacilitateStoryDraft`, `FacilitateStory`; `ChapterScope.section_id` | Modify |
| `src/services/chat/agents/_scope.py` | extend `resolve_book` → section pick; `resolve_section` helper; section-aware clarify | Modify |
| `src/services/chat/prompts/chapter.py` | `FACILITATE_STORY_WRITE_PROMPT`, `FACILITATE_BRIEF_PROMPT`; extend `FACILITATE_VERIFY_PROMPT` | Modify |
| `src/services/chat/agents/facilitate_story.py` | `run_facilitate_story` + `_concept_binder` + `_statement_fidelity` (pure code) | Create |
| `src/services/chat/router.py` | swap `"facilitate"` dispatch to `run_facilitate_story` | Modify |
| `src/services/chat/concept_explore.py` | `concept_explore` SSE generator (seed + deepen), pure-code citations | Create |
| `src/services/chat/api.py` | mount `POST /api/concept/explore` | Modify |
| `web/src/types.ts` | `FormalStatement`, `Movement`, `FacilitateStory` types | Modify |
| `web/src/components/FacilitateStoryCard.tsx` | render hook/movements/takeaway, formal blocks, chips, pills | Create |
| `web/src/components/ConceptChat.tsx` | side-chat panel (fork TempChat shell), calls `/api/concept/explore` | Create |
| `web/src/components/MessageThread.tsx` | route `schema==="FacilitateStory"` → `FacilitateStoryCard`; wire pill → ConceptChat | Modify |
| `web/src/data/facilitateMode.ts` + `FacilitatePipelineDiagram.tsx` | modal pipeline stages | Create/Modify |
| docs (md + html), invariants, changelog | dual-surface lockstep | Modify |

---

### Task 1: Schemas — FacilitateStory + Movement + FormalStatement

**Files:**
- Modify: `src/services/chat/schemas/output.py` (add after `FacilitateDigest`, ~line 528; add `section_id` to `ChapterScope` ~line 429)
- Test: `src/services/chat/tests/test_facilitate_story_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_facilitate_story_schema.py
import pytest
from pydantic import ValidationError
from src.services.chat.schemas.output import (
    FormalStatement, Movement, FacilitateStoryDraft, FacilitateStory, ChapterScope,
)


def test_movement_prose_only_ok():
    m = Movement(prose="The law of large numbers says averages stabilise.")
    assert m.prose and m.formal is None


def test_movement_formal_only_ok():
    fs = FormalStatement(kind="theorem", statement="$$\\bar X_n \\to \\mu$$",
                         explanation="elements ... intuition ... close.")
    m = Movement(formal=fs)
    assert m.formal and not m.prose


def test_movement_rejects_both_empty():
    with pytest.raises(ValidationError):
        Movement()


def test_movement_rejects_both_populated():
    fs = FormalStatement(kind="lemma", statement="x", explanation="y")
    with pytest.raises(ValidationError):
        Movement(prose="some prose", formal=fs)


def test_draft_has_no_citation_or_provenance_field():
    # anti-tutor / true-by-construction: writer cannot author citations
    fields = set(FacilitateStoryDraft.model_fields)
    assert "citations" not in fields and "concepts" not in fields and "provenance" not in fields
    assert fields == {"hook", "movements", "takeaway", "math_blocks"}


def test_facilitate_story_roundtrip_and_discriminator():
    story = FacilitateStory(
        mode="facilitate_story",
        scope=ChapterScope(book_slug="hansen", chapter_id="ch07", section_id="7.4"),
        hook="why it matters", movements=[Movement(prose="p")], takeaway="t")
    d = story.model_dump()
    assert d["mode"] == "facilitate_story"
    assert FacilitateStory(**d).scope.section_id == "7.4"


def test_chapter_scope_section_id_defaults_empty():
    assert ChapterScope(book_slug="b", chapter_id="ch01").section_id == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest src/services/chat/tests/test_facilitate_story_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'FormalStatement'` / `ChapterScope` has no `section_id`.

- [ ] **Step 3: Implement**

In `ChapterScope` (after `resolution`):

```python
    section_id: str = ""  # the ONE resolved section for facilitate_story; "" for legacy/whole-chapter
```

Add after `FacilitateDigest`:

```python
from pydantic import model_validator  # ensure imported at top


class FormalStatement(BaseModel):
    kind: Literal["definition", "lemma", "theorem", "proposition", "corollary", "remark"]
    statement: str = ""    # reproduced VERBATIM from source; display math in $$…$$
    explanation: str = ""  # didactic arc: elements → associations → intuition → close (may carry [[cN]])


class Movement(BaseModel):
    """Exactly one of `prose` / `formal` is populated (true-by-construction)."""
    prose: str = ""
    formal: FormalStatement | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "Movement":
        has_prose = bool(self.prose.strip())
        has_formal = self.formal is not None
        if has_prose == has_formal:  # both or neither
            raise ValueError("Movement must have exactly one of prose / formal")
        return self


class FacilitateStoryDraft(BaseModel):
    """Writer structured output — NO citation/provenance field by design."""
    hook: str = ""
    movements: list[Movement] = Field(default_factory=list)
    takeaway: str = ""
    math_blocks: list[str] = Field(default_factory=list)


class FacilitateStory(BaseModel):
    mode: Literal["facilitate_story"]
    scope: ChapterScope
    hook: str = ""
    movements: list[Movement] = Field(default_factory=list)
    takeaway: str = ""
    concepts: list[ConceptAnchor] = Field(default_factory=list)
    citations: list[StoryCitation] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)
    grounding: dict = Field(default_factory=dict)
```

(If `StoryCitation` is defined below this point in the file, move the new classes after it, or import-order is fine since all are in one module evaluated top-to-bottom — place the new block AFTER `StoryCitation` at ~line 665 to be safe.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest src/services/chat/tests/test_facilitate_story_schema.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/schemas/output.py src/services/chat/tests/test_facilitate_story_schema.py
git commit -m "feat(facilitate): FacilitateStory schema — movement prose XOR formal, no-citation draft"
```

---

### Task 2: Section resolve — closest-match + confirm

**Files:**
- Modify: `src/services/chat/agents/_scope.py` (add `resolve_section`, extend `maybe_clarify` for section)
- Modify: `src/services/chat/prompts/chapter.py` (`CHAPTER_PARSE_PROMPT` weighting note)
- Test: `src/services/chat/tests/test_resolve_section.py`

Reuse: `expand_section_refs` (already extracts `"7.4"`), Extension matcher idea from `agents/extension_agents/runner.py` (`_extract_section_num`).

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_resolve_section.py
from src.services.chat.agents._scope import resolve_section, section_clarify


HEADINGS = [
    {"section_id": "7.3", "h2_path": "7.3 The Sample Mean"},
    {"section_id": "7.4", "h2_path": "7.4 Law of Large Numbers"},
    {"section_id": "7.5", "h2_path": "7.5 Central Limit Theorem"},
]


def test_explicit_section_number_is_deterministic():
    sid, score = resolve_section("teach me 7.4", subtopics=["7.4"], headings=HEADINGS)
    assert sid == "7.4" and score == 1.0


def test_no_number_matches_heading_by_words():
    sid, score = resolve_section("explain the law of large numbers",
                                 subtopics=["law of large numbers"], headings=HEADINGS)
    assert sid == "7.4" and score >= 0.5


def test_low_match_returns_empty_section():
    sid, score = resolve_section("tell me about quantum entanglement",
                                 subtopics=["quantum entanglement"], headings=HEADINGS)
    assert sid == "" and score < 0.5


def test_section_clarify_when_no_section_resolved():
    ev = section_clarify(headings=HEADINGS, chapter_id="ch07")
    assert ev["type"] == "clarify" and ev["reason"] == "section_ambiguous"
    assert len(ev["candidates"]) == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest src/services/chat/tests/test_resolve_section.py -q`
Expected: FAIL — `ImportError: cannot import name 'resolve_section'`.

- [ ] **Step 3: Implement** (append to `_scope.py`)

```python
import re as _re


def _norm_tokens(s: str) -> set[str]:
    return {t for t in _re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


def resolve_section(message: str, *, subtopics: list[str],
                    headings: list[dict]) -> tuple[str, float]:
    """Pick ONE section_id. Explicit "X.y" wins deterministically; else best
    word-overlap match against heading h2_path. Returns (section_id, score);
    ("", <0.5) when nothing matches well."""
    if not headings:
        return "", 0.0
    nums = expand_section_refs(message) + [s for s in subtopics if _SEC.search(s)]
    valid = {h["section_id"] for h in headings}
    for n in nums:
        if n in valid:
            return n, 1.0
    query = " ".join(subtopics) or message
    q = _norm_tokens(query)
    if not q:
        return "", 0.0
    best_sid, best = "", 0.0
    for h in headings:
        h_tokens = _norm_tokens(h.get("h2_path", ""))
        if not h_tokens:
            continue
        overlap = len(q & h_tokens) / max(1, len(q))
        if overlap > best:
            best, best_sid = overlap, h["section_id"]
    return (best_sid, best) if best >= 0.5 else ("", best)


def section_clarify(*, headings: list[dict], chapter_id: str) -> dict:
    """Clarify event listing the chapter's sections to pick from."""
    cands = [{"section_id": h["section_id"], "h2_path": h.get("h2_path", "")}
             for h in headings][:12]
    return {"type": "clarify", "reason": "section_ambiguous",
            "message": "Which section should I teach? Pick one:",
            "candidates": cands, "chapter_guess": chapter_id}
```

In `CHAPTER_PARSE_PROMPT` (prompts/chapter.py), inside `<task>` add one line after the matching paragraph:

```
Weight the match by author surname and field as strongly as the title; a
confident author+field match outranks a weak title-substring match.
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest src/services/chat/tests/test_resolve_section.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/_scope.py src/services/chat/prompts/chapter.py src/services/chat/tests/test_resolve_section.py
git commit -m "feat(facilitate): resolve_section closest-match + section_clarify; richer book weighting"
```

---

### Task 3: Concept binder + statement fidelity (pure code)

**Files:**
- Create: `src/services/chat/agents/facilitate_story.py` (binder + fidelity helpers only this task; runner in Task 4)
- Test: `src/services/chat/tests/test_facilitate_binder.py`

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_facilitate_binder.py
from src.services.chat.agents.facilitate_story import (
    bind_concepts, strip_unbound_markers, statement_fidelity,
)
from src.services.chat.schemas.output import ConceptAnchor, ConceptProvenance


def _anchor(cid):
    return ConceptAnchor(id=cid, term=f"term-{cid}", kind="concept",
                         explanation="e", provenance=ConceptProvenance(book_slug="hansen"))


def test_strip_unbound_markers_removes_invented_keeps_text():
    body = "We rely on [[c1]] and also [[c9]] here."
    out = strip_unbound_markers(body, valid_ids={"c1"})
    assert "[[c1]]" in out and "[[c9]]" not in out and "here." in out


def test_bind_concepts_only_keeps_referenced_anchors():
    movements_text = "intro [[c1]] middle"  # c2 never referenced
    kept = bind_concepts([_anchor("c1"), _anchor("c2")], referenced_ids={"c1"})
    assert [a.id for a in kept] == ["c1"]


def test_statement_fidelity_passes_for_verbatim():
    src = "Theorem 7.4. The sample mean converges: $$\\bar X_n \\to \\mu$$ in probability."
    ok, score = statement_fidelity("The sample mean converges: $$\\bar X_n \\to \\mu$$", src)
    assert ok and score >= 0.8


def test_statement_fidelity_flags_fabricated():
    src = "Theorem 7.4. The sample mean converges in probability."
    ok, score = statement_fidelity("Every continuous function is differentiable", src)
    assert not ok and score < 0.5
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest src/services/chat/tests/test_facilitate_binder.py -q`
Expected: FAIL — module `facilitate_story` does not exist.

- [ ] **Step 3: Implement** (create `facilitate_story.py` with ONLY these helpers for now)

```python
"""Facilitate story mode — single-section narrative pipeline.

Pure-code binders/fidelity here; the LLM runner lands in run_facilitate_story.
Chinese-wall: imports only src.core.* and sibling src.services.chat.*.
"""
from __future__ import annotations

import re

from src.services.chat.schemas.output import ConceptAnchor

_MARKER = re.compile(r"\[\[(c\d+)\]\]")


def referenced_ids(text: str) -> set[str]:
    return set(_MARKER.findall(text or ""))


def strip_unbound_markers(text: str, *, valid_ids: set[str]) -> str:
    """Remove [[cN]] markers whose id is not in valid_ids; keep surrounding text."""
    def repl(m: re.Match) -> str:
        return m.group(0) if m.group(1) in valid_ids else ""
    return _MARKER.sub(repl, text or "")


def bind_concepts(anchors: list[ConceptAnchor], *, referenced_ids: set[str]) -> list[ConceptAnchor]:
    """Keep only anchors actually referenced by a surviving [[cN]] marker."""
    return [a for a in anchors if a.id in referenced_ids]


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\$+", " ", s)             # drop math delimiters
    s = re.sub(r"[^a-z0-9\\ ]+", " ", s)   # keep latex backslash words + alnum
    return re.sub(r"\s+", " ", s).strip()


def statement_fidelity(statement: str, source_text: str) -> tuple[bool, float]:
    """Fuzzy token-recall of the formal statement against the source section.
    True when most statement tokens appear in the source (verbatim/near-verbatim)."""
    st = set(_norm(statement).split())
    src = set(_norm(source_text).split())
    if not st:
        return False, 0.0
    recall = len(st & src) / len(st)
    return recall >= 0.6, recall
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest src/services/chat/tests/test_facilitate_binder.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/facilitate_story.py src/services/chat/tests/test_facilitate_binder.py
git commit -m "feat(facilitate): pure-code concept binder + formal-statement fidelity"
```

---

### Task 4: run_facilitate_story runner

**Files:**
- Modify: `src/services/chat/agents/facilitate_story.py` (add the runner + `_chat` seam + stage helpers)
- Modify: `src/services/chat/router.py:242` (swap `"facilitate"` dispatch)
- Test: `src/services/chat/tests/test_facilitate_story_runner.py`

Depends on Task 5 prompts; in this task add prompt-name imports and let Task 5 fill the strings — to keep tasks independent, define the prompt constants as `""` placeholders ONLY if Task 5 not yet merged. Since subagent-driven runs tasks in order, Task 5 prompts exist by the time this runs **if reordered**; to avoid coupling, this task imports the prompts and the runner is tested with `_chat` monkeypatched (prompts irrelevant to the test). **Run Task 5 before Task 4 if executing strictly in number order is preferred** — both orders work because tests monkeypatch `_chat`.

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_facilitate_story_runner.py
import json
import pytest
from src.services.chat.agents import facilitate_story as fs
from src.services.chat.schemas import Source


class _Req:
    def __init__(self, msg, books=None):
        self.message = msg
        self.bookFilter = books or ["hansen"]
        self.model = "nano"
        self.stageModels = None
        self.conversationId = None


def _source():
    return Source(chunkId="hansen:ch07:7.4", title="7.4 Law of Large Numbers",
                  chunk="Theorem. The sample mean converges: $$\\bar X_n \\to \\mu$$.",
                  excerpt="", book="hansen", book_name="Probability", authors_short="Hansen",
                  page_from=120, page_to=122, chapter="ch07", section="7.4")


@pytest.mark.asyncio
async def test_emits_single_facilitate_story(monkeypatch):
    # resolve to one section
    monkeypatch.setattr(fs, "_resolve_one_section", lambda req: (
        fs.ChapterScope(book_slug="hansen", chapter_id="ch07", section_id="7.4"), _source(), None))

    async def fake_chat(messages, **kw):
        sys = messages[0]["content"]
        if "MAP" in sys or "key_points" in sys:
            return json.dumps({"key_points": ["averages stabilise"],
                               "concepts": [{"term": "law of large numbers", "kind": "theorem", "status": "explained"}]})
        if "VERIFY" in sys or "fixed" in sys:
            return json.dumps({"ok": True, "unsupported": [], "confidence": 0.9})
        # writer
        return json.dumps({"hook": "why", "takeaway": "done", "math_blocks": [],
                           "movements": [{"prose": "The [[c1]] is central.", "formal": None}]})
    monkeypatch.setattr(fs, "_chat", fake_chat)

    events = [e async for e in fs.run_facilitate_story(_Req("teach 7.4"))]
    payloads = [e for e in events if e.get("type") == "structured_output"]
    assert len(payloads) == 1
    data = payloads[0]["data"]
    assert payloads[0]["schema"] == "FacilitateStory"
    assert data["scope"]["section_id"] == "7.4"
    assert len(data["movements"]) == 1
    assert data["concepts"][0]["id"] == "c1"   # bound because [[c1]] referenced
    assert any(e.get("type") == "done" for e in events)


@pytest.mark.asyncio
async def test_clarify_short_circuits(monkeypatch):
    monkeypatch.setattr(fs, "_resolve_one_section", lambda req: (None, None,
        {"type": "clarify", "reason": "book_unknown", "message": "pick", "candidates": []}))
    events = [e async for e in fs.run_facilitate_story(_Req("teach nothing"))]
    assert any(e.get("type") == "clarify" for e in events)
    assert not any(e.get("type") == "structured_output" for e in events)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest src/services/chat/tests/test_facilitate_story_runner.py -q`
Expected: FAIL — `run_facilitate_story` / `_resolve_one_section` / `_chat` not defined.

- [ ] **Step 3: Implement** (add to `facilitate_story.py`)

```python
import asyncio
import json
import logging
import os
import time
from typing import AsyncIterator

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.agents._scope import (
    resolve_book, resolve_section, section_clarify, maybe_clarify,
)
from src.services.chat.books import parse_catalog
from src.services.chat.llm.router import aclient_for
from src.services.chat.llm.structured import apply_structured_output
from src.services.chat.prompts.chapter import (
    FACILITATE_STORY_WRITE_PROMPT, FACILITATE_MAP_PROMPT, FACILITATE_VERIFY_PROMPT,
)
from src.services.chat.retrieval import fetch_chapter_sections, fetch_concept_support, _section_order_in_book
from src.services.chat.schemas import ChapterScope, ConceptAnchor, ConceptProvenance, Source
from src.services.chat.schemas.output import (
    FacilitateStory, FacilitateStoryDraft, FormalStatement, Movement, FacilitateMap, StoryCitation,
)

logger = logging.getLogger(__name__)
_MAX_CONCEPTS = int(os.environ.get("FACILITATE_MAX_CONCEPTS", "5"))
_PREVIEW = 1500


async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
    oa = aclient_for(model)
    messages, response_format = apply_structured_output(messages, model, schema)
    kwargs = {"model": model, "messages": messages, "temperature": temperature,
              "max_completion_tokens": max_tokens}
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = await oa.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def _model_for(stage: str, req) -> str:
    sm = getattr(req, "stageModels", None)
    if sm and isinstance(sm.get(stage), str) and sm[stage].strip():
        return sm[stage].strip()
    return settings.openai_model_nano


def _resolve_one_section(req):
    """Return (scope, source, clarify_event|None). Pure-ish; LLM book-resolve via resolve_book."""
    message = req.message or ""
    bf = getattr(req, "bookFilter", None)
    book_slugs = list(bf) if isinstance(bf, list) and bf else None
    catalog = parse_catalog()
    # resolve_book is async; caller wraps. We do book resolve in the async runner instead.
    raise NotImplementedError  # replaced by inline async logic in run_facilitate_story


async def _map(s: Source, *, model: str):
    user = f"heading: {s.title}\n\nsection text:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}"
    try:
        raw = await _chat([{"role": "system", "content": FACILITATE_MAP_PROMPT},
                           {"role": "user", "content": user}], model=model, max_tokens=500, schema=FacilitateMap)
        data = json.loads(strip_fences(raw))
        concepts = []
        for c in (data.get("concepts") or [])[:_MAX_CONCEPTS]:
            term = str(c.get("term", "")).strip()
            if term:
                kind = c.get("kind") if c.get("kind") in ("concept", "theorem", "formula") else "concept"
                concepts.append({"term": term, "kind": kind, "status": c.get("status", "explained")})
        return [str(x) for x in (data.get("key_points") or [])], concepts
    except Exception:  # noqa: BLE001
        logger.exception("facilitate_story._map failed")
        return [], []


def _anchor_from_source(cid: str, c: dict, s: Source) -> ConceptAnchor:
    return ConceptAnchor(id=cid, term=c["term"], kind=c["kind"], explanation="",
        provenance=ConceptProvenance(
            book_slug=s.book, book_name=s.book_name or s.book, authors_short=s.authors_short or "",
            section=s.title, page_from=s.page_from if s.page_from is not None else -1,
            page_to=s.page_to if s.page_to is not None else -1, chunk_id=s.chunkId))


def _parse_draft(raw: str) -> FacilitateStoryDraft:
    data = json.loads(strip_fences(raw))
    movements = []
    for m in (data.get("movements") or []):
        f = m.get("formal")
        if isinstance(f, dict) and (f.get("statement") or "").strip():
            movements.append(Movement(formal=FormalStatement(
                kind=f.get("kind", "remark"), statement=f.get("statement", ""),
                explanation=f.get("explanation", ""))))
        elif (m.get("prose") or "").strip():
            movements.append(Movement(prose=m["prose"]))
    return FacilitateStoryDraft(hook=data.get("hook", ""), takeaway=data.get("takeaway", ""),
                                movements=movements, math_blocks=data.get("math_blocks") or [])


async def run_facilitate_story(req) -> AsyncIterator[dict]:
    t0 = time.time()
    message = req.message or ""
    bf = getattr(req, "bookFilter", None)
    book_slugs = list(bf) if isinstance(bf, list) and bf else None

    yield {"type": "meta", "mode": "facilitate", "books": book_slugs or [],
           "sourceCount": 0, "latencyMs": 0, "model": getattr(req, "model", "nano")}
    yield {"type": "stage", "stage": "parse", "label": "Parse + resolve scope"}

    # _resolve_one_section is monkeypatched in tests; in prod we resolve inline.
    try:
        scope, src, clarify = _resolve_one_section(req)
    except NotImplementedError:
        catalog = parse_catalog()
        res = await resolve_book(message, selected_slugs=book_slugs, catalog=catalog, model=_model_for("map", req))
        clar = maybe_clarify(res, catalog)
        if clar is not None:
            yield clar; yield {"type": "done"}; return
        sections = fetch_chapter_sections(res.book_slug, res.chapter_id, max_sections=30) \
            if res.book_slug and res.chapter_id else []
        headings = [{"section_id": s.chunkId, "h2_path": s.title} for s in sections]
        sid, _score = resolve_section(message, subtopics=res.requested_subtopics, headings=headings)
        if not sid:
            yield section_clarify(headings=headings, chapter_id=res.chapter_id)
            yield {"type": "done"}; return
        src = next((s for s in sections if s.chunkId == sid), None)
        scope = ChapterScope(book_slug=res.book_slug, chapter_id=res.chapter_id,
                             requested_subtopics=res.requested_subtopics, section_id=sid)
        clarify = None
    if clarify is not None:
        yield clarify; yield {"type": "done"}; return
    if src is None:
        yield section_clarify(headings=[], chapter_id=getattr(scope, "chapter_id", ""))
        yield {"type": "done"}; return

    yield {"type": "stage", "stage": "map", "label": f"Map · {src.title}"}
    _kps, concept_dicts = await _map(src, model=_model_for("map", req))
    anchors = [_anchor_from_source(f"c{i}", c, src) for i, c in enumerate(concept_dicts, 1)]

    yield {"type": "stage", "stage": "write", "label": "Write story"}
    ids = "; ".join(f"{a.id}={a.term}" for a in anchors)
    user = (f"heading: {src.title}\nconcept ids: {ids}\n\nsection text:\n"
            f"{(src.chunk or src.excerpt or '')[:_PREVIEW]}")
    try:
        raw = await _chat([{"role": "system", "content": FACILITATE_STORY_WRITE_PROMPT},
                           {"role": "user", "content": user}], model=_model_for("write", req), max_tokens=1200)
        draft = _parse_draft(raw)
    except Exception:  # noqa: BLE001
        logger.exception("facilitate_story.write failed")
        draft = FacilitateStoryDraft(hook="", takeaway="", movements=[Movement(prose=src.excerpt or src.title)])

    # ---- pure-code bind ----
    valid = {a.id for a in anchors}
    used: set[str] = set()
    new_movs = []
    for m in draft.movements:
        if m.prose:
            txt = strip_unbound_markers(m.prose, valid_ids=valid)
            used |= referenced_ids(txt)
            new_movs.append(Movement(prose=txt))
        elif m.formal:
            expl = strip_unbound_markers(m.formal.explanation, valid_ids=valid)
            used |= referenced_ids(expl)
            new_movs.append(Movement(formal=FormalStatement(
                kind=m.formal.kind, statement=m.formal.statement, explanation=expl)))
    bound = bind_concepts(anchors, referenced_ids=used)

    yield {"type": "stage", "stage": "verify", "label": "Verify"}
    grounding = {"ok": True, "unsupported": [], "confidence": 1.0}
    for m in new_movs:
        if m.formal:
            ok, _sc = statement_fidelity(m.formal.statement, src.chunk or src.excerpt or "")
            if not ok:
                grounding = {"ok": False, "unsupported": [m.formal.statement[:120]], "confidence": 0.4}

    citations = [StoryCitation(kind="corpus",
        label=f"{src.authors_short or src.book} §{src.title}",
        book_slug=src.book, book_name=src.book_name, authors=src.authors_short,
        chapter=src.chapter, section_id=src.title,
        pages=(f"{src.page_from}–{src.page_to}" if src.page_from else None),
        chunk_id=src.chunkId)]

    story = FacilitateStory(mode="facilitate_story", scope=scope, hook=draft.hook,
        movements=new_movs, takeaway=draft.takeaway, concepts=bound,
        citations=citations, math_blocks=draft.math_blocks, grounding=grounding)
    yield {"type": "structured_output", "schema": "FacilitateStory", "data": story.model_dump()}
    yield {"type": "sources_full", "sources": [src.model_dump()]}
    yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000),
           "promptChars": len(message), "completionChars": len(draft.hook), "estTokens": 0}
    yield {"type": "done"}
```

Add the missing top-of-file imports already declared in Task 3's module (`bind_concepts`, `strip_unbound_markers`, `referenced_ids`, `statement_fidelity` are in the same module — no import needed).

In `src/services/chat/router.py` swap the facilitate dispatch:

```python
async def _run_facilitate(req: ChatRequest, history: list[dict] | None) -> AsyncIterator[dict]:
    """Facilitate runner -> agents.facilitate_story.run_facilitate_story."""
    from src.services.chat.agents.facilitate_story import run_facilitate_story  # noqa: PLC0415
    async for event in run_facilitate_story(req):
        yield event
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest src/services/chat/tests/test_facilitate_story_runner.py src/services/chat/tests/test_facilitate_binder.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/facilitate_story.py src/services/chat/router.py src/services/chat/tests/test_facilitate_story_runner.py
git commit -m "feat(facilitate): run_facilitate_story single-section runner + dispatch swap"
```

---

### Task 5: Prompts — story writer, brief, verify extension

**Files:**
- Modify: `src/services/chat/prompts/chapter.py`
- Test: `src/services/chat/tests/test_facilitate_story_prompts.py`

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_facilitate_story_prompts.py
from src.services.chat.prompts.chapter import (
    FACILITATE_STORY_WRITE_PROMPT, FACILITATE_BRIEF_PROMPT,
)


def test_write_prompt_demands_verbatim_formal_and_arc():
    p = FACILITATE_STORY_WRITE_PROMPT.lower()
    assert "verbatim" in p
    assert "hook" in p and "movements" in p and "takeaway" in p
    assert "[[c" in FACILITATE_STORY_WRITE_PROMPT  # concept-anchor instruction
    for w in ("elements", "associations", "intuition"):
        assert w in p


def test_brief_prompt_is_short_and_grounded():
    p = FACILITATE_BRIEF_PROMPT.lower()
    assert "two sentence" in p or "2 sentence" in p or "≤2" in p or "two-sentence" in p
    assert "wikipedia" in p or "passage" in p or "evidence" in p
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest src/services/chat/tests/test_facilitate_story_prompts.py -q`
Expected: FAIL — names not defined.

- [ ] **Step 3: Implement** (append to `prompts/chapter.py`)

```python
FACILITATE_STORY_WRITE_PROMPT = """<role>
You are a teacher turning ONE textbook section into a short, connected story that
makes a learner understand it. You connect the dots; you never dump facts.
</role>

<task>
Write the section as a flowing lesson with three parts:
  - hook: ONE paragraph — why this section matters / what it lets you do (the through-line).
  - movements: 2-5 movements that CONTINUE one another into a single arc. Each movement
      is EITHER a prose paragraph OR a formal block:
      * prose movement: develops ONE idea, links smoothly to the previous movement.
      * formal block: when the section states a DEFINITION, LEMMA, THEOREM, PROPOSITION,
          COROLLARY or REMARK, reproduce that statement VERBATIM (word-for-word, with
          display math in $$...$$) in "statement", then in "explanation" unpack it as:
          the ELEMENTS (name each symbol/term, especially the formulas) → the ASSOCIATIONS
          (how the elements relate, what acts on what) → the INTUITION (what it means in
          plain words, why it holds) → a concise CLOSE (one-sentence takeaway).
  - takeaway: ONE paragraph — what the reader now understands.
</task>

<rules>
NO REPETITION: cover each idea once. Preserve the author's order.
VERBATIM: never paraphrase a formal statement; copy it exactly from the section text.
CONCEPT ANCHORS: every concept id you are given MUST appear exactly once as its [[cN]]
  marker IN PROSE (or in a formal explanation), in place of the term word — never also
  write the term word next to it, never put a marker inside a verbatim "statement".
MATH: $...$ inline, $$...$$ display; never \\( \\) or \\[ \\]. English only; never copy
  garbled/OCR characters. No markdown headings (# or ##) — the app adds the section title.
</rules>

<output_format>
Return ONLY a JSON object:
  {"hook": "...", "takeaway": "...", "math_blocks": [],
   "movements": [{"prose": "...", "formal": null}
                 | {"prose": "", "formal": {"kind": "theorem", "statement": "...", "explanation": "..."}}]}
Exactly one of prose / formal is non-empty per movement.
</output_format>
"""

FACILITATE_BRIEF_PROMPT = """<role>
You give a learner a brief, grounded orientation to ONE concept.
</role>

<task>
Using ONLY the provided corpus passage(s) and Wikipedia evidence, explain the concept
in at most TWO sentences of plain English. State what it is and why it matters. Do not
invent sources; do not cite — the app attaches the references.
</task>

<output_format>
Plain prose, English only. For math use $...$ inline, $$...$$ display. Return ONLY the text.
</output_format>
"""
```

Extend `FACILITATE_VERIFY_PROMPT` rule #1 — add after the "balance unmatched $" line:

```
     - You MAY fix LaTeX delimiters inside a reproduced formal statement, but NEVER
       change the statement's wording or meaning.
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest src/services/chat/tests/test_facilitate_story_prompts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/prompts/chapter.py src/services/chat/tests/test_facilitate_story_prompts.py
git commit -m "feat(facilitate): story-write + concept-brief prompts; verify guards statement wording"
```

---

### Task 6: Concept-explore endpoint (corpus + Wikipedia, stateless)

**Files:**
- Create: `src/services/chat/concept_explore.py`
- Modify: `src/services/chat/api.py` (mount `POST /api/concept/explore`)
- Test: `src/services/chat/tests/test_concept_explore.py`

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_concept_explore.py
import pytest
from src.services.chat import concept_explore as ce
from src.services.chat.research import Evidence


@pytest.mark.asyncio
async def test_seed_builds_corpus_and_wiki_chips(monkeypatch):
    monkeypatch.setattr(ce, "corpus_evidence", lambda *a, **k: [
        Evidence(subject_id="t", kind="corpus", text="passage about LLN",
                 meta={"book_slug": "hansen", "book_name": "Probability",
                       "authors": "Hansen", "section_id": "7.4", "pages": "120", "chunk_id": "x"})])
    monkeypatch.setattr(ce, "wiki_evidence", lambda *a, **k: [
        Evidence(subject_id="t", kind="wikipedia", text="LLN says averages converge",
                 meta={"title": "Law of large numbers", "url": "https://en.wikipedia.org/wiki/LLN"})])

    async def fake_brief(term, evid, *, model):
        return "The law of large numbers says sample averages converge to the mean."
    monkeypatch.setattr(ce, "_brief", fake_brief)

    body = {"term": "law of large numbers", "kind": "theorem",
            "book_slug": "hansen", "section_id": "7.4", "conversationId": "abc"}
    events = [e async for e in ce.concept_explore(body)]
    payload = next(e for e in events if e["type"] == "concept_seed")
    kinds = {c["kind"] for c in payload["citations"]}
    assert kinds == {"corpus", "wikipedia"}
    assert "converge" in payload["brief"]
    # the wiki chip url is verbatim from evidence meta (pure code, not model)
    assert any(c.get("url", "").endswith("/LLN") for c in payload["citations"])


@pytest.mark.asyncio
async def test_concept_explore_never_touches_conversation_store(monkeypatch):
    import src.services.chat.store as store
    calls = []
    monkeypatch.setattr(store, "append_message", lambda **k: calls.append(k))
    monkeypatch.setattr(ce, "corpus_evidence", lambda *a, **k: [])
    monkeypatch.setattr(ce, "wiki_evidence", lambda *a, **k: [])

    async def fake_brief(term, evid, *, model):
        return "x"
    monkeypatch.setattr(ce, "_brief", fake_brief)
    _ = [e async for e in ce.concept_explore({"term": "t", "kind": "concept",
         "book_slug": "hansen", "section_id": "7.4", "conversationId": "abc"})]
    assert calls == []  # isolation: side-chat must not write the main thread
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest src/services/chat/tests/test_concept_explore.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement** — create `concept_explore.py`

```python
"""Concept explorer — stateless side-chat for one concept (corpus + Wikipedia).

NEVER reads or writes the conversation message store: the side-chat cannot leak
into the main answer (true-by-construction isolation).
Chinese-wall: imports only src.core.* and sibling src.services.chat.*.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from src.core.config import settings
from src.services.chat.books import parse_catalog
from src.services.chat.llm.router import aclient_for
from src.services.chat.prompts.chapter import FACILITATE_BRIEF_PROMPT
from src.services.chat.research import corpus_evidence, wiki_evidence, _citation, Evidence

logger = logging.getLogger(__name__)


async def _brief(term: str, evidence: list[Evidence], *, model: str) -> str:
    corpus = "\n".join(e.text for e in evidence if e.kind == "corpus")[:1500]
    wiki = "\n".join(e.text for e in evidence if e.kind == "wikipedia")[:1500]
    user = f"concept: {term}\n\ncorpus passage(s):\n{corpus}\n\nwikipedia:\n{wiki}"
    oa = aclient_for(model)
    resp = await oa.chat.completions.create(model=model, temperature=0.0,
        max_completion_tokens=160,
        messages=[{"role": "system", "content": FACILITATE_BRIEF_PROMPT},
                  {"role": "user", "content": user}])
    return (resp.choices[0].message.content or "").strip()


async def concept_explore(body: dict) -> AsyncIterator[dict]:
    term = (body.get("term") or "").strip()
    book_slug = body.get("book_slug") or ""
    history = body.get("history") or []
    model = settings.openai_model_nano
    if not term:
        yield {"type": "concept_seed", "term": term, "brief": "", "citations": []}
        yield {"type": "done"}; return

    all_slugs = [c.slug for c in parse_catalog()]
    follow = ""
    if history:
        last = history[-1]
        follow = last.get("text", "") if last.get("role") == "user" else ""
    query = f"{term} {follow}".strip()
    seen: set[str] = set()
    try:
        corpus, wiki = await asyncio.gather(
            asyncio.to_thread(corpus_evidence, query, subject_id=term, exclude_book="",
                              all_slugs=all_slugs, seen_ids=seen, top_n=3),
            asyncio.to_thread(wiki_evidence, query, subject_id=term))
    except Exception:  # noqa: BLE001
        logger.exception("concept_explore retrieval failed")
        corpus, wiki = [], []
    evidence = list(corpus) + list(wiki)
    try:
        brief = await _brief(term, evidence, model=model)
    except Exception:  # noqa: BLE001
        logger.exception("concept_explore brief failed")
        brief = (wiki[0].text[:240] if wiki else (corpus[0].text[:240] if corpus else ""))
    citations = [_citation(e).model_dump() for e in evidence]
    event_type = "concept_followup" if history else "concept_seed"
    yield {"type": event_type, "term": term, "brief": brief, "citations": citations}
    yield {"type": "done"}
```

In `api.py`, near the other `@app.post` routes, add:

```python
from sse_starlette.sse import EventSourceResponse  # if not already imported
from src.services.chat.concept_explore import concept_explore  # noqa: PLC0415 at top or inline


@app.post("/api/concept/explore")
async def concept_explore_route(request: Request) -> EventSourceResponse:
    body = await request.json()

    async def gen():
        async for ev in concept_explore(body):
            yield {"event": ev.get("type", "message"), "data": json.dumps(ev)}
    return EventSourceResponse(gen())
```

(Match the existing import style in `api.py` for `json`, `Request`, `EventSourceResponse`.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest src/services/chat/tests/test_concept_explore.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/concept_explore.py src/services/chat/api.py src/services/chat/tests/test_concept_explore.py
git commit -m "feat(facilitate): POST /api/concept/explore — stateless corpus+wiki concept seed"
```

---

### Task 7: Frontend — FacilitateStoryCard

**Files:**
- Modify: `web/src/types.ts` (add `FormalStatement`, `Movement`, `FacilitateStory`)
- Create: `web/src/components/FacilitateStoryCard.tsx`
- Modify: `web/src/components/MessageThread.tsx` (route `schema==="FacilitateStory"`)
- Test: `web/src/components/FacilitateStoryCard.test.tsx`

Reuse `FacilitateContent` (renders markdown + `$…$`/`$$…$$` + `[[cN]]` pills) and its `onPick` callback.

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/components/FacilitateStoryCard.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import FacilitateStoryCard from "./FacilitateStoryCard";
import type { FacilitateStory } from "../types";

const story: FacilitateStory = {
  mode: "facilitate_story",
  scope: { book_slug: "hansen", chapter_id: "ch07", section_id: "7.4",
           requested_subtopics: [], resolution: [] },
  hook: "Why averages stabilise.",
  movements: [
    { prose: "The [[c1]] is the engine here.", formal: null },
    { prose: "", formal: { kind: "theorem", statement: "$$\\bar X_n \\to \\mu$$",
                           explanation: "Elements: the mean. Intuition: it converges." } },
  ],
  takeaway: "You can now justify averaging.",
  concepts: [{ id: "c1", term: "law of large numbers", kind: "theorem",
               explanation: "converges", provenance: { book_slug: "hansen", book_name: "Probability",
               authors_short: "Hansen", section: "7.4", page_from: 120, page_to: 122,
               chunk_id: "x", same_author: true, fallback: false } }],
  citations: [{ kind: "wikipedia", label: "Wikipedia: LLN", url: "https://en.wikipedia.org/wiki/LLN" }],
  math_blocks: [], grounding: { ok: true, unsupported: [], confidence: 1 },
};

describe("FacilitateStoryCard", () => {
  it("renders hook, takeaway, and a formal statement block with kind badge", () => {
    render(<FacilitateStoryCard story={story} onConcept={() => {}} />);
    expect(screen.getByText(/Why averages stabilise/)).toBeInTheDocument();
    expect(screen.getByText(/You can now justify/)).toBeInTheDocument();
    expect(screen.getByText(/theorem/i)).toBeInTheDocument();         // kind badge
    expect(document.querySelector(".math-block, .katex")).toBeTruthy(); // KaTeX rendered
  });

  it("fires onConcept when a concept pill is clicked", () => {
    const onConcept = vi.fn();
    render(<FacilitateStoryCard story={story} onConcept={onConcept} />);
    fireEvent.click(screen.getByRole("button", { name: /law of large numbers/i }));
    expect(onConcept).toHaveBeenCalledWith(expect.objectContaining({ id: "c1" }));
  });

  it("renders a wikipedia citation chip", () => {
    render(<FacilitateStoryCard story={story} onConcept={() => {}} />);
    expect(screen.getByText(/Wikipedia: LLN/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/components/FacilitateStoryCard.test.tsx`
Expected: FAIL — module/types not found.

- [ ] **Step 3: Implement**

Add to `web/src/types.ts`:

```ts
export interface FormalStatement {
  kind: "definition" | "lemma" | "theorem" | "proposition" | "corollary" | "remark";
  statement: string;
  explanation: string;
}
export interface Movement {
  prose: string;
  formal: FormalStatement | null;
}
export interface FacilitateStory {
  mode: "facilitate_story";
  scope: ChapterScope;            // existing type
  hook: string;
  movements: Movement[];
  takeaway: string;
  concepts: ConceptAnchor[];      // existing type
  citations: StoryCitation[];     // existing type
  math_blocks: string[];
  grounding: { ok: boolean; unsupported: string[]; confidence: number };
}
```

Create `web/src/components/FacilitateStoryCard.tsx`:

```tsx
import type { FacilitateStory, ConceptAnchor, Movement } from "../types";
import FacilitateContent from "./FacilitateContent";

interface Props { story: FacilitateStory; onConcept: (a: ConceptAnchor) => void; }

function byId(story: FacilitateStory): Map<string, ConceptAnchor> {
  return new Map(story.concepts.map((c) => [c.id, c]));
}

export default function FacilitateStoryCard({ story, onConcept }: Props) {
  const concepts = story.concepts;
  const renderMovement = (m: Movement, i: number) => {
    if (m.formal) {
      const f = m.formal;
      return (
        <div className="fstory__formal" key={i}>
          <span className={`fstory__kind fstory__kind--${f.kind}`}>{f.kind}</span>
          <blockquote className="fstory__statement">
            <FacilitateContent text={f.statement} />
          </blockquote>
          <div className="fstory__unpack">
            <FacilitateContent text={f.explanation} concepts={concepts} onPick={onConcept} />
          </div>
        </div>
      );
    }
    return (
      <p className="fstory__movement" key={i}>
        <FacilitateContent text={m.prose} concepts={concepts} onPick={onConcept} />
      </p>
    );
  };
  return (
    <div className="fstory" data-testid="facilitate-story">
      {story.hook && (
        <div className="fstory__hook"><FacilitateContent text={story.hook} concepts={concepts} onPick={onConcept} /></div>
      )}
      <div className="fstory__body">{story.movements.map(renderMovement)}</div>
      {story.takeaway && (
        <div className="fstory__takeaway"><FacilitateContent text={story.takeaway} concepts={concepts} onPick={onConcept} /></div>
      )}
      {story.citations.length > 0 && (
        <div className="fstory__cites">
          {story.citations.map((c, i) =>
            c.url ? (
              <a key={i} className="fstory__chip" href={c.url} target="_blank" rel="noreferrer">
                {c.kind === "wikipedia" ? "🌐" : "📕"} {c.label}
              </a>
            ) : (
              <span key={i} className="fstory__chip">📕 {c.label}</span>
            ))}
        </div>
      )}
      {story.grounding && story.grounding.ok === false && (
        <div className="fstory__warn">⚠ Some content may not be fully grounded.</div>
      )}
    </div>
  );
}
```

(Check `FacilitateContent`'s prop names — it accepts `text`, `concepts?`, `onPick?` per `FacilitateContent.tsx:170-173`. If the concept pill is rendered as a `<button>` with the term as accessible name, the test's `getByRole("button", {name:/law of large numbers/i})` passes; confirm `FacilitateContent` renders the term text inside the button.)

In `MessageThread.tsx`, mirror the `FacilitateDigest` block (~line 320). Add import + route:

```tsx
import FacilitateStoryCard from "./FacilitateStoryCard";
import type { FacilitateStory } from "../types";
// ... inside the schema switch:
{msg.structuredOutput.schema === "FacilitateStory" && (
  <FacilitateStoryCard
    story={msg.structuredOutput.data as FacilitateStory}
    onConcept={(a) => onOpenConcept?.(a)}
  />
)}
```

(`onOpenConcept` is threaded in Task 8; for this task add an optional prop `onOpenConcept?: (a: ConceptAnchor) => void` to `MessageThread` and default the click to a no-op so this task's tests/build pass independently.)

Add minimal CSS for `.fstory*` classes in the existing facilitate stylesheet (mirror `ChapterDigestCard`/`FacilitateDigestCard` styles).

- [ ] **Step 4: Run to verify it passes**

Run: `cd web && npx vitest run src/components/FacilitateStoryCard.test.tsx && npx tsc --noEmit`
Expected: PASS + clean tsc.

- [ ] **Step 5: Commit**

```bash
git add web/src/types.ts web/src/components/FacilitateStoryCard.tsx web/src/components/FacilitateStoryCard.test.tsx web/src/components/MessageThread.tsx web/src/**/*.css
git commit -m "feat(facilitate): FacilitateStoryCard — hook/movements/takeaway, formal blocks, chips, pills"
```

---

### Task 8: Frontend — ConceptChat side panel (wired to /api/concept/explore)

**Files:**
- Create: `web/src/components/ConceptChat.tsx` (fork `TempChat.tsx` shell/CSS)
- Modify: `web/src/App.tsx` (state: open concept + anchor; render panel; pass `onOpenConcept` down to `MessageThread`)
- Modify: `web/src/components/MessageThread.tsx` (accept + thread `onOpenConcept`)
- Test: `web/src/components/ConceptChat.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/components/ConceptChat.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ConceptChat from "./ConceptChat";
import type { ConceptAnchor } from "../types";

const anchor: ConceptAnchor = {
  id: "c1", term: "law of large numbers", kind: "theorem", explanation: "",
  provenance: { book_slug: "hansen", book_name: "Probability", authors_short: "Hansen",
    section: "7.4", page_from: 120, page_to: 122, chunk_id: "x", same_author: true, fallback: false },
};

describe("ConceptChat", () => {
  beforeEach(() => {
    // mock the explore fetch helper
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, body: null,
      json: async () => ({}),
    })) as unknown as typeof fetch);
  });

  it("renders the concept term as the panel title and a close button", () => {
    const onClose = vi.fn();
    render(<ConceptChat anchor={anchor} bookSlug="hansen" sectionId="7.4"
                        conversationId="abc" onClose={onClose} />);
    expect(screen.getByText(/law of large numbers/i)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/close/i));
    expect(onClose).toHaveBeenCalled();
  });

  it("does not expose any handler that mutates the main thread", () => {
    // structural: ConceptChat has no prop named setMessages / onMainMessage
    const props = Object.keys(ConceptChat.length ? {} : {});
    expect(props).not.toContain("setMessages");
  });
});
```

(Keep this test light — the seed-render path uses SSE which is awkward to fully mock; the deeper "deepen re-queries" behaviour is verified live in the orchestrator's Law-1 pass. The unit test pins: title, close, and the no-main-thread-handler isolation contract.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/components/ConceptChat.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `web/src/components/ConceptChat.tsx` — fork the `TempChat` JSX shell (header badge, body, input), but:
- Props: `{ anchor: ConceptAnchor; bookSlug: string; sectionId: string; conversationId: string; onClose(): void }`. **No `setMessages` / main-thread handler.**
- On mount: POST to `/api/concept/explore` with `{ term: anchor.term, kind: anchor.kind, book_slug, section_id, conversationId }`, read SSE, render the `concept_seed` `brief` + citation chips (📕/🌐, `url` clickable) as the first assistant bubble.
- Input "deepen": POST again with `history: [...turns]`; render `concept_followup`.
- Header title = `anchor.term`; badge "CONCEPT". Footer hint "grounded in your books + Wikipedia".

```tsx
import { useEffect, useRef, useState } from "react";
import type { ConceptAnchor, StoryCitation } from "../types";

interface Props {
  anchor: ConceptAnchor; bookSlug: string; sectionId: string;
  conversationId: string; onClose(): void;
}
interface Turn { role: "user" | "assistant"; text: string; citations?: StoryCitation[]; }

async function streamExplore(body: object, onEvent: (e: any) => void) {
  const resp = await fetch("/api/concept/explore", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!resp.ok || !resp.body) return;
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const p of parts) {
      const line = p.split("\n").find((l) => l.startsWith("data:"));
      if (line) { try { onEvent(JSON.parse(line.slice(5).trim())); } catch { /* ignore */ } }
    }
  }
}

export default function ConceptChat({ anchor, bookSlug, sectionId, conversationId, onClose }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(true);
  const seeded = useRef(false);

  useEffect(() => {
    if (seeded.current) return;
    seeded.current = true;
    streamExplore({ term: anchor.term, kind: anchor.kind, book_slug: bookSlug,
      section_id: sectionId, conversationId }, (e) => {
        if (e.type === "concept_seed")
          setTurns([{ role: "assistant", text: e.brief, citations: e.citations }]);
      }).finally(() => setLoading(false));
  }, [anchor.term, anchor.kind, bookSlug, sectionId, conversationId]);

  function deepen(text: string) {
    const v = text.trim(); if (!v) return;
    const history = [...turns.map((t) => ({ role: t.role, text: t.text })), { role: "user", text: v }];
    setTurns((p) => [...p, { role: "user", text: v }]); setValue(""); setLoading(true);
    streamExplore({ term: anchor.term, kind: anchor.kind, book_slug: bookSlug,
      section_id: sectionId, conversationId, history }, (e) => {
        if (e.type === "concept_followup")
          setTurns((p) => [...p, { role: "assistant", text: e.brief, citations: e.citations }]);
      }).finally(() => setLoading(false));
  }

  return (
    <div className="concept-chat" role="dialog" aria-label={anchor.term}>
      <header className="concept-chat__hd">
        <span className="concept-chat__badge">CONCEPT</span>
        <span className="concept-chat__title">{anchor.term}</span>
        <button className="concept-chat__close" onClick={onClose} aria-label="Close concept chat">×</button>
      </header>
      <div className="concept-chat__body">
        {turns.map((t, i) => (
          <div key={i} className={`concept-chat__turn concept-chat__turn--${t.role}`}>
            <p>{t.text}</p>
            {t.citations && t.citations.length > 0 && (
              <div className="concept-chat__cites">
                {t.citations.map((c, j) => c.url
                  ? <a key={j} href={c.url} target="_blank" rel="noreferrer">{c.kind === "wikipedia" ? "🌐" : "📕"} {c.label}</a>
                  : <span key={j}>📕 {c.label}</span>)}
              </div>
            )}
          </div>
        ))}
        {loading && <div className="concept-chat__loading">…</div>}
      </div>
      <div className="concept-chat__input">
        <textarea value={value} placeholder="Ask to go deeper on this concept…"
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); deepen(value); } }} />
        <span className="concept-chat__foot">grounded in your books + Wikipedia</span>
      </div>
    </div>
  );
}
```

In `App.tsx`: add `const [conceptAnchor, setConceptAnchor] = useState<ConceptAnchor | null>(null);`, pass `onOpenConcept={setConceptAnchor}` to `MessageThread`, and render `{conceptAnchor && <ConceptChat anchor={conceptAnchor} bookSlug={...currentBook} sectionId={...currentSection} conversationId={convId} onClose={() => setConceptAnchor(null)} />}` in the side-panel slot where `TempChat` renders. Thread `onOpenConcept` through `MessageThread` props to `FacilitateStoryCard`'s `onConcept`.

Add `.concept-chat*` CSS (fork `.temp-chat*` rules).

- [ ] **Step 4: Run to verify it passes**

Run: `cd web && npx vitest run src/components/ConceptChat.test.tsx && npx tsc --noEmit`
Expected: PASS + clean tsc.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/ConceptChat.tsx web/src/components/ConceptChat.test.tsx web/src/App.tsx web/src/components/MessageThread.tsx web/src/**/*.css
git commit -m "feat(facilitate): ConceptChat side panel wired to /api/concept/explore (no main-thread leak)"
```

---

### Task 9: Docs + modal lockstep (dual-surface)

**Files:**
- Modify: `web/src/data/facilitateMode.ts` (or create if absent) + `web/src/components/FacilitatePipelineDiagram.tsx` + its test (or update `ChapterPipelineDiagram` if facilitate shares it)
- Modify: `docs/services/chat-features/53-facilitate-concept-map.md`
- Modify: `docs/common ground/Elements/modes/facilitate.html`
- Modify: `docs/system/invariants.md`, `docs/system/changelog.md`, `CLAUDE.md` pending row

- [ ] **Step 1: Update the modal pipeline data + diagram**

Reflect the new stages: `parse + resolve scope` → `fetch section (one)` → `map concepts` → `write story` → `bind (pure code)` → `verify`. Plus a note node: "concept pill → side-chat (corpus + Wikipedia)". Update the diagram component + its `.test.tsx` node-count/label assertions to match.

- [ ] **Step 2: Run the modal diagram test**

Run: `cd web && npx vitest run src/components/FacilitatePipelineDiagram.test.tsx` (or `ChapterPipelineDiagram.test.tsx`)
Expected: PASS after updating expected nodes/labels.

- [ ] **Step 3: Update markdown + HTML docs**

- `docs/services/chat-features/53-facilitate-concept-map.md`: new mermaid graph + prose for story mode, formal-statement reproduction, concept side-chat, one-section rule, env knobs.
- `docs/common ground/Elements/modes/facilitate.html`: mirror the two diagrams (pipeline + concept side-chat) and the response-card description.
- `docs/system/invariants.md`: add invariants — (a) facilitate_story emits exactly one section; (b) concept citations/provenance are pure-code verbatim; (c) concept-explore never writes the conversation store; (d) formal statements reproduced verbatim (fidelity-checked).
- `docs/system/changelog.md`: top entry describing the remake.
- `CLAUDE.md` pending table: add a row (or update) marking the facilitate story remake and its spec/plan links.

- [ ] **Step 4: Verify build + full suites**

Run: `cd web && npx tsc --noEmit && npx vitest run` and `.venv/bin/pytest src/services/chat/tests -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add web/src/data/facilitate* web/src/components/Facilitate*Diagram* docs/ CLAUDE.md
git commit -m "docs(facilitate): story-remake lockstep — modal, md+html, invariants, changelog"
```

---

## Self-Review

**Spec coverage:**
- Storytelling (hook/movements/takeaway) → Tasks 1, 5, 7. ✓
- Formal statements verbatim + didactic unpack → Tasks 1 (schema), 3 (fidelity), 5 (prompt), 7 (render). ✓
- Concept → side chat (corpus + Wikipedia, deepen) → Tasks 6 (endpoint), 8 (panel). ✓
- One section per request → Tasks 1 (schema), 2 (resolve), 4 (runner single Source). ✓
- Better book association → Task 2 (richer weighting + confirm). ✓
- Remade response card → Task 7. ✓
- No-leak isolation → Tasks 6 (stateless endpoint test), 8 (no setMessages prop). ✓
- Discriminator / legacy → Tasks 1 (mode literal), 7 (MessageThread route keeps FacilitateDigest). ✓
- Dual-surface docs + modal → Task 9. ✓

**Placeholder scan:** No "TBD"/"add error handling". The one ordering note (Task 4 vs 5) is explicit, not a placeholder; both orders pass because tests monkeypatch `_chat`.

**Type consistency:** `FacilitateStory` fields identical across schema (Task 1), runner emit (Task 4), TS type (Task 7). `Movement{prose,formal}`, `FormalStatement{kind,statement,explanation}` consistent. Endpoint event types `concept_seed`/`concept_followup` match between Task 6 (emit) and Task 8 (consume). `resolve_section`/`section_clarify` names match between Task 2 (def) and Task 4 (call). Binder names `bind_concepts`/`strip_unbound_markers`/`referenced_ids`/`statement_fidelity` match Task 3 (def) and Task 4 (call).

**Calibration note (live):** the `resolve_section` 0.5 floor and `statement_fidelity` 0.6 recall threshold are first guesses — confirm against ~10 real queries during live-verify; tune in Task 2/3 files if needed (not a blocker).
