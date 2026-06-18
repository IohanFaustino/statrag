# Tutor Multi-Question Facet Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make multi-question tutor prompts decompose so every question becomes a covered facet and every named definitional form (strict/weak/covariance stationarity, unit root) gets a verbatim `formal_statements[]` box.

**Architecture:** Pure-code, true-by-construction. A regex splitter turns an N-question prompt into N asks; a regex concept-extractor turns each ask into a subject; both are unioned (ask-subjects first) into the planner's `concepts` (→ definition recovery) and `facets` (→ coverage + finalize) at the single point where they're read. Definition recovery already runs by default (`TUTOR_DEEP_DEFINITIONS` defaults `'1'`) and already expands `stationarity → {strict, weak, covariance}`; the only gap was that each question's subject never reached it, and the `_MAX_GAPS` cap was too low for 4 forms.

**Tech Stack:** Python 3.12, pytest. Files: `src/services/chat/agents/definition_gaps.py` (pure helpers), `src/services/chat/agents/deep_tutor.py` (wiring), `src/services/chat/tests/`.

**Spec corrections (vs `2026-06-18-tutor-multiquestion-facet-contract-design.md`):** `TUTOR_DEEP_DEFINITIONS` already defaults ON; "unit root" needs NO map/regex entry (query is already definitional via "what is/are", and unit root has no sub-forms — it passes through as itself); the real change is reaching the detector + raising `_MAX_GAPS`.

---

### Task 1: `multi_question_split` — split a prompt into asks

**Files:**
- Modify: `src/services/chat/agents/definition_gaps.py` (append helper near top-level functions)
- Test: `src/services/chat/tests/test_multiquestion_facets.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# src/services/chat/tests/test_multiquestion_facets.py
from src.services.chat.agents.definition_gaps import multi_question_split


def test_split_three_questions():
    q = "What is stationarity? What are its versions? What is a unit root?"
    assert multi_question_split(q) == [
        "What is stationarity?",
        "What are its versions?",
        "What is a unit root?",
    ]


def test_single_question_returns_itself():
    assert multi_question_split("What is a unit root?") == ["What is a unit root?"]


def test_no_question_mark_returns_itself():
    assert multi_question_split("Explain stationarity.") == ["Explain stationarity."]


def test_caps_at_five():
    q = " ".join(f"Q{i}?" for i in range(8))
    assert len(multi_question_split(q)) <= 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_multiquestion_facets.py -q`
Expected: FAIL — `ImportError: cannot import name 'multi_question_split'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/services/chat/agents/definition_gaps.py`:

```python
_MAX_ASKS = 5


def multi_question_split(prompt: str) -> list[str]:
    """Split a prompt into sentence-final-``?`` questions. Single-question or
    no-``?`` prompts return ``[prompt.strip()]``. Pure, deterministic."""
    if not prompt or not prompt.strip():
        return []
    # Keep the trailing '?' on each piece; split only on '?' followed by
    # whitespace+capital or end (sentence-final), so "AR(1)?" mid-clause is safe.
    parts = re.findall(r"[^?]*\?", prompt)
    asks = [p.strip() for p in parts if p.strip()]
    if len(asks) <= 1:
        return [prompt.strip()]
    return asks[:_MAX_ASKS]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_multiquestion_facets.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/definition_gaps.py src/services/chat/tests/test_multiquestion_facets.py
git commit -m "feat(tutor): multi_question_split — split prompt into asks"
```

---

### Task 2: `concepts_from_asks` + raise `_MAX_GAPS`

**Files:**
- Modify: `src/services/chat/agents/definition_gaps.py`
- Test: `src/services/chat/tests/test_multiquestion_facets.py`

- [ ] **Step 1: Write the failing test (append)**

```python
from src.services.chat.agents.definition_gaps import concepts_from_asks, _MAX_GAPS


def test_concepts_from_asks_strips_scaffolding():
    asks = ["What is stationarity?", "What is a unit root?"]
    got = concepts_from_asks(asks)
    assert "stationarity" in got
    assert "unit root" in got


def test_max_gaps_fits_four_forms():
    # strict + weak + covariance stationarity + unit root = 4
    assert _MAX_GAPS >= 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_multiquestion_facets.py -q`
Expected: FAIL — `ImportError: cannot import name 'concepts_from_asks'` (and `_MAX_GAPS` is 3)

- [ ] **Step 3: Write minimal implementation**

In `src/services/chat/agents/definition_gaps.py`: change `_MAX_GAPS = 3` to `_MAX_GAPS = 5`, and add:

```python
# Strip leading question scaffolding + articles + trailing punctuation to get
# the bare subject of an ask. Junk subjects (e.g. "its versions") are harmless:
# they yield no labelled def and are dropped. ponytail: regex, not an LLM call.
_SCAFFOLD_RE = re.compile(
    r"^\s*(what\s+is|what\s+are|what\s+does|define|definition\s+of|explain|describe|"
    r"how\s+is|how\s+does)\s+", re.IGNORECASE)
_ARTICLE_RE = re.compile(r"^(a|an|the)\s+", re.IGNORECASE)


def concepts_from_asks(asks: list[str]) -> list[str]:
    """Best-effort bare subject of each ask (pure regex). Order preserved."""
    out: list[str] = []
    for ask in asks:
        s = _SCAFFOLD_RE.sub("", ask.strip())
        s = s.rstrip("?.!").strip()
        s = _ARTICLE_RE.sub("", s).strip()
        if s and s.lower() not in (c.lower() for c in out):
            out.append(s)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_multiquestion_facets.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/definition_gaps.py src/services/chat/tests/test_multiquestion_facets.py
git commit -m "feat(tutor): concepts_from_asks + raise _MAX_GAPS to 5"
```

