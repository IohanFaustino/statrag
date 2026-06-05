# Formula Recovery + Global Formula Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a tutor concept's defining equation was OCR-dropped to an image, recover it (gpt-4o vision reads the figure; text re-query fallback) and feed it verbatim to the synthesizer; cache recovered equations globally for consistency and cost.

**Architecture:** A gap-triggered, best-effort formula-recovery stage in `run_orchestrator_workers` (between worker briefs and the L0 structured synth), built from three small focused modules — a pure gap detector, an async parallel recoverer, and a Qdrant-backed global cache — plus one synth-prompt line. Lightweight `asyncio.gather` (no deepagents). Degrades to today's behavior on any failure.

**Tech Stack:** Python 3.12, Qdrant (`src.core.qdrant_store`), OpenAI embeddings + gpt-4o vision, pytest. Reuses `retrieval.search_figures`, `tools.inspect_figure.inspect_figure`, `retrieval.hybrid_search`, and the `memory.py` embed/upsert/search pattern.

**Spec:** `docs/superpowers/specs/2026-06-04-formula-recovery-and-cache-design.md`

---

## File Structure

- `src/services/chat/agents/formula_gaps.py` — `GapConcept` + `detect_formula_gaps` (pure, no I/O). One responsibility: decide which concepts lack a source equation.
- `src/services/chat/agents/formula_cache.py` — `RecoveredEquation` + `cache_lookup` / `cache_write` (Qdrant collection `formula_cache`). One responsibility: persist/retrieve concept→equation. (Lowest-level module; defines `RecoveredEquation` so `formula_recovery` can import it without a cycle.)
- `src/services/chat/agents/formula_recovery.py` — `recover_formulas` + `format_recovered_block` (async; vision→text fallback; uses the cache). One responsibility: produce verbatim equations for gaps.
- `src/services/chat/agents/orchestrator_workers.py` — wire the stage into the synth `user` message (modify).
- `src/services/chat/prompts/deep_tutor.py` — one `<recovered_equations>` rule (modify).
- Tests: `src/services/chat/tests/test_formula_gaps.py`, `test_formula_cache.py`, `test_formula_recovery.py`, and additions to `test_orchestrator_workers.py` + `test_tutor_prompt_contract.py`.

Import graph (no cycles): `formula_recovery` → `formula_cache` (`RecoveredEquation`, cache fns) and `formula_gaps` (`GapConcept`); `orchestrator_workers` → `formula_gaps` + `formula_recovery`.

---

## Task 1: `formula_gaps.py` — pure gap detector

**Files:**
- Create: `src/services/chat/agents/formula_gaps.py`
- Test: `src/services/chat/tests/test_formula_gaps.py`

- [ ] **Step 1: Write failing tests**

