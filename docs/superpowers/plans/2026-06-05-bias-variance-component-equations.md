# Bias-Variance Per-Component Equation Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject + auto-repair deep-tutor answers whose mathematical `definition` has a `### ` subsection lacking a `$$…$$` defining equation (or carrying a word-form pseudo-equation), so component subsections like `### Bias`/`### Variance` always state their formula.

**Architecture:** Add a Pydantic `model_validator` to `DeepTutorAnswer` (`schemas/output.py`). It raises on non-compliant math answers; the orchestrator's existing ADR-005 `_validate_and_repair` path (`orchestrator.py:403`) catches the `ValidationError` and runs one free-form repair call that backfills the missing equations. A prompt nudge in `prompts/deep_tutor.py` bans word-form pseudo-equations. No frontend change — `definition` stays a markdown string.

**Tech Stack:** Python 3.12, Pydantic v2 (`model_validator(mode="after")`), `re`, pytest. Chinese-wall in `schemas/output.py`: stdlib + pydantic only, no `src.*` imports.

---

## File Structure

- `src/services/chat/schemas/output.py` — add `model_validator` import, two module-level helper functions (`_split_definition_subsections`, `_has_real_equation`), and `_require_component_equations` on `DeepTutorAnswer`.
- `src/services/chat/prompts/deep_tutor.py` — append a negative example to the `definition` block (~lines 218-221).
- `src/services/chat/tests/test_component_equations.py` — NEW unit tests for the validator + helpers.

---

## Task 1: Equation-detection helpers

**Files:**
- Modify: `src/services/chat/schemas/output.py` (top of file + new helpers before `class DeepTutorAnswer`)
- Test: `src/services/chat/tests/test_component_equations.py`

- [ ] **Step 1: Write the failing test**

Create `src/services/chat/tests/test_component_equations.py`:

```python
"""Unit tests for per-component equation enforcement on DeepTutorAnswer."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.services.chat.schemas.output import (
    _has_real_equation,
    _split_definition_subsections,
)


def test_split_definition_subsections_returns_name_and_body():
    text = (
        "framing sentence with no header.\n"
        "### Bias\nbias prose\n"
        "### Variance\nvariance prose\n"
    )
    subs = _split_definition_subsections(text)
    assert [name for name, _ in subs] == ["Bias", "Variance"]
    assert "bias prose" in dict(subs)["Bias"]


def test_split_definition_subsections_empty_when_no_headers():
    assert _split_definition_subsections("just a paragraph, no headers") == []


def test_has_real_equation_true_for_symbolic_block():
    body = r"text before $$\mathrm{Var}(\hat\theta)=\mathbb{E}[(\hat\theta-\mathbb{E}[\hat\theta])^2]$$ after"
    assert _has_real_equation(body) is True


def test_has_real_equation_false_when_no_block():
    assert _has_real_equation("only prose, no dollars") is False


def test_has_real_equation_false_for_word_form_pseudo_equation():
    body = r"$$\text{Squared bias}+\text{Variance}\approx\text{Test MSE}$$"
    assert _has_real_equation(body) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest src/services/chat/tests/test_component_equations.py -v`
Expected: FAIL — `ImportError: cannot import name '_has_real_equation'`.

- [ ] **Step 3: Write minimal implementation**

In `src/services/chat/schemas/output.py`, change the pydantic import line:

```python
from pydantic import BaseModel, Field, model_validator
```

Add `import re` to the stdlib imports (after `from typing import Literal`):

```python
import re
```

Add these module-level helpers immediately before `class DeepTutorAnswer(BaseModel):` (around line 111):