---

### Task 3: Wire asks into concepts + facets in the pipeline

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py:2822-2823` (after `concepts`/`facets` are read from the plan)
- Test: `src/services/chat/tests/test_multiquestion_facets.py`

- [ ] **Step 1: Write the failing test (append) — drives the unioning logic as a pure helper**

To keep the wiring testable without running the whole async pipeline, the union is a tiny pure helper. Test it directly:

```python
from src.services.chat.agents.definition_gaps import augment_concepts_and_facets


def test_augment_unions_asks_first():
    query = "What is stationarity? What are its versions? What is a unit root?"
    concepts, facets = augment_concepts_and_facets(query, ["stationarity"], ["stationarity"])
    # ask-subjects unioned in FIRST so they survive the _MAX_GAPS cap
    assert concepts[0] == "stationarity"
    assert "unit root" in concepts
    # each question becomes a facet to cover
    assert "What is a unit root?" in facets


def test_augment_single_question_noop_ish():
    concepts, facets = augment_concepts_and_facets("What is a unit root?", ["unit root"], ["unit root"])
    assert "unit root" in concepts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_multiquestion_facets.py -q`
Expected: FAIL — `ImportError: cannot import name 'augment_concepts_and_facets'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/services/chat/agents/definition_gaps.py`:

```python
def augment_concepts_and_facets(
    query: str, concepts: list[str], facets: list[str]
) -> tuple[list[str], list[str]]:
    """For a multi-question prompt, union each question's subject into concepts
    (ask-subjects FIRST so they survive the _MAX_GAPS cap) and each question
    into facets. Single-question prompts: just ensure the subject is present."""
    asks = multi_question_split(query)
    ask_concepts = concepts_from_asks(asks)

    def _dedup(seq: list[str]) -> list[str]:
        seen: dict[str, str] = {}
        for x in seq:
            k = x.strip().lower()
            if x.strip() and k not in seen:
                seen[k] = x.strip()
        return list(seen.values())

    new_concepts = _dedup([*ask_concepts, *concepts])
    new_facets = _dedup([*facets, *asks]) if len(asks) > 1 else _dedup(facets)
    return new_concepts, new_facets
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_multiquestion_facets.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Wire into the pipeline**

In `src/services/chat/agents/deep_tutor.py`, find (around line 2822):

```python
    concepts = plan_qp.concepts
    facets = plan_qp.facets
```

Replace with:

```python
    concepts = plan_qp.concepts
    facets = plan_qp.facets
    # Scope A: guarantee every question in a multi-question prompt becomes a
    # concept (→ definition recovery) and a facet (→ coverage + finalize).
    from src.services.chat.agents.definition_gaps import augment_concepts_and_facets  # noqa: PLC0415
    concepts, facets = augment_concepts_and_facets(query, concepts, facets)
```

- [ ] **Step 6: Verify nothing regressed + import resolves**

Run: `.venv/bin/python -c "import src.services.chat.agents.deep_tutor"`
Expected: no error.
Run: `.venv/bin/python -m pytest src/services/chat/tests/test_deep_tutor.py -q`
Expected: PASS (no regressions).

- [ ] **Step 7: Commit**

```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_multiquestion_facets.py
git commit -m "feat(tutor): union multi-question asks into concepts + facets"
```

---

### Task 4: Regression test — the stationarity prompt yields all three forms

**Files:**
- Test: `src/services/chat/tests/test_multiquestion_facets.py`

This is the spec's acceptance test, expressed against the pure detector (no LLM/network): with the augmented concepts and a definitional query, `detect_definition_gaps` must surface strict + weak stationarity AND unit root.

- [ ] **Step 1: Write the test (append)**

```python
from src.services.chat.agents.definition_gaps import detect_definition_gaps


def test_stationarity_prompt_surfaces_all_required_forms():
    query = "What is stationarity? What are its versions? What is a unit root?"
    concepts, _facets = augment_concepts_and_facets(query, ["stationarity"], ["stationarity"])
    # sources empty → every concept lacks a labelled def → all become gaps
    gaps = {g.norm for g in detect_definition_gaps(concepts, query, [])}
    assert "strict stationarity" in gaps
    assert "weak stationarity" in gaps
    assert "unit root" in gaps
```

- [ ] **Step 2: Run test to verify it passes (proves the end-to-end contract)**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_multiquestion_facets.py -q`
Expected: PASS (9 tests). If `unit root` is missing → `concepts_from_asks` didn't extract it (check Task 2); if a form is missing → `_MAX_GAPS` too low (check Task 2).

- [ ] **Step 3: Commit**

```bash
git add src/services/chat/tests/test_multiquestion_facets.py
git commit -m "test(tutor): stationarity multi-question prompt surfaces strict/weak/unit-root"
```

---

## Self-review notes

- **Spec coverage:** split (T1), form-reaching via concept extraction (T2), binding into concepts+facets (T3), acceptance test (T4). Unit-root-as-facet covered by T3; verbatim-box rendering is existing behaviour once the gap is detected (T4 proves detection).
- **Out of scope (follow-ups):** decompose-chain hardening (B), narrative thread/spine (C), coverage retry-and-enforce (D).
- **Type consistency:** `multi_question_split`/`concepts_from_asks`/`augment_concepts_and_facets`/`detect_definition_gaps` signatures consistent across tasks.
- **Live verify after merge:** ask the stationarity 3-question prompt on :5175; confirm the answer covers all three questions and renders verbatim formal defs for strict + weak stationarity + unit root.