Create `src/services/chat/tests/test_formula_gaps.py`:
```python
from src.services.chat.agents.formula_gaps import detect_formula_gaps, GapConcept


def _src(chunk, book="murphy", section="4.7"):
    from src.services.chat.schemas import Source
    return Source(rank=1, book=book, chapter="ch04", section=section, title="t",
                  excerpt=chunk[:120], chunkId="c1", chunk=chunk, score=0.9)


def test_gap_when_definition_has_image_placeholder_and_no_latex():
    chunk = ("The bias of an estimator is defined as\n\n"
             "![art](markdown/media/Art_P760.jpg)\n\n"
             "where theta* is the true parameter value.")
    gaps = detect_formula_gaps([_src(chunk)], "bias variance tradeoff")
    assert len(gaps) == 1
    assert "bias" in gaps[0].term.lower()
    assert gaps[0].book_slugs == ["murphy"]


def test_no_gap_when_latex_present_near_definition():
    chunk = ("The estimator is unbiased if and only if $E(\\widehat{\\mu}) = \\mu$ "
             "which is the defining condition.")
    gaps = detect_formula_gaps([_src(chunk, book="baltagi")], "bias")
    assert gaps == []


def test_dedupe_same_term_across_chunks():
    chunk = ("Bias of an estimator is defined as\n![art](a.jpg)\nwhere x.")
    gaps = detect_formula_gaps([_src(chunk), _src(chunk, book="islp")], "bias")
    assert len(gaps) == 1
    assert set(gaps[0].book_slugs) == {"murphy", "islp"}


def test_cap_at_four_gaps():
    srcs = []
    for i, term in enumerate(["bias", "variance", "mse", "consistency", "efficiency"]):
        c = f"The {term} of an estimator is defined as\n![art](x{i}.jpg)\nwhere y."
        srcs.append(_src(c, book=f"b{i}", section=str(i)))
    gaps = detect_formula_gaps(srcs, "estimator properties")
    assert len(gaps) <= 4
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_formula_gaps.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/services/chat/agents/formula_gaps.py`:
```python
"""Pure detector for concepts whose defining equation is missing from the
retrieved sources because it was OCR-dropped to an image placeholder.

No I/O, no LLM — deterministic, unit-testable on fixture chunks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.services.chat.schemas import Source

# A definitional span: a definiendum followed by "is/are defined as|to be" or
# the textbook heading form "<Term> of an estimator".
_DEF_RE = re.compile(
    r"(?P<term>[A-Z][A-Za-z][A-Za-z \-]{1,40}?)\s+"
    r"(?:of an estimator|is defined as|are defined as|is defined to be|of the estimator)",
    re.IGNORECASE,
)
_LATEX_RE = re.compile(r"\$\$?[^$]*[=][^$]*\$\$?")
_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_WINDOW = 220  # chars around the definition span to look for latex / image
_MAX_GAPS = 4


@dataclass
class GapConcept:
    term: str
    hint: str
    book_slugs: list[str] = field(default_factory=list)


def _norm(term: str) -> str:
    return re.sub(r"\s+", " ", term).strip().lower()


def detect_formula_gaps(sources: list[Source], query: str) -> list[GapConcept]:
    """Return concepts whose defining equation is absent as LaTeX but whose
    definition sits next to a dropped image placeholder (formula lost to OCR)."""
    by_term: dict[str, GapConcept] = {}
    for s in sources:
        text = s.chunk or s.excerpt or ""
        for m in _DEF_RE.finditer(text):
            term = m.group("term").strip()
            lo = max(0, m.start() - _WINDOW)
            hi = min(len(text), m.end() + _WINDOW)
            window = text[lo:hi]
            has_latex = bool(_LATEX_RE.search(window))
            has_img = bool(_IMG_RE.search(window))
            if has_latex or not has_img:
                continue  # equation present, or no evidence it was dropped
            key = _norm(term)
            book = getattr(s, "book", "") or ""
            if key in by_term:
                if book and book not in by_term[key].book_slugs:
                    by_term[key].book_slugs.append(book)
            else:
                by_term[key] = GapConcept(term=term, hint=window.strip(),
                                          book_slugs=[book] if book else [])
    return list(by_term.values())[:_MAX_GAPS]
```

- [ ] **Step 4: Run, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_formula_gaps.py -v`
Expected: PASS (4 tests). If `Source` requires extra required fields, read `src/services/chat/schemas/_core.py` `class Source` and add them to `_src` in the test.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/formula_gaps.py src/services/chat/tests/test_formula_gaps.py
git commit -m "feat(formula): pure gap detector for OCR-dropped defining equations"
```

---

## Task 2: `formula_cache.py` — global concept→equation cache

**Files:**
- Create: `src/services/chat/agents/formula_cache.py`
- Test: `src/services/chat/tests/test_formula_cache.py`

- [ ] **Step 1: Write failing tests**

