# Tutor Narrative Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the tutor mode's 7 synthesis variants to ONE single-pass narrative synthesizer whose 5 body beats (intro excluded) are threaded by woven prose transitions, enforced by a pure-code seam validator with one bounded redraft.

**Architecture:** Keep the retrieval front untouched. Delete orchestrator-workers / deepagents / `organize` / harness levels and the `tutorWorkflow` request knob; `_draft_coro` collapses to a single `_stream_draft` call. Rewire formula recovery onto that call. A new pure-code `agents/seams.py` validates narrative continuity over the present beats; on failure the draft is silently re-rolled once (non-streamed) and the outcome recorded in the existing `quality` dict. Storytelling lives in the prompt + per-beat `Field` descriptions; the `tldr` intro stays outside the thread.

**Tech Stack:** Python 3.12 (FastAPI/pydantic/openai/asyncio), pytest; React+Vite+TS frontend (vitest); Qdrant. Interpreter: `.venv/bin/python`. Frontend: `cd web && npm`.

**Spec:** `docs/superpowers/specs/2026-06-11-tutor-narrative-rebuild-design.md` (read it first).

**Key anchors (verified 2026-06-11):**
- `src/services/chat/agents/deep_tutor.py`: `_WORKFLOW_DEFAULT` :1026, `_resolve_workflow` :1036, `_stream_draft` :1857, `_build_organize_pool` :1896, `_draft_coro` :2668, draft drain loop :2712-2722, assemble/quality region :2748-2780.
- `src/services/chat/schemas/_core.py`: `tutorWorkflow` field :144.
- `src/services/chat/schemas/output.py`: `DeepTutorAnswer` field descriptions :163-196, `quality` on `TutorAnswer` :109.
- Files to delete: `agents/orchestrator_workers.py`, `agents/ow_deepagents.py`, `agents/ow_harness.py`, `agents/ow_skills/`, `eval/ow_harness_compare.py`, `eval/ow_deepagents_compare.py`, `eval/structured_synth_compare.py`, `tests/test_orchestrator_workers.py`, `tests/test_ow_harness.py`.
- Formula recovery (KEEP, rewire): `agents/formula_gaps.py` `detect_formula_gaps`, `agents/formula_recovery.py` `recover_formulas`/`format_recovered_block` — today called at `orchestrator_workers.py:283-285`.
- Frontend refs to scrub: `web/src/App.tsx`, `web/src/components/modals/AboutModelModal.tsx`, `web/src/components/PipelineDiagram.tsx` (+ `.test.tsx`), `web/src/data/tutorPipeline.ts`, `web/src/api/sse.ts`, `web/src/state/chat.ts`.

**Gates each task must leave green:**
- Backend: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
- Lint/type: `.venv/bin/ruff check src/services/chat/` and `.venv/bin/mypy src/services/chat/agents/seams.py` (new module)
- Frontend (tasks 6+): `cd web && npm test -- --run` and `npx tsc --noEmit`

---

## Task 1: Deletion sweep + formula-recovery rewire

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py` (`_draft_coro` :2668-2710, `_resolve_workflow` :1036, env consts :1026-1031, imports :56)
- Modify: `src/services/chat/schemas/_core.py:144` (delete `tutorWorkflow`)
- Delete: `agents/orchestrator_workers.py`, `agents/ow_deepagents.py`, `agents/ow_harness.py`, `agents/ow_skills/`, `eval/ow_harness_compare.py`, `eval/ow_deepagents_compare.py`, `eval/structured_synth_compare.py`, `tests/test_orchestrator_workers.py`, `tests/test_ow_harness.py`
- Modify: `src/services/chat/tests/test_tutor_prompt_contract.py` (drop ow_harness refs)
- Test: `src/services/chat/tests/test_tutor_narrative_collapse.py` (new)

- [ ] **Step 1: Write the failing test** — `test_tutor_narrative_collapse.py`

```python
"""The synthesis tail is collapsed: no workflow knob, no OW/organize modules."""
import importlib
import pytest


def test_tutorworkflow_field_removed():
    from src.services.chat.schemas._core import ChatRequest
    assert "tutorWorkflow" not in ChatRequest.model_fields