```python
# ---------------------------------------------------------------------------
# Per-component equation enforcement (bias-variance fix, 2026-06-05)
# ---------------------------------------------------------------------------

_DISPLAY_EQ_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
# A display block is a "real" equation only if its body carries a math symbol
# beyond words/\text/\approx — a relation/operator/greek/command/digit.
_REAL_MATH_RE = re.compile(
    r"=|\^|_|\\frac|\\hat|\\mathbb|\\mathrm|\\sum|\\int|\\sigma|\\theta"
    r"|\\beta|\\lambda|\\mu|\\partial|\\sqrt|\\bar|\\big|\d"
)


def _split_definition_subsections(text: str) -> list[tuple[str, str]]:
    """Split a markdown ``definition`` into ``(heading, body)`` pairs, one per
    ``### `` subsection. Text before the first ``### `` (framing sentence) is
    ignored. Returns ``[]`` when there are no ``### `` headers."""
    parts = re.split(r"(?m)^###\s+(.+?)\s*$", text)
    # parts = [pre, name1, body1, name2, body2, ...]
    out: list[tuple[str, str]] = []
    for i in range(1, len(parts) - 1, 2):
        out.append((parts[i].strip(), parts[i + 1]))
    return out


def _has_real_equation(body: str) -> bool:
    """True iff ``body`` contains a ``$$…$$`` block whose contents include a
    genuine math symbol (not a word-form pseudo-equation like
    ``$$\\text{Squared bias}+\\text{Variance}\\approx\\text{Test MSE}$$``)."""
    for m in _DISPLAY_EQ_RE.finditer(body):
        inner = m.group(1)
        # Strip \text{...} wrappers so their letters don't count as math.
        stripped = re.sub(r"\\text\{[^}]*\}", "", inner)
        if _REAL_MATH_RE.search(stripped):
            return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest src/services/chat/tests/test_component_equations.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/schemas/output.py src/services/chat/tests/test_component_equations.py
git commit -m "feat(schema): equation-detection helpers for component-equation enforcement"
```

---

## Task 2: The `model_validator` on `DeepTutorAnswer`

**Files:**
- Modify: `src/services/chat/schemas/output.py` (inside `class DeepTutorAnswer`, after the field declarations ~line 158)
- Test: `src/services/chat/tests/test_component_equations.py`

- [ ] **Step 1: Write the failing test**

Append to `src/services/chat/tests/test_component_equations.py`:

```python
def _answer(definition: str, math_blocks=None) -> dict:
    """Minimal valid DeepTutorAnswer payload with a custom definition."""
    return dict(
        tldr="intro",
        definition=definition,
        formal_statement="",
        example_intuition="ex",
        applications="apps",
        further_reading="more",
        math_blocks=math_blocks or [],
    )


def _build(**kw):
    from src.services.chat.schemas.output import DeepTutorAnswer

    return DeepTutorAnswer(**_answer(**kw))


def test_math_definition_missing_variance_equation_rejected():
    definition = (
        "We define each component.\n"
        "### Bias\n- bias prose\n"
        r"$$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$" "\n"
        "### Variance\n- variance prose, but no formula here\n"
        "### MSE\n"
        r"$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$" "\n"
    )
    with pytest.raises(ValidationError) as exc:
        _build(definition=definition)
    assert "Variance" in str(exc.value)


def test_math_definition_all_subsections_have_equation_valid():
    definition = (
        "We define each component.\n"
        "### Bias\n"
        r"$$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$" "\n"
        "### Variance\n"
        r"$$\mathrm{Var}(\hat\theta)=\mathbb{E}[(\hat\theta-\mathbb{E}[\hat\theta])^2]$$" "\n"
        "### MSE\n"
        r"$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$" "\n"
    )
    ans = _build(definition=definition)
    assert ans.definition == definition


def test_conceptual_definition_no_math_is_exempt():
    definition = (
        "Overfitting is when a model learns noise.\n"
        "### Symptoms\n- high train accuracy, low test accuracy\n"
        "### Causes\n- too much flexibility\n"
    )
    ans = _build(definition=definition)  # no math_blocks, no $$ -> no-op gate
    assert ans.definition == definition


def test_pseudo_equation_rejected():
    definition = (
        "We define each component.\n"
        "### Bias\n"
        r"$$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$" "\n"
        "### MSE\n"
        r"$$\text{Squared bias}+\text{Variance}\approx\text{Test MSE}$$" "\n"
    )
    with pytest.raises(ValidationError) as exc:
        _build(definition=definition)
    assert "MSE" in str(exc.value)


def test_header_less_text_definition_does_not_raise():
    # _wrap_text_answer path: raw text, no ### headers -> no-op even if math.
    definition = r"A paragraph mentioning $$x=1$$ with no headers at all."
    ans = _build(definition=definition, math_blocks=[r"$$x=1$$"])
    assert ans.definition == definition
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest src/services/chat/tests/test_component_equations.py -v -k "definition or pseudo or header_less"`
Expected: FAIL — the rejection tests fail because no validator exists yet (answers construct successfully).