Create `src/services/chat/tests/test_formula_cache.py`:
```python
import asyncio
import src.services.chat.agents.formula_cache as fc
from src.services.chat.agents.formula_cache import RecoveredEquation


class _Pt:
    def __init__(self, score, payload): self.score = score; self.payload = payload


def test_lookup_returns_hit_above_threshold(monkeypatch):
    monkeypatch.setattr(fc, "_embed", _fake_embed)
    monkeypatch.setattr(fc, "_collection_exists", lambda name: True)
    class _Res:
        points = [_Pt(0.97, {"term": "bias", "latex": "$E[\\hat\\theta]-\\theta$", "citation": "Murphy"})]
    monkeypatch.setattr(fc, "_query", lambda name, emb, limit: _Res())
    out = asyncio.run(fc.cache_lookup("bias of an estimator"))
    assert out is not None and out.latex == "$E[\\hat\\theta]-\\theta$"


def test_lookup_miss_below_threshold(monkeypatch):
    monkeypatch.setattr(fc, "_embed", _fake_embed)
    monkeypatch.setattr(fc, "_collection_exists", lambda name: True)
    class _Res:
        points = [_Pt(0.50, {"term": "bias", "latex": "$x$", "citation": "c"})]
    monkeypatch.setattr(fc, "_query", lambda name, emb, limit: _Res())
    assert asyncio.run(fc.cache_lookup("bias")) is None


def test_lookup_miss_when_collection_absent(monkeypatch):
    monkeypatch.setattr(fc, "_collection_exists", lambda name: False)
    assert asyncio.run(fc.cache_lookup("bias")) is None


def test_write_is_best_effort_on_error(monkeypatch):
    monkeypatch.setattr(fc, "_embed", _fake_embed)
    def boom(*a, **k): raise RuntimeError("qdrant down")
    monkeypatch.setattr(fc, "_upsert", boom)
    # must not raise
    asyncio.run(fc.cache_write("bias", "$x$", "Murphy"))


async def _fake_embed(text): return [0.1] * 8
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_formula_cache.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement** (mirrors `src/services/chat/memory.py` embed/upsert/search)

Create `src/services/chat/agents/formula_cache.py`:
```python
"""Global concept→defining-equation cache (Qdrant collection ``formula_cache``).

Once a concept's verbatim equation is recovered, store it so later queries
reuse the SAME equation (consistency) without re-running vision (cost).
Best-effort: any failure degrades to a cache miss / no-op.
"""
from __future__ import annotations

import logging
import re
import uuid

import openai as _openai
from pydantic import BaseModel

from src.core.config import settings
from src.core.qdrant_store import TEXT_VECTOR, client, ensure_text_collection

logger = logging.getLogger(__name__)

COLLECTION = "formula_cache"
_NS = uuid.UUID("00000000-0000-0000-0000-0000000fca1e")  # stable namespace for ids


class RecoveredEquation(BaseModel):
    term: str
    latex: str
    citation: str = ""


def _norm(term: str) -> str:
    return re.sub(r"\s+", " ", term).strip().lower()


async def _embed(text: str) -> list[float]:
    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    return (await oa.embeddings.create(model=settings.embedding_model, input=text[:8000])).data[0].embedding


def _collection_exists(name: str) -> bool:
    try:
        return name in {c.name for c in client().get_collections().collections}
    except Exception:  # noqa: BLE001
        return False


def _query(name, emb, limit):
    return client().query_points(collection_name=name, query=emb, using=TEXT_VECTOR,
                                 limit=limit, with_payload=True)


def _upsert(name, point_id, emb, payload):
    from qdrant_client.models import PointStruct  # noqa: PLC0415
    ensure_text_collection(name)
    client().upsert(collection_name=name,
                    points=[PointStruct(id=point_id, vector={TEXT_VECTOR: emb}, payload=payload)])


async def cache_lookup(term: str, *, threshold: float = 0.93) -> RecoveredEquation | None:
    """Semantic-lookup a recovered equation for *term*; None on miss/error."""
    try:
        if not _collection_exists(COLLECTION):
            return None
        emb = await _embed(_norm(term))
        res = _query(COLLECTION, emb, 1)
        pts = getattr(res, "points", [])
        if not pts or (pts[0].score or 0.0) < threshold:
            return None
        pl = pts[0].payload or {}
        if not pl.get("latex"):
            return None
        return RecoveredEquation(term=pl.get("term", term), latex=pl["latex"], citation=pl.get("citation", ""))
    except Exception:  # noqa: BLE001
        logger.exception("formula cache lookup failed for %s", term)
        return None