def test_orchestrator_and_harness_modules_gone():
    for mod in (
        "src.services.chat.agents.orchestrator_workers",
        "src.services.chat.agents.ow_deepagents",
        "src.services.chat.agents.ow_harness",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(mod)


def test_deep_tutor_has_no_workflow_resolver():
    import src.services.chat.agents.deep_tutor as dt
    assert not hasattr(dt, "_resolve_workflow")
    assert not hasattr(dt, "_build_organize_pool")
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_narrative_collapse.py -q`
Expected: FAIL (`tutorWorkflow` still present; modules still import).

- [ ] **Step 3: Delete modules + tests + eval drivers**

```bash
git rm src/services/chat/agents/orchestrator_workers.py \
       src/services/chat/agents/ow_deepagents.py \
       src/services/chat/agents/ow_harness.py \
       src/services/chat/eval/ow_harness_compare.py \
       src/services/chat/eval/ow_deepagents_compare.py \
       src/services/chat/eval/structured_synth_compare.py \
       src/services/chat/tests/test_orchestrator_workers.py \
       src/services/chat/tests/test_ow_harness.py
git rm -r src/services/chat/agents/ow_skills
```

- [ ] **Step 4: Collapse `_draft_coro` + remove resolver/organize**

In `deep_tutor.py`:
1. Delete `_resolve_workflow` (:1036) and `_build_organize_pool` (:1896) and the env consts `_WORKFLOW_DEFAULT`, `_ORGANIZE_MODEL`, `_ORGANIZE_MAX_TOKENS`, `_WORKER_MODEL` (:1026-1031) — grep each name first and remove all remaining references.
2. Remove the `ORGANIZER_PREAMBLE` import (:56) and any `m_synth`/`_WORKER_MODEL` plumbing only used by the deleted branches.
3. Replace the whole `_draft_coro` body (:2668-2710) with the single-draft call. Keep formula recovery (Step 5) — final shape:

```python
    async def _draft_coro():
        recovered_block = await _recover_equations_block(query, sources)
        return await _stream_draft(
            query, sources, figures=approved_figures,
            on_aspect_delta=_emit_aspect_delta, model=m_draft, plan=plan,
            recovered_block=recovered_block,
        )
```

- [ ] **Step 5: Rewire formula recovery onto the single draft**

Read `formula_recovery.py` (`recover_formulas`, `format_recovered_block`) and `formula_gaps.py` (`detect_formula_gaps`) signatures, and `_stream_draft` (:1857) to see how `instructions`/prompt context is assembled. Add a helper in `deep_tutor.py` near the other draft helpers:

```python
async def _recover_equations_block(query: str, sources: list) -> str:
    """Gap-triggered formula recovery (was wired inside orchestrator-workers).
    Returns a ``<recovered_equations>…</recovered_equations>`` block to inject
    verbatim into the draft prompt, or '' when no gaps / recovery yields nothing.
    Best-effort: never raises."""
    try:
        from src.services.chat.agents.formula_gaps import detect_formula_gaps
        from src.services.chat.agents.formula_recovery import (
            recover_formulas, format_recovered_block,
        )
        gaps = detect_formula_gaps(sources, query)
        if not gaps:
            return ""
        recovered = await recover_formulas(query, gaps)
        return format_recovered_block(recovered) if recovered else ""
    except Exception:  # noqa: BLE001
        logger.exception("formula recovery failed; continuing without it")
        return ""
```

Thread a new optional `recovered_block: str = ""` param through `_stream_draft` so the block is appended to the draft's source/context section (verbatim) — follow how the existing `instructions`/source bundle is concatenated. Add no env flag.

- [ ] **Step 6: Delete `tutorWorkflow` request field**

In `_core.py` remove the field + its docstring comment block (:139-144). Grep `tutorWorkflow` across `src/services/chat/` and remove every remaining backend reference (router, modes, tests). Fix `test_tutor_prompt_contract.py` to drop any `ow_harness`/`tutorWorkflow` assertions.

- [ ] **Step 7: Run gates**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q && .venv/bin/ruff check src/services/chat/`
Expected: PASS. New collapse test green; no import errors; no lingering `tutorWorkflow`/`ow_harness` references (`grep -rn "tutorWorkflow\|ow_harness\|run_orchestrator_workers" src/services/chat/` returns nothing).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(tutor): collapse 7 synthesis variants to single draft; rewire formula recovery"
```

---

## Task 2: Seam module (pure code, zero LLM)

**Files:**
- Create: `src/services/chat/agents/seams.py`
- Test: `src/services/chat/tests/test_seams.py`

The narrative beats, in order, by aspect key (intro excluded):
`["definition", "formal_statement", "example_intuition", "applications", "further_reading"]`.
A beat is "present" when its aspect string is non-empty after strip. `formal_statement` may be empty → dropped from the chain (the ②→③ seam becomes ①→③ automatically because we iterate over present beats only).

- [ ] **Step 1: Write the failing test** — `test_seams.py`

```python
from src.services.chat.agents.seams import check_seams, BEAT_ORDER


def _beats(**kw):
    base = {k: "" for k in BEAT_ORDER}
    base.update(kw)
    return base


def test_connected_beats_pass():
    beats = _beats(
        definition="Test MSE decomposes into bias, variance and noise. This decomposition is the key lever.",
        example_intuition="That decomposition plays out on a polynomial fit. A degree-1 model underfits, lifting bias.",
        applications="The same bias lever governs random forests. Tree depth trades variance for bias in practice.",
        further_reading="Beyond forests, the bias question opens active research. See ESL chapter 7.",
    )
    res = check_seams(beats, thesis="bias and variance trade off to shape test error")
    assert res.passed is True
    assert res.scores["seam_continuity"] == 1.0


def test_disconnected_beat_fails_and_names_seam():
    beats = _beats(
        definition="Test MSE decomposes into bias, variance and noise.",
        example_intuition="Photosynthesis converts sunlight into chemical energy in chloroplasts.",
        applications="The bias lever governs random forests too.",
    )
    res = check_seams(beats, thesis="bias variance tradeoff")
    assert res.passed is False
    assert any("example_intuition" in f for f in res.failing_seams)
    assert res.scores["seam_continuity"] < 1.0


def test_thesis_rescues_a_pivot():
    # second beat shares nothing with the first beat's last sentence,
    # but shares a lemma with the thesis -> seam holds.
    beats = _beats(
        definition="A model's error has three additive parts.",
        example_intuition="Variance shows up clearly when we refit on resampled data.",
    )
    res = check_seams(beats, thesis="variance drives instability across resamples")
    assert res.passed is True


def test_formalize_drop_relinks_definition_to_example():
    # formal_statement empty -> chain is definition -> example_intuition.
    beats = _beats(
        definition="Bias measures how far the average prediction sits from truth.",
        formal_statement="",
        example_intuition="That same bias is visible when a linear fit misses a curved trend.",
        applications="Bias also explains underfitting in shallow trees.",
    )
    res = check_seams(beats, thesis="bias")
    assert res.passed is True


def test_polish_language_drift_flagged():
    beats = _beats(
        definition="Bias mierzy odchylenie predykcji od prawdy w modelu statystycznym.",
        example_intuition="To samo zjawisko widać przy dopasowaniu liniowym do krzywej.",
    )
    res = check_seams(beats, thesis="bias")
    assert res.scores["lang_ok"] == 0.0


def test_boilerplate_openers_flagged():
    beats = _beats(
        definition="Bias is the systematic error of a model. Now that we understand bias, more follows.",
        example_intuition="Now that we understand bias, consider a linear fit to curved data.",
        applications="Now that we understand bias, trees underfit when shallow.",
    )
    res = check_seams(beats, thesis="bias")
    # >=2 beats opening with same 3-gram "now that we" -> boilerplate failure
    assert res.passed is False
    assert any("boilerplate" in f.lower() for f in res.failing_seams)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_seams.py -q`
Expected: FAIL (`No module named ...seams`).

- [ ] **Step 3: Implement `seams.py`**

```python
"""Pure-code narrative-seam validator for the tutor mode.

Zero LLM. Verifies that the body beats (intro excluded) form one woven
narrative: each present beat's opening sentence connects to the previous
present beat's closing sentence OR to the plan thesis; openers are not
boilerplate; and the prose stays in English (guards the known long-run
language-drift bug). Returns scores that ride the existing
``TutorAnswer.quality`` dict.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Intro (``tldr``) is deliberately absent — the thread is defined over body beats.
BEAT_ORDER = [
    "definition",
    "formal_statement",
    "example_intuition",
    "applications",
    "further_reading",
]

# Small English function-word set: presence ratio discriminates English prose
# from drift (e.g. Polish) without an LLM.
_EN_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "is", "are", "in", "on", "that",
    "this", "with", "as", "for", "we", "it", "by", "from", "be", "which", "when",
}
_LANG_FLOOR = 0.06  # >=6% of tokens must be English function words

_WORD_RE = re.compile(r"[A-Za-zÀ-ſ]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# Generic connective lemmas carry no topical signal -> excluded from overlap.
_GENERIC = _EN_STOP | {
    "now", "then", "next", "here", "these", "those", "same", "also", "thus",
    "first", "second", "third", "above", "below", "follows", "consider", "see",
}


@dataclass
class SeamResult:
    passed: bool
    failing_seams: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _content_lemmas(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _GENERIC and len(t) > 2}


def _sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]
    return parts


def _first_sentence(text: str) -> str:
    s = _sentences(text)
    return s[0] if s else ""


def _last_sentence(text: str) -> str:
    s = _sentences(text)
    return s[-1] if s else ""


def _leading_trigram(text: str) -> str:
    toks = _tokens(_first_sentence(text))
    return " ".join(toks[:3])


def _lang_ratio(text: str) -> float:
    toks = _tokens(text)
    if not toks:
        return 1.0
    return sum(1 for t in toks if t in _EN_STOP) / len(toks)


def check_seams(beats: dict[str, str], thesis: str = "") -> SeamResult:
    """Validate the narrative seams over the *present* body beats.

    ``beats`` maps aspect key -> markdown string. ``thesis`` is the synthesis
    plan throughline (may be empty -> seam-only validation)."""
    present = [(k, beats.get(k, "") or "") for k in BEAT_ORDER]
    present = [(k, v) for k, v in present if v.strip()]

    thesis_lemmas = _content_lemmas(thesis)
    failing: list[str] = []

    # 1. Seam continuity (adjacent present beats; first beat has no inbound seam).
    seam_total = max(len(present) - 1, 0)
    seam_pass = 0
    for (pk, pv), (ck, cv) in zip(present, present[1:]):
        prev_lemmas = _content_lemmas(_last_sentence(pv))
        cur_lemmas = _content_lemmas(_first_sentence(cv))
        connected = bool(cur_lemmas & prev_lemmas) or bool(cur_lemmas & thesis_lemmas)
        if connected:
            seam_pass += 1
        else:
            failing.append(
                f"seam {pk}->{ck}: opener has no lemma overlap with prior close "
                f"or thesis"
            )
    seam_continuity = (seam_pass / seam_total) if seam_total else 1.0

    # 2. Boilerplate: >=2 present beats opening with the same leading 3-gram.
    trigrams: dict[str, list[str]] = {}
    for k, v in present:
        tg = _leading_trigram(v)
        if tg:
            trigrams.setdefault(tg, []).append(k)
    for tg, keys in trigrams.items():
        if len(keys) >= 2:
            failing.append(f"boilerplate openers ({tg!r}) in beats: {', '.join(keys)}")

    # 3. Language drift.
    lang_ok = 1.0
    for k, v in present:
        if _lang_ratio(v) < _LANG_FLOOR:
            lang_ok = 0.0
            failing.append(f"beat {k}: language-drift (English function-word ratio below floor)")

    passed = (seam_continuity >= 1.0) and lang_ok >= 1.0 and not any(
        f.startswith("boilerplate") for f in failing
    )
    return SeamResult(
        passed=passed,
        failing_seams=failing,
        scores={
            "seam_continuity": round(seam_continuity, 3),
            "lang_ok": lang_ok,
            "thesis_adherence": round(
                _thesis_adherence(beats, thesis_lemmas), 3
            ),
        },
    )


def _thesis_adherence(beats: dict[str, str], thesis_lemmas: set[str]) -> float:
    """Fraction of beats (incl. tldr) sharing >=1 lemma with the thesis.
    Reported only — never gates (overlap is too noisy to fail on)."""
    if not thesis_lemmas:
        return 0.0
    keys = ["tldr"] + BEAT_ORDER
    vals = [(beats.get(k, "") or "") for k in keys]
    present = [v for v in vals if v.strip()]
    if not present:
        return 0.0
    hits = sum(1 for v in present if _content_lemmas(v) & thesis_lemmas)
    return hits / len(present)
```

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_seams.py -q && .venv/bin/mypy src/services/chat/agents/seams.py`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/seams.py src/services/chat/tests/test_seams.py
git commit -m "feat(tutor): pure-code narrative seam validator"
```

---

## Task 3: Narrative prompt + per-beat Field descriptions

**Files:**
- Modify: `src/services/chat/prompts/deep_tutor.py` (`DEEP_TUTOR_INSTRUCTIONS`, `SYNTHESIS_PLAN_PROMPT`)
- Modify: `src/services/chat/schemas/output.py:163-196` (`DeepTutorAnswer` field descriptions)
- Test: `src/services/chat/tests/test_tutor_narrative_prompt.py` (new)

- [ ] **Step 1: Write the failing test**

```python
from src.services.chat.schemas.output import DeepTutorAnswer
from src.services.chat.prompts import deep_tutor as P


def test_field_descriptions_carry_bridge_contract():
    f = DeepTutorAnswer.model_fields
    # intro must say it stays OUTSIDE the thread
    assert "outside" in f["tldr"].description.lower() or "standalone" in f["tldr"].description.lower()
    # each non-intro beat description names the open/close bridge duty
    for k in ("definition", "example_intuition", "applications", "further_reading"):
        d = f[k].description.lower()
        assert "open" in d and ("previous" in d or "prior" in d)
        assert "next" in d or "set up" in d or "lead" in d


def test_instructions_have_narrative_contract_and_no_orchestrator_tasks():
    txt = P.DEEP_TUTOR_INSTRUCTIONS.lower()
    assert "thread" in txt or "narrative" in txt
    assert "tl;dr" in txt or "introduction" in txt  # intro carve-out present
    # SYNTHESIS_PLAN_PROMPT no longer asks for worker `tasks`
    assert "tasks" not in P.SYNTHESIS_PLAN_PROMPT.lower() or "worker" not in P.SYNTHESIS_PLAN_PROMPT.lower()
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_narrative_prompt.py -q`
Expected: FAIL.

- [ ] **Step 3: Rewrite the field descriptions** (`output.py:163-196`)

Replace the six `Field(description=...)` strings (keep field names + required-ness + the `_require_component_equations` validator untouched):

```python
    tldr: str = Field(
        ...,
        description=(
            "INTRODUCTION — stands OUTSIDE the narrative thread. 2-3 sentence "
            "direct answer, then a one-sentence roadmap of the beats that follow. "
            "Do NOT write a transition into or out of this section."
        ),
    )
    definition: str = Field(
        ...,
        description=(
            "BEAT 1 (Define). Opens the thread from the thesis (not from the "
            "intro). Defines the concept; component subsections each carry their "
            "$$display equation$$. CLOSE by setting up why we next make it "
            "precise / see it work."
        ),
    )
    formal_statement: str = Field(
        ...,
        description=(
            "BEAT 2 (Formalize). Verbatim numbered theorem/definition when the "
            "sources state one ('Conforming to Definition X.Y.Z, …' + blockquote), "
            "OPENING by carrying the definition forward and CLOSING toward the "
            "worked example. Otherwise an EMPTY STRING — when empty the heading is "
            "dropped and Beat 3 must hand off directly from Beat 1 (do NOT leave a "
            "dangling 'as the theorem above shows')."
        ),
    )
    example_intuition: str = Field(
        ...,
        description=(
            "BEAT 3 (See it work). OPENS by carrying the prior beat's thread "
            "forward (the definition/formal result). Describe three cases, analyse "
            "them, state explicitly 'the intuition here is that …'. CLOSE by "
            "setting up real-world use."
        ),
    )
    applications: str = Field(
        ...,
        description=(
            "BEAT 4 (Use it). OPENS from the worked example's thread. "
            "Corpus-grounded specific use-cases (method/model/dataset, cited). "
            "CLOSE by pointing past current practice."
        ),
    )
    further_reading: str = Field(
        ...,
        description=(
            "BEAT 5 (Go further). OPENS from the applications thread. Related "
            "topics with citations + 2-3 open research questions extending this "
            "topic. Closes the narrative."
        ),
    )
```

- [ ] **Step 4: Rewrite `DEEP_TUTOR_INSTRUCTIONS` narrative contract + strip plan tasks**

Read the current `DEEP_TUTOR_INSTRUCTIONS` and `SYNTHESIS_PLAN_PROMPT`. Add a NARRATIVE CONTRACT block to the instructions (keep all existing per-beat content/citation/figure/`$$`-owns-line rules — those still hold):

```
NARRATIVE CONTRACT (one continuous story, intro excluded):
- The TL;DR introduction stands alone. Do not thread it.
- The five body beats form ONE story developing the <thesis> you are given.
  Each body beat OPENS with a clause that carries the previous beat's idea
  forward, and CLOSES with a clause that sets up the next beat.
- Vary the bridge: echo a key term, pose the question the next beat answers,
  or carry the running example forward. NEVER open two beats with the same
  phrase, and never use the formula "Now that we …".
- If you leave formal_statement empty, Beat 3 (see it work) must hand off
  directly from Beat 1 (define) — do not reference a theorem you did not state.
- Write in English.
```

In `SYNTHESIS_PLAN_PROMPT`, remove the instructions that ask the model to populate worker `tasks` (orchestrator-only). The `SynthesisPlan.tasks` schema field stays (defaults empty) for one release.

- [ ] **Step 5: Run, verify pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_narrative_prompt.py src/services/chat/tests/test_tutor_prompt_contract.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/prompts/deep_tutor.py src/services/chat/schemas/output.py src/services/chat/tests/test_tutor_narrative_prompt.py
git commit -m "feat(tutor): narrative field descriptions + thread contract; strip orchestrator plan tasks"
```

---

## Task 4: Wire seam validation + one bounded redraft + thesis injection

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py` (`_stream_draft` :1857 thesis injection; assemble region :2748-2780 seam validate + redraft + quality)
- Test: `src/services/chat/tests/test_tutor_seam_wiring.py` (new)
- Verify (manual, Step 6): `web/src/components/views/TutorView.tsx` final-payload-overwrites-stream behavior

- [ ] **Step 1: Write the failing test** (monkeypatch the draft to return controlled aspects; assert one redraft happens on seam failure and `quality` is recorded)

```python
import asyncio
import pytest
import src.services.chat.agents.deep_tutor as dt
from src.services.chat.agents.seams import BEAT_ORDER


def test_seam_failure_triggers_one_redraft(monkeypatch):
    calls = {"n": 0}
    bad = {k: "" for k in BEAT_ORDER}
    bad.update(definition="Bias is systematic error.",
               example_intuition="Photosynthesis happens in chloroplasts.")
    good = {k: "" for k in BEAT_ORDER}
    good.update(definition="Bias is systematic error in a model.",
                example_intuition="That same bias appears when a linear model misfits curves.")

    async def fake_validate_and_maybe_redraft(aspects, deep, *, query, plan, **kw):
        # exercised through the real wiring helper
        raise AssertionError("replace with real helper under test")

    # See Step 3: the real helper is `_seam_guard`. Test it directly.
    async def fake_redraft(**kw):
        calls["n"] += 1
        return None, good

    res_aspects, scores = asyncio.run(
        dt._seam_guard(bad, thesis="bias variance", redraft=fake_redraft)
    )
    assert calls["n"] == 1
    assert res_aspects["example_intuition"].startswith("That same bias")
    assert "seam_continuity" in scores


def test_second_failure_accepts_and_records(monkeypatch):
    bad = {k: "" for k in BEAT_ORDER}
    bad.update(definition="Bias is error.",
               example_intuition="Photosynthesis in chloroplasts.")

    async def always_bad(**kw):
        return None, bad

    res_aspects, scores = asyncio.run(
        dt._seam_guard(bad, thesis="bias", redraft=always_bad)
    )
    # accepted despite failure; score reflects the failing seam
    assert scores["seam_continuity"] < 1.0
```

- [ ] **Step 2: Run, verify fail**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_seam_wiring.py -q`
Expected: FAIL (`_seam_guard` undefined).

- [ ] **Step 3: Implement `_seam_guard` + thesis injection + wire it**

Add to `deep_tutor.py`:

```python
async def _seam_guard(aspects, thesis, *, redraft):
    """Validate narrative seams; on failure re-roll the draft ONCE (caller
    supplies a non-streamed ``redraft`` coroutine returning ``(deep, aspects)``).
    Returns ``(final_aspects, quality_scores)``. Never raises, never aborts."""
    from src.services.chat.agents.seams import check_seams
    res = check_seams(aspects, thesis=thesis or "")
    if res.passed:
        return aspects, res.scores
    logger.info("seam check failed: %s", "; ".join(res.failing_seams))
    try:
        _deep2, aspects2 = await redraft(failing=res.failing_seams)
        res2 = check_seams(aspects2, thesis=thesis or "")
        # keep whichever scored higher on continuity; record the score.
        if res2.scores["seam_continuity"] >= res.scores["seam_continuity"]:
            return aspects2, res2.scores
    except Exception:  # noqa: BLE001
        logger.exception("seam redraft failed; accepting first draft")
    return aspects, res.scores
```

Thesis injection: in `_stream_draft` (read :1857), prepend the plan thesis to the user message under an explicit header when `plan` is present:

```python
    if plan is not None and getattr(plan, "thesis", ""):
        user_msg = f"<thesis>Develop this single throughline and nothing else: {plan.thesis}</thesis>\n\n" + user_msg
```

Wire into `run_deep_tutor` after the draft drain (around :2722, before assemble :2748). Build a non-streamed redraft closure that re-calls `_stream_draft` with `on_aspect_delta=None` and a retry note appended to instructions naming the failing seams; then merge scores into the final answer's `quality`:

```python
    deep, aspects = await draft_task
    timings["draft_ms"] = int((time.monotonic() - t_draft) * 1000)

    async def _redraft(failing):
        note = ("\n\nThe previous draft broke these narrative seams; fix them "
                "while keeping every other rule:\n- " + "\n- ".join(failing))
        return await _stream_draft(
            query, sources, figures=approved_figures,
            on_aspect_delta=None, model=m_draft, plan=plan,
            recovered_block=await _recover_equations_block(query, sources),
            extra_instructions=note,
        )

    thesis = getattr(plan, "thesis", "") if plan is not None else ""
    aspects, seam_scores = await _seam_guard(aspects, thesis, redraft=_redraft)
    if deep is not None:
        for k, v in aspects.items():
            if hasattr(deep, k):
                try:
                    setattr(deep, k, v)
                except Exception:  # noqa: BLE001
                    pass
```

After `_convert_to_tutor_answer` (:2776), merge the scores into the existing quality dict before `final_payload`:

```python
    answer.quality.update(seam_scores)
    final_payload = answer.model_dump()
```

(Read `_stream_draft` to add the `extra_instructions: str = ""` param if it doesn't already accept one; append it to the instruction string the same way `instructions` is used.)

- [ ] **Step 4: Run, verify pass**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_seam_wiring.py src/services/chat/tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_tutor_seam_wiring.py
git commit -m "feat(tutor): wire seam guard, bounded redraft, thesis injection, quality scores"
```

- [ ] **Step 6: Verify the stream-overwrite assumption (manual, blocking)**

Read `web/src/components/views/TutorView.tsx` + `web/src/api/sse.ts` + `web/src/state/chat.ts`: confirm the final `structured_output:TutorAnswer` payload REPLACES the accumulated streamed `token` text (not appends). Record the finding in the task report. If the stream is authoritative (redraft text would NOT overwrite), STOP and report — the redraft must instead run pre-stream (buffered) and this task's wiring changes. Default plan assumes overwrite holds.

---

## Task 5: Non-interference tests (invariants survive narrative prose)

**Files:**
- Test: `src/services/chat/tests/test_tutor_narrative_invariants.py` (new)

- [ ] **Step 1: Write the tests**

```python
import re
from src.services.chat.agents.seams import BEAT_ORDER, _first_sentence, _last_sentence
from src.services.chat.schemas.output import DeepTutorAnswer


def test_seam_sentences_never_contain_display_math():
    # guards: transition clauses must not swallow a $$ block onto a seam line
    sample = {
        "definition": "Bias is error. $$\\mathrm{Bias}=\\mathbb{E}[\\hat f]-f$$ It sets up variance.",
        "example_intuition": "Building on bias, variance measures spread. It leads to applications.",
    }
    for k in ("definition", "example_intuition"):
        assert "$$" not in _first_sentence(sample[k])
        assert "$$" not in _last_sentence(sample[k])


def test_component_equation_validator_passes_on_narrative_definition():
    # a math definition whose component subsections each carry a real equation
    ans = DeepTutorAnswer(
        tldr="Intro.",
        definition=(
            "Error decomposes into two components.\n\n"
            "### Bias\nBias is the gap. $$\\mathrm{Bias}=\\mathbb{E}[\\hat f]-f$$\n\n"
            "### Variance\nVariance is the spread. $$\\mathrm{Var}=\\mathbb{E}[(\\hat f-\\mathbb{E}\\hat f)^2]$$"
        ),
        formal_statement="",
        example_intuition="See it on a polynomial fit.",
        applications="Used in random forests.",
        further_reading="See ESL 7.",
        math_blocks=["x"],
    )
    assert ans.definition.count("### ") == 2


def test_component_equation_validator_still_raises_on_wordform():
    import pytest
    with pytest.raises(Exception):
        DeepTutorAnswer(
            tldr="Intro.",
            definition=(
                "Decomposition.\n\n### Bias\nNo formula here, just words about bias.\n\n"
                "### Variance\nAlso words.$$\\text{Variance}\\approx\\text{MSE}$$"
            ),
            formal_statement="",
            example_intuition="x", applications="y", further_reading="z",
            math_blocks=["x"],
        )
```

- [ ] **Step 2: Run, verify pass** (these assert existing behavior holds with the new prose shape)

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_narrative_invariants.py -q`
Expected: PASS. If `test_component_equation_validator_still_raises_on_wordform` fails, the component-equation invariant regressed — STOP and report.

- [ ] **Step 3: Full backend gate**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q && .venv/bin/ruff check src/services/chat/`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/services/chat/tests/test_tutor_narrative_invariants.py
git commit -m "test(tutor): non-interference — equations/citations/figures survive narrative prose"
```

---

## Task 6: Frontend lockstep — scrub workflow knob, collapse pipeline diagram

**Files:**
- Modify: `web/src/state/chat.ts`, `web/src/api/sse.ts`, `web/src/App.tsx`, `web/src/components/modals/AboutModelModal.tsx` (remove `tutorWorkflow` send/select)
- Modify: `web/src/data/tutorPipeline.ts`, `web/src/components/PipelineDiagram.tsx` (delete OW / organize / orchestrator-deep nodes + workflow selector; single narrative draft node)
- Modify: `web/src/components/PipelineDiagram.test.tsx`
- Test: existing vitest suite

- [ ] **Step 1: Update the diagram test first** — in `PipelineDiagram.test.tsx`, replace assertions that expect orchestrator/organize/orchestrator-deep nodes or a workflow dropdown with assertions that (a) no workflow selector renders, (b) a single `draft` (narrative) node exists. Add:

```ts
it("renders a single narrative draft node and no workflow selector", () => {
  render(<PipelineDiagram /* existing required props */ />);
  expect(screen.queryByText(/orchestrator/i)).toBeNull();
  expect(screen.queryByText(/organize/i)).toBeNull();
  expect(screen.getByText(/draft/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run, verify fail**

Run: `cd web && npm test -- --run PipelineDiagram`
Expected: FAIL.

- [ ] **Step 3: Implement**

1. `tutorPipeline.ts`: remove the orchestrator/organize/orchestrator-deep node + edge definitions and any `StageKey` entries only they used; keep the linear chain ending in a single `draft` node labelled "narrative draft". 
2. `PipelineDiagram.tsx`: delete the workflow-variant branching (single vs orchestrator vs organize) and the workflow `<select>`; render the one collapsed chain. Keep per-node model dropdowns.
3. `state/chat.ts` + `sse.ts` + `App.tsx` + `AboutModelModal.tsx`: remove every `tutorWorkflow` reference (request payload field, any UI control, any persisted setting). `grep -rn "tutorWorkflow\|orchestrator-deep\|organize" web/src` must return nothing after.

- [ ] **Step 4: Run gates**

Run: `cd web && npm test -- --run && npx tsc --noEmit`
Expected: PASS, tsc clean, grep clean.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "refactor(web): collapse tutor pipeline diagram to single narrative path; drop tutorWorkflow knob"
```

---

## Task 7: Docs + HTML + invariants + changelog lockstep

**Files:**
- Create: `docs/services/chat-features/57-tutor-narrative.md`
- Modify: `docs/services/chat-features/36-deep-tutor.md` (mermaid graph + env table — drop `TUTOR_WORKFLOW`/`TUTOR_OW_HARNESS`/`TUTOR_ORGANIZE_*`/`TUTOR_WORKER_MODEL`; add narrative-seam stage)
- Modify: `docs/services/chat-features/44-orchestrator-workers.md`, `48-long-context-organizer.md`, `56-deep-synthesis-l3b.md` (prepend SUPERSEDED banner pointing to 57)
- Modify: `docs/common ground/Elements/modes/tutor.html` (two diagrams reflect single narrative path)
- Modify: `docs/system/invariants.md` (new invariant: tutor body beats form one woven narrative validated by `seams.py`; intro excluded), `docs/system/changelog.md` (top entry)
- Modify: `CLAUDE.md` pending-tasks table (mark this rebuild + note doc 57)

- [ ] **Step 1: Write `57-tutor-narrative.md`** — single source of truth for the rebuilt mode: the collapsed pipeline, the 5-beat arc + intro carve-out, beat→field mapping table, the seam validator contract (rules + scores `seam_continuity`/`lang_ok`/`thesis_adherence`), bounded-redraft behavior, formula-recovery rewire, and the cut list. Include a mermaid graph of the collapsed pipeline.

- [ ] **Step 2: Update `36-deep-tutor.md`** — replace the workflow-branching mermaid with the single narrative path + seam-guard node; delete the removed `TUTOR_*` rows from the env table; add a row noting seams.py is config-free.

- [ ] **Step 3: SUPERSEDED banners** on 44/48/56 — top line: `> **SUPERSEDED 2026-06-11** by [57-tutor-narrative](57-tutor-narrative.md) — orchestrator-workers / organize / deepagents synthesis removed; tutor now uses a single woven-narrative synthesizer.`

- [ ] **Step 4: Update `Elements/modes/tutor.html`** — both pipeline diagrams show the collapsed single narrative path (no orchestrator cluster). Match the labels in `tutorPipeline.ts`.

- [ ] **Step 5: invariants + changelog + CLAUDE.md** — add the narrative invariant; changelog top entry summarizing the collapse + seam validator; update the CLAUDE.md pending table row.

- [ ] **Step 6: Commit**

```bash
git add docs CLAUDE.md
git commit -m "docs(tutor): doc 57 narrative rebuild; supersede 44/48/56; env table + invariants + changelog + HTML lockstep"
```

---

## Task 8: Live verification (orchestrator-run, Law 1)

> Not a subagent task — the orchestrator runs this personally after all reviews pass. Listed here so it is tracked.

- [ ] **Step 1:** Launch `./scripts/dev.sh` (Vite :5175 + backend :8766). Confirm Qdrant up.
- [ ] **Step 2:** Bias-variance query (the known conv topic) in tutor mode. Watch the stream. Inspect the rendered answer: intro standalone; 5 beats each opening with a carry-forward clause; `### Bias`/`### Variance` each carry a real `$$` equation; citations hyperlink; any figure placed in a beat. Read `quality` (seam_continuity, lang_ok) off the payload.
- [ ] **Step 3:** No-theorem query (forces `formal_statement=""`) — confirm the formalize beat is dropped AND beat 3 hands off from the definition with no dangling theorem reference.
- [ ] **Step 4:** Open the tutor (i) modal; confirm it matches `Elements/modes/tutor.html` (single narrative path, no orchestrator nodes).
- [ ] **Step 5:** Final-result check **via Google MCP acting as the user** — drive the browser as a real user would, read the final answer end-to-end for narrative coherence (does it read as one story?), capture counts (beats, seams that connect, equations present).
- [ ] **Step 6:** `rag-verify` skill — report pre-existing invariant violations, do not fix unrelated ones.

---

## Self-review notes

- **Spec coverage:** collapse (T1) · seam validator (T2) · prompt/schema contract (T3) · wiring+redraft+thesis (T4) · invariant non-interference (T5) · frontend lockstep (T6) · docs/HTML/invariants (T7) · live verify incl. Google-MCP-as-user (T8). Formula-recovery rewire = T1 Step 5. Stream-overwrite assumption = T4 Step 6 (blocking verify). All spec sections mapped.
- **Sequencing:** T1→T2→T3→T4 strictly ordered (T4 depends on seams + prompt + collapse). T5 after T4. T6 (frontend) after T1 removes the field. T7 after code settles. T8 last.
- **Parallelism:** none within backend (shared `deep_tutor.py`). T6 frontend could overlap T2/T3 but T1 must land first (removes the field T6 scrubs) — run sequentially to avoid merge surprises.