- [ ] **Step 3: Write minimal implementation**

In `src/services/chat/schemas/output.py`, add this method inside `class DeepTutorAnswer`, immediately after the `figures` field (~line 158):

```python
    @model_validator(mode="after")
    def _require_component_equations(self) -> "DeepTutorAnswer":
        """Every component ``### `` subsection of a *mathematical* definition
        must carry a real ``$$…$$`` defining equation. Math-answer gate: only
        enforced when ``math_blocks`` is non-empty or ``definition`` contains
        ``$$``. Header-less / non-math definitions are exempt, so directly
        constructed fallbacks (e.g. ``_wrap_text_answer``) never raise."""
        is_math = bool(self.math_blocks) or "$$" in self.definition
        if not is_math:
            return self
        for name, body in _split_definition_subsections(self.definition):
            if not _has_real_equation(body):
                raise ValueError(
                    f"definition subsection '### {name}' is missing its "
                    f"required $$display equation$$ — every component "
                    f"subsection in a mathematical definition must state its "
                    f"defining formula symbolically (not a word-form "
                    f"pseudo-equation like "
                    f"$$\\text{{Squared bias}}+\\text{{Variance}}$$)."
                )
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest src/services/chat/tests/test_component_equations.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/schemas/output.py src/services/chat/tests/test_component_equations.py
git commit -m "feat(schema): require defining equation per component subsection in math definitions"
```

---

## Task 3: Repair-path integration test

**Files:**
- Test: `src/services/chat/tests/test_component_equations.py`

- [ ] **Step 1: Write the failing test**

First confirm the helper signature. Run:
`grep -n "def _validate_and_repair\|def build_repair_prompt" src/services/chat/orchestrator.py src/services/chat/schemas/output_repair.py`
Expected: `_validate_and_repair(accumulated, spec, llm, model_id)` and `build_repair_prompt(error, schema_json, accumulated)`.

Append to `src/services/chat/tests/test_component_equations.py`:

```python
def test_noncompliant_json_triggers_repair(monkeypatch):
    """A non-compliant DeepTutorAnswer JSON routed through _validate_and_repair
    must trigger exactly one repair call, then validate."""
    import asyncio

    from src.services.chat import orchestrator
    from src.services.chat.schemas.output import DeepTutorAnswer

    bad_def = (
        "We define each component.\n"
        "### Bias\n- prose only, no formula\n"
        "### MSE\n"
        r"$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$" "\n"
    )
    good_def = (
        "We define each component.\n"
        "### Bias\n"
        r"$$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$" "\n"
        "### MSE\n"
        r"$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$" "\n"
    )

    def _payload(definition: str) -> str:
        return DeepTutorAnswer.model_construct(  # bypass validation to emit raw
            tldr="i", definition=definition, formal_statement="",
            example_intuition="e", applications="a", further_reading="f",
            citations=[], math_blocks=[], figures=[],
        ).model_dump_json()

    bad_json = _payload(bad_def)
    good_json = _payload(good_def)

    calls = {"n": 0}

    class _FakeLLM:
        async def stream(self, messages, **kw):
            calls["n"] += 1
            for chunk in (good_json,):
                yield chunk

    class _Spec:
        output_schema = DeepTutorAnswer

    validated, err = asyncio.run(
        orchestrator._validate_and_repair(bad_json, _Spec(), _FakeLLM(), "gpt-5.4-nano-2026-03-17")
    )
    assert err is None
    assert calls["n"] == 1  # exactly one repair call
    assert validated is not None
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `.venv/bin/pytest src/services/chat/tests/test_component_equations.py::test_noncompliant_json_triggers_repair -v`
Expected: PASS (validator from Task 2 makes the first `model_validate_json` raise, repair stream returns `good_json`, second validate passes). If the `_validate_and_repair` / `build_repair_prompt` signatures differ from Step 1, adjust the `_Spec`/call to match the real signature, then re-run.

- [ ] **Step 3: Commit**

```bash
git add src/services/chat/tests/test_component_equations.py
git commit -m "test(schema): repair path backfills missing component equation"
```

---

## Task 4: Prompt nudge — ban word-form pseudo-equations

**Files:**
- Modify: `src/services/chat/prompts/deep_tutor.py` (end of the `definition` per-field block, ~line 221, after "NEVER omit a component's equation.")

- [ ] **Step 1: Read the exact insertion point**

Run: `sed -n '206,222p' src/services/chat/prompts/deep_tutor.py`
Expected: the formulas block ending with `NEVER omit a component's equation.`