async def cache_write(term: str, latex: str, citation: str) -> None:
    """Best-effort upsert; overwrites by stable id (normalized term)."""
    if not latex:
        return
    try:
        emb = await _embed(_norm(term))
        pid = str(uuid.uuid5(_NS, _norm(term)))
        _upsert(COLLECTION, pid, emb, {"term": term, "latex": latex, "citation": citation})
    except Exception:  # noqa: BLE001
        logger.exception("formula cache write failed for %s", term)
```

- [ ] **Step 4: Run, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_formula_cache.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/formula_cache.py src/services/chat/tests/test_formula_cache.py
git commit -m "feat(formula): global formula_cache Qdrant collection (lookup/write, best-effort)"
```

---

## Task 3: `formula_recovery.py` — async parallel recoverer

**Files:**
- Create: `src/services/chat/agents/formula_recovery.py`
- Test: `src/services/chat/tests/test_formula_recovery.py`

- [ ] **Step 1: Write failing tests**

Create `src/services/chat/tests/test_formula_recovery.py`:
```python
import asyncio
import src.services.chat.agents.formula_recovery as fr
from src.services.chat.agents.formula_gaps import GapConcept
from src.services.chat.agents.formula_cache import RecoveredEquation


def _gap(term="bias", books=("murphy",)):
    return GapConcept(term=term, hint="bias is defined as", book_slugs=list(books))


def test_cache_hit_short_circuits_vision(monkeypatch):
    async def hit(term, **k): return RecoveredEquation(term="bias", latex="$cached$", citation="C")
    monkeypatch.setattr(fr, "cache_lookup", hit)
    called = {"vision": False}
    def figs(*a, **k): called["vision"] = True; return []
    monkeypatch.setattr(fr, "search_figures", figs)
    out = asyncio.run(fr.recover_formulas("q", [_gap()]))
    assert out and out[0].latex == "$cached$" and called["vision"] is False


def test_vision_path_extracts_latex(monkeypatch):
    async def miss(term, **k): return None
    monkeypatch.setattr(fr, "cache_lookup", miss)
    async def noop_write(*a, **k): return None
    monkeypatch.setattr(fr, "cache_write", noop_write)
    class _Fig: chart="http://x/a.jpg"; caption="Bias"; book="murphy"; chapter="ch04"; ref="r"
    monkeypatch.setattr(fr, "search_figures", lambda *a, **k: [_Fig()])
    async def vis(fig, *, query): return "The equation is $\\text{Bias}=E[\\hat\\theta]-\\theta$ shown above."
    monkeypatch.setattr(fr, "inspect_figure", vis)
    out = asyncio.run(fr.recover_formulas("q", [_gap()]))
    assert out and out[0].latex == "$\\text{Bias}=E[\\hat\\theta]-\\theta$"


def test_text_fallback_when_no_figure(monkeypatch):
    async def miss(term, **k): return None
    monkeypatch.setattr(fr, "cache_lookup", miss)
    async def noop_write(*a, **k): return None
    monkeypatch.setattr(fr, "cache_write", noop_write)
    monkeypatch.setattr(fr, "search_figures", lambda *a, **k: [])
    class _S: chunk = "bias is defined as $E[\\hat\\theta]-\\theta$ in the text"
    monkeypatch.setattr(fr, "hybrid_search", lambda *a, **k: ([_S()], {}))
    out = asyncio.run(fr.recover_formulas("q", [_gap()]))
    assert out and "E[\\hat\\theta]" in out[0].latex


def test_total_miss_yields_no_equation(monkeypatch):
    async def miss(term, **k): return None
    monkeypatch.setattr(fr, "cache_lookup", miss)
    monkeypatch.setattr(fr, "search_figures", lambda *a, **k: [])
    monkeypatch.setattr(fr, "hybrid_search", lambda *a, **k: ([], {}))
    out = asyncio.run(fr.recover_formulas("q", [_gap()]))
    assert out == []


def test_format_recovered_block():
    block = fr.format_recovered_block([RecoveredEquation(term="Bias", latex="$b$", citation="Murphy")])
    assert "<recovered_equations>" in block and "$b$" in block and "Bias" in block
    assert fr.format_recovered_block([]) == ""
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_formula_recovery.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/services/chat/agents/formula_recovery.py`:
```python
"""Recover OCR-dropped defining equations for gap concepts.

Per gap, in parallel: cache → vision-on-figure (search_figures + inspect_figure)
→ formula-scoped text re-query. Best-effort; returns only equations found.
"""
from __future__ import annotations

import asyncio
import logging
import re

from src.services.chat.agents.formula_cache import RecoveredEquation, cache_lookup, cache_write
from src.services.chat.agents.formula_gaps import GapConcept
from src.services.chat.retrieval import hybrid_search, search_figures
from src.services.chat.tools.inspect_figure import inspect_figure

logger = logging.getLogger(__name__)

_LATEX_RE = re.compile(r"\$\$?[^$]+?\$\$?")


def _first_latex(text: str) -> str | None:
    m = _LATEX_RE.search(text or "")
    return m.group(0) if m else None


def _cite(fig) -> str:
    book = getattr(fig, "book", "") or ""
    chap = getattr(fig, "chapter", "") or ""
    return f"{book} {chap}".strip()


async def _recover_one(query: str, gap: GapConcept) -> RecoveredEquation | None:
    # 1. cache
    try:
        hit = await cache_lookup(gap.term)
        if hit:
            return hit
    except Exception:  # noqa: BLE001
        logger.exception("cache_lookup raised for %s", gap.term)
    # 2. vision on figure
    try:
        figs = search_figures(f"{gap.term} definition formula equation",
                              book_slugs=gap.book_slugs or None, k=2)
        for fig in figs:
            txt = await inspect_figure(
                fig, query=(f"Transcribe the exact defining equation for '{gap.term}' "
                            f"shown in this figure as LaTeX, delimited with $...$ or $$...$$. "
                            f"Output ONLY the equation."))
            latex = _first_latex(txt)
            if latex:
                eq = RecoveredEquation(term=gap.term, latex=latex, citation=_cite(fig))
                await cache_write(eq.term, eq.latex, eq.citation)
                return eq
    except Exception:  # noqa: BLE001
        logger.exception("vision recovery failed for %s", gap.term)
    # 3. text re-query fallback
    try:
        srcs, _ = hybrid_search(f"{gap.term} is defined as the formula",
                                book_slugs=gap.book_slugs or None, top_k=3, rerank=False)
        for s in srcs:
            chunk = getattr(s, "chunk", "") or ""
            if gap.term.split()[0].lower() in chunk.lower():
                latex = _first_latex(chunk)
                if latex:
                    cite = f"{getattr(s,'book','')} {getattr(s,'chapter','')}".strip()
                    eq = RecoveredEquation(term=gap.term, latex=latex, citation=cite)
                    await cache_write(eq.term, eq.latex, eq.citation)
                    return eq
    except Exception:  # noqa: BLE001
        logger.exception("text fallback failed for %s", gap.term)
    return None


async def recover_formulas(query: str, gaps: list[GapConcept]) -> list[RecoveredEquation]:
    """Recover an equation per gap, in parallel. Returns only those found."""
    if not gaps:
        return []
    results = await asyncio.gather(*(_recover_one(query, g) for g in gaps), return_exceptions=True)
    return [r for r in results if isinstance(r, RecoveredEquation)]


def format_recovered_block(eqs: list[RecoveredEquation]) -> str:
    """Render the recovered equations for the synth prompt. Empty → ''."""
    if not eqs:
        return ""
    lines = ["<recovered_equations>"]
    for e in eqs:
        cite = f" [{e.citation}]" if e.citation else ""
        lines.append(f"- {e.term}: {e.latex}{cite}")
    lines.append("</recovered_equations>")
    return "\n".join(lines)
```

- [ ] **Step 4: Run, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_formula_recovery.py -v`
Expected: PASS (5 tests). If `search_figures`/`hybrid_search` import names differ, read `src/services/chat/retrieval.py` and adjust the imports (they are module-level functions there).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/formula_recovery.py src/services/chat/tests/test_formula_recovery.py
git commit -m "feat(formula): async parallel recoverer (cache→vision→text fallback)"
```

---

## Task 4: Wire into the synth + prompt rule

**Files:**
- Modify: `src/services/chat/agents/orchestrator_workers.py`
- Modify: `src/services/chat/prompts/deep_tutor.py`
- Test: `src/services/chat/tests/test_orchestrator_workers.py`, `src/services/chat/tests/test_tutor_prompt_contract.py`

- [ ] **Step 1: Write failing tests**

Add to `src/services/chat/tests/test_tutor_prompt_contract.py`:
```python
def test_recovered_equations_rule_present():
    assert "<recovered_equations>" in INSTR or "recovered_equations" in INSTR
    assert "verbatim" in INSTR
```

Add to `src/services/chat/tests/test_orchestrator_workers.py`:
```python
def test_recovered_equations_injected_into_synth(monkeypatch):
    sources, plan = _two_author_inputs()
    async def fake_worker(query, thesis, author, srcs, *, model=None):
        from src.services.chat.schemas.output import AuthorBrief
        return AuthorBrief(author=author, summary="s", key_points=["k"], source_ranks=[srcs[0].rank])
    monkeypatch.setattr(OW, "run_author_worker", fake_worker)
    # force a gap + a recovered equation
    from src.services.chat.agents.formula_gaps import GapConcept
    from src.services.chat.agents.formula_cache import RecoveredEquation
    monkeypatch.setattr(OW, "detect_formula_gaps", lambda sources, query: [GapConcept(term="Bias", hint="h", book_slugs=["murphy"])])
    async def fake_recover(query, gaps): return [RecoveredEquation(term="Bias", latex="$E[\\hat\\theta]-\\theta$", citation="Murphy")]
    monkeypatch.setattr(OW, "recover_formulas", fake_recover)
    captured = {}
    from src.services.chat.schemas.output import DeepTutorAnswer
    async def fake_stream(messages, model, on_aspect_delta=None):
        captured["messages"] = messages
        return DeepTutorAnswer(tldr="t", definition="d", formal_statement="",
                               example_intuition="", applications="", further_reading=""), {}
    monkeypatch.setattr(OW, "_stream_structured", fake_stream)
    asyncio.run(OW.run_orchestrator_workers("q", sources, plan))
    user_msg = next(m["content"] for m in captured["messages"] if m["role"] == "user")
    assert "<recovered_equations>" in user_msg and "$E[\\hat\\theta]-\\theta$" in user_msg
```