- [ ] **Step 2: Add the negative example**

Insert immediately after the line `it as LaTeX, copy it verbatim; otherwise reconstruct it from the prose or` … `NEVER omit a component's equation.` (keep existing text; append within the same bullet, matching the surrounding indentation):

```python
    A word-form "equation" is a FAILURE: never emit
    ``$$\\text{Squared bias}+\\text{Variance}\\approx\\text{Test MSE}$$``.
    Use real symbols — the central-quantity subsection states e.g.
    ``$$\\mathrm{MSE}=\\mathrm{Bias}^2+\\mathrm{Var}+\\sigma^2$$`` and the
    component subsections state e.g.
    ``$$\\mathrm{Bias}(\\hat\\theta)=\\mathbb{E}[\\hat\\theta]-\\theta$$`` and
    ``$$\\mathrm{Var}(\\hat\\theta)=\\mathbb{E}[(\\hat\\theta-\\mathbb{E}[\\hat\\theta])^2]$$``.
```

(Match the literal string-concatenation / quoting style already used in that prompt block — verify with the `sed` output from Step 1 and mirror it exactly.)

- [ ] **Step 3: Verify the prompt still imports/builds**

Run: `.venv/bin/python -c "import src.services.chat.prompts.deep_tutor as m; print('ok')"`
Expected: `ok` (no `SyntaxError`).

- [ ] **Step 4: Commit**

```bash
git add src/services/chat/prompts/deep_tutor.py
git commit -m "feat(prompt): ban word-form pseudo-equations in definition subsections"
```

---

## Task 5: Full suite + lint regression

**Files:** none (verification only)

- [ ] **Step 1: Run the chat test suite**

Run: `.venv/bin/pytest src/services/chat/tests/ -q`
Expected: all pass (new tests included; no regressions). If any prior test constructs a `DeepTutorAnswer` with a math `definition` that has a header-less or formula-bearing layout, confirm it still passes; if a legitimate test now fails because it used a math `###` subsection without `$$`, that test's fixture was itself non-compliant — fix the fixture to include the equation (do NOT weaken the validator).

- [ ] **Step 2: Lint + type check**

Run: `.venv/bin/ruff check src/services/chat/schemas/output.py src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_component_equations.py && .venv/bin/mypy src/services/chat/schemas/output.py`
Expected: clean.

- [ ] **Step 3: Commit any fixups**

```bash
git add -A
git commit -m "test: fixups for component-equation enforcement"
```

---

## Task 6: Docs — changelog + invariant cross-reference

**Files:**
- Modify: `docs/system/changelog.md`
- Modify: `docs/system/invariants.md` (cross-reference only)

- [ ] **Step 1: Append a changelog entry**

Add a dated entry to `docs/system/changelog.md` describing: DeepTutorAnswer now enforces a `$$…$$` defining equation per `### ` subsection in mathematical definitions; non-compliant answers auto-repair via ADR-005; word-form pseudo-equations banned. Reference spec `docs/superpowers/specs/2026-06-05-bias-variance-component-equations-design.md` and conv `9e0a393d`.

- [ ] **Step 2: Cross-reference the invariant**

In `docs/system/invariants.md`, locate invariant 23 and/or 37 (equation preservation) and add a one-line note that DeepTutorAnswer’s `_require_component_equations` validator enforces the per-component-equation half of it at schema time.

- [ ] **Step 3: Commit**

```bash
git add docs/system/changelog.md docs/system/invariants.md
git commit -m "docs: record component-equation enforcement (changelog + invariant xref)"
```

---

## Manual verification (after implementation)

> Blocked until the Claude Chrome extension is reconnected. Then:
> 1. `./scripts/dev.sh` (Qdrant already up).
> 2. Open :5175, ask "What is the bias-variance tradeoff?" with orchestrator-deep + an OpenAI model (nano) — Groq JSON flakiness would mask the fix.
> 3. Confirm `### Bias`, `### Variance`, `### MSE` each render a symbolic `$$…$$` equation and no word-form pseudo-equation appears.
> 4. Note: `data/cost_log.jsonl` is NOT written by the tutor path — don't rely on it.