- [ ] **Step 2: Run, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_orchestrator_workers.py::test_recovered_equations_injected_into_synth src/services/chat/tests/test_tutor_prompt_contract.py::test_recovered_equations_rule_present -v`
Expected: FAIL.

- [ ] **Step 3: Add the prompt rule**

In `src/services/chat/prompts/deep_tutor.py`, inside the `<structure>` or `<math_format>` area of `DEEP_TUTOR_INSTRUCTIONS` (near the existing "defining formula" rule), add:
```
- If the user message contains a ``<recovered_equations>`` block, use each
  listed LaTeX VERBATIM as that concept's defining equation in its ``### ``
  subsection, and cite the provided source. These were recovered from a figure
  the main text dropped; prefer them over reconstruction.
```
(Keep wording so `recovered_equations` and `verbatim` are lowercase-matchable; do not break other contract tests or the token-budget test.)

- [ ] **Step 4: Wire the stage into `run_orchestrator_workers`**

In `src/services/chat/agents/orchestrator_workers.py`:
1. Add imports near the top:
```python
from src.services.chat.agents.formula_gaps import detect_formula_gaps
from src.services.chat.agents.formula_recovery import recover_formulas, format_recovered_block
```
2. In `run_orchestrator_workers`, just BEFORE the L0 synth `user = (...)` string is built (after the `if level == 5:` block, where `plan_block = _format_plan_block(plan)` is), insert:
```python
    # Formula recovery: when a concept's defining equation was OCR-dropped to an
    # image, recover it (vision/text) so the synth states it verbatim. Best-effort.
    recovered_block = ""
    try:
        gaps = detect_formula_gaps(sources, query)
        if gaps:
            recovered = await recover_formulas(query, gaps)
            recovered_block = format_recovered_block(recovered)
    except Exception:  # noqa: BLE001
        logger.exception("formula recovery stage failed; continuing without it")
```
3. In the `user = (...)` construction for the L0 synth, add the block right after the source bundle line:
```python
        f"{format_source_bundle(sources)}\n\n"
        f"{(recovered_block + chr(10) + chr(10)) if recovered_block else ''}"
```
(Read the existing `user = (...)` to place it cleanly; keep the rest unchanged.)

- [ ] **Step 5: Run, verify PASS + no regressions**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_orchestrator_workers.py src/services/chat/tests/test_tutor_prompt_contract.py -q`
Expected: all pass. Watch `test_deep_tutor_instructions_within_token_budget` — tighten the new rule if over budget.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/agents/orchestrator_workers.py src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_orchestrator_workers.py src/services/chat/tests/test_tutor_prompt_contract.py
git commit -m "feat(ow): wire formula-recovery stage + <recovered_equations> verbatim synth rule"
```

---

## Task 5: Full suite, docs lockstep, manual verify

**Files:**
- Modify: `docs/system/changelog.md`, `docs/services/chat-features/56-deep-synthesis-l3b.md`

- [ ] **Step 1: Full suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: all green (3 groq SKIP). Fix any regression before proceeding.

- [ ] **Step 2: Docs lockstep**

- `docs/system/changelog.md`: prepend `### 2026-06-0X — Formula recovery (vision second-RAG) + global cache` — what it does (gap-triggered vision recovery of OCR-dropped equations, `<recovered_equations>` verbatim into synth, `formula_cache` global collection), best-effort, lightweight async (no deepagents).
- `docs/services/chat-features/56-deep-synthesis-l3b.md`: add a "Formula recovery stage" section describing the detect→recover→cache flow + the three new modules.

- [ ] **Step 3: Commit docs**

```bash
git add docs/system/changelog.md docs/services/chat-features/56-deep-synthesis-l3b.md
git commit -m "docs(formula): document formula-recovery stage + global cache"
```

- [ ] **Step 4: Manual verify (live)**

With `./scripts/dev.sh` running, ask the bias-variance question via `tutorWorkflow="orchestrator-deep"`. Confirm: (a) a recovered verbatim equation appears in the `### Bias`/`### Variance` subsection with a citation; (b) re-ask the identical question — the second run is served from `formula_cache` (same equation, no vision call — check logs for the absence of "vision recovery" and presence of a cache hit). Note the result. (No commit — verification.)

---

## Self-Review

- **Spec coverage:** detector → Task 1; cache → Task 2; recoverer (cache→vision→text) → Task 3; synth wiring + prompt rule → Task 4; suite/docs/manual → Task 5. All spec components covered.
- **Placeholders:** none — every module/test/command is concrete. The one heuristic (`_DEF_RE`) is given as real regex; execution may need to widen it for more concept names (noted in Task 1 Step 4 as a read-and-adjust if `Source` fields differ).
- **Type/name consistency:** `GapConcept{term,hint,book_slugs}`, `RecoveredEquation{term,latex,citation}`, `detect_formula_gaps`, `recover_formulas`, `format_recovered_block`, `cache_lookup`, `cache_write` are used identically across Tasks 1-4 and the tests. Import graph is acyclic (`formula_recovery`→`formula_cache`+`formula_gaps`; `orchestrator_workers`→both). `_stream_structured(messages, model, on_aspect_delta=None)` signature matches the one used by existing OW tests. Monkeypatch targets (`OW.detect_formula_gaps`, `OW.recover_formulas`, `OW._stream_structured`, `fr.cache_lookup`, `fr.search_figures`, `fr.inspect_figure`, `fr.hybrid_search`, `fc._embed/_query/_upsert/_collection_exists`) are the module-level names the implementations reference.
