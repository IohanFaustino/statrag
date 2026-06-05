# Deep-Tutor Answer Formatting Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four deep-tutor rendering defects — raw inline-LaTeX leak (A), sentence-breaking display equations (B), orphan citation lines (C), duplicate/low-value figure blocks (D) — with best-effort enforcement that never blanks an answer.

**Architecture:** A is fixed deterministically by strengthening the existing `_wrap_bare_math` post-processor (unicode greek support) plus a prompt rule. B/C are prompt rules. The existing `_require_component_equations` validator is made best-effort via a pydantic validation-context flag + an orchestrator fallback that accepts a structurally-valid-but-format-imperfect answer. D dedupes/caps figures in `_convert_to_tutor_answer`. No frontend change.

**Tech Stack:** Python 3.12, Pydantic v2 (`model_validator` + `ValidationInfo` context), `re`, existing ADR-005 repair infra, pytest.

---

## File Structure

- `src/services/chat/schemas/output.py` — `_require_component_equations` gains a `ValidationInfo` param + `skip_format_checks` gate; import `ValidationInfo`.
- `src/services/chat/orchestrator.py` — `_validate_and_repair` best-effort final fallback.
- `src/services/chat/agents/deep_tutor.py` — `_MATH_TOK` unicode-greek support; `_convert_to_tutor_answer` figure dedupe/cap/drop-generic.
- `src/services/chat/prompts/deep_tutor.py` — A1/B/C prompt rules.
- `src/services/chat/tests/test_tutor_prompt_contract.py` — raise `_PROMPT_BUDGET_CEILING`.
- `src/services/chat/tests/test_component_equations.py` — extend (best-effort + context).
- `src/services/chat/tests/test_deep_tutor.py` — `_wrap_bare_math` + figure tests.

---

## Task 1: Best-effort degrade for the equation validator

**Files:**
- Modify: `src/services/chat/schemas/output.py`
- Modify: `src/services/chat/orchestrator.py`
- Test: `src/services/chat/tests/test_component_equations.py`

- [ ] **Step 1: Write failing tests** — append to `test_component_equations.py`:

```python
def test_skip_format_checks_context_bypasses_equation_validator():
    from src.services.chat.schemas.output import DeepTutorAnswer

    bad = (
        "We define each component.\n"
        "### Bias\n- prose only, no formula\n"
        "### MSE\n"
        r"$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$" "\n"
    )
    payload = DeepTutorAnswer.model_construct(
        tldr="i", definition=bad, formal_statement="", example_intuition="e",
        applications="a", further_reading="f", citations=[], math_blocks=[], figures=[],
    ).model_dump_json()
    # Without context -> raises (math def, ### Bias missing $$)
    with pytest.raises(ValidationError):
        DeepTutorAnswer.model_validate_json(payload)
    # With skip context -> accepted
    obj = DeepTutorAnswer.model_validate_json(payload, context={"skip_format_checks": True})
    assert obj.definition == bad


def test_validate_and_repair_best_effort_accepts_on_repair_failure():
    """When the only defect is the format validator and repair ALSO fails,
    _validate_and_repair returns the imperfect answer (rendered), not an error."""
    import asyncio
    from src.services.chat import orchestrator
    from src.services.chat.schemas.output import DeepTutorAnswer

    bad = (
        "We define each component.\n"
        "### Bias\n- prose only, no formula\n"
        "### MSE\n"
        r"$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$" "\n"
    )
    bad_json = DeepTutorAnswer.model_construct(
        tldr="i", definition=bad, formal_statement="", example_intuition="e",
        applications="a", further_reading="f", citations=[], math_blocks=[], figures=[],
    ).model_dump_json()

    class _FakeLLM:
        async def stream(self, messages, **kw):
            yield bad_json  # repair returns the SAME non-compliant payload

    class _Spec:
        output_schema = DeepTutorAnswer

    validated, err = asyncio.run(
        orchestrator._validate_and_repair(bad_json, _Spec(), _FakeLLM(), "gpt-5.4-nano-2026-03-17")
    )
    assert err is None
    assert validated is not None
    assert "### Bias" in validated["definition"]
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest src/services/chat/tests/test_component_equations.py -k "skip_format or best_effort" -v`
Expected: FAIL — context kwarg ignored (validator still raises) / repair path returns `(None, err)`.

- [ ] **Step 3: Gate the validator** — in `src/services/chat/schemas/output.py`:

Change the pydantic import to include `ValidationInfo`:
```python
from pydantic import BaseModel, Field, ValidationInfo, model_validator
```
Change the validator signature + add the gate as its first lines:
```python
    @model_validator(mode="after")
    def _require_component_equations(self, info: ValidationInfo) -> "DeepTutorAnswer":
        """... (existing docstring) ...

        Best-effort: when validated with ``context={"skip_format_checks": True}``
        this check is skipped (used by the orchestrator's final fallback so a
        format-imperfect answer renders instead of erroring)."""
        if (info.context or {}).get("skip_format_checks"):
            return self
        is_math = bool(self.math_blocks) or "$$" in self.definition
        ...
```
(Keep the rest of the method body unchanged.)

- [ ] **Step 4: Best-effort fallback** — in `src/services/chat/orchestrator.py` `_validate_and_repair`:

Restructure so `text` is computed once and a `repaired_text` default exists, then add the fallback. Replace the function body's first-attempt + repair + final-except with:

```python
    schema_cls = spec.output_schema

    text = accumulated.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    # --- First attempt ---
    try:
        obj = schema_cls.model_validate_json(text)
        return obj.model_dump(), None
    except (ValidationError, Exception) as first_err:
        first_error_str = str(first_err)

    # --- Repair attempt ---
    schema_json = json.dumps(schema_cls.model_json_schema(), indent=2)
    repair_prompt = build_repair_prompt(first_error_str, schema_json, accumulated)
    repair_messages: list[ChatMessage] = [ChatMessage(role="user", content=repair_prompt)]
    repaired_text = ""
    try:
        repaired = ""
        async for chunk in llm.stream(repair_messages, model=model_id):
            repaired += chunk
        repaired_text = repaired.strip()
        if repaired_text.startswith("```"):
            lines = repaired_text.splitlines()
            repaired_text = "\n".join(lines[1:-1]) if len(lines) > 2 else repaired_text
        obj = schema_cls.model_validate_json(repaired_text)
        return obj.model_dump(), None
    except (ValidationError, Exception) as second_err:
        # Best-effort: if the answer is structurally valid and only a soft
        # FORMAT validator failed, accept it (render imperfect) rather than
        # blanking the turn. context={"skip_format_checks": True} bypasses only
        # DeepTutorAnswer's format validators; other schemas ignore it.
        for candidate in (repaired_text, text):
            if not candidate:
                continue
            try:
                obj = schema_cls.model_validate_json(
                    candidate, context={"skip_format_checks": True}
                )
                return obj.model_dump(), None
            except Exception:
                continue
        return None, str(second_err)
```

- [ ] **Step 5: Run tests** — `.venv/bin/pytest src/services/chat/tests/test_component_equations.py -v` → all pass (prior 14 + 2 new = 16).

- [ ] **Step 6: Commit**
```bash
git add src/services/chat/schemas/output.py src/services/chat/orchestrator.py src/services/chat/tests/test_component_equations.py
git commit -m "feat(schema): best-effort format validation — render imperfect answer instead of blanking"
```

---

## Task 2: Strengthen `_wrap_bare_math` for unicode greek (defect A)

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py` (the `_MATH_TOK` constant)
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Write failing test** — append to `src/services/chat/tests/test_deep_tutor.py`:

```python
def test_wrap_bare_math_wraps_unicode_greek_latex_run():
    from src.services.chat.agents.deep_tutor import _wrap_bare_math

    # The exact leak observed in conv on :5175 — \tilde + unicode greek mixed.
    s = r"running a simple regression: \tilde y=\tilde β_0+\tilde β_1 x_1."
    out = _wrap_bare_math(s)

    # No LaTeX backslash command may remain OUTSIDE a $...$ span.
    import re
    stripped = re.sub(r"\$\$[^$]+\$\$|\$[^$]+\$", "", out)
    assert "\\tilde" not in stripped, f"raw LaTeX leaked: {out!r}"
    assert "$" in out


def test_wrap_bare_math_leaves_plain_prose_untouched():
    from src.services.chat.agents.deep_tutor import _wrap_bare_math
    s = "The model omits a relevant variable and induces bias."
    assert _wrap_bare_math(s) == s
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest src/services/chat/tests/test_deep_tutor.py -k wrap_bare_math -v`
Expected: `test_wrap_bare_math_wraps_unicode_greek_latex_run` FAILS (raw `\tilde` remains because the run breaks on unicode `β`).

- [ ] **Step 3: Add a unicode-greek token alternative to `_MATH_TOK`**

In `src/services/chat/agents/deep_tutor.py`, locate `_MATH_TOK = (` and add a new alternative inside the `(?: … )` group — right after the "isolated single math letter" alternative — so greek letters (and the unicode minus / middle dot) count as math tokens that a run can bridge:

```python
    r"|"
    # unicode Greek-and-Coptic block (U+0370-U+03FF: covers alpha-omega incl.
    # beta theta sigma lambda mu) + unicode minus (U+2212), middle dot
    # (U+00B7), combining circumflex/hat (U+0302). The `re` module parses
    # \uXXXX escapes even from raw strings. Models emit these interleaved with
    # \commands, which used to break the run and leak raw LaTeX.
    r"[Ͱ-Ͽ−·̂]"
```

> IMPORTANT for the implementer: write the character class using the
> backslash-`u` escapes EXACTLY as shown (`Ͱ-Ͽ−·̂`),
> NOT literal Greek glyphs — `Ͱ-Ͽ` is the Greek-and-Coptic block
> (includes β=U+03B2), `−` minus, `·` middle-dot, `̂` combining hat.

(Place it as a sibling alternative before the closing `r")"`. Do not change `_MATH_RUN_RE`. Verify with the Task-2 test that `β` (U+03B2, which IS inside U+0370–U+03FF) is now bridged.)

- [ ] **Step 4: Run tests** — `.venv/bin/pytest src/services/chat/tests/test_deep_tutor.py -k wrap_bare_math -v` → both pass. Then run the whole file: `.venv/bin/pytest src/services/chat/tests/test_deep_tutor.py -q` → no regressions.

- [ ] **Step 5: Commit**
```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "fix(tutor): _wrap_bare_math bridges unicode-greek+LaTeX runs so inline math no longer leaks raw"
```

---

## Task 3: Prompt rules A1/B/C + raise prompt budget

**Files:**
- Modify: `src/services/chat/prompts/deep_tutor.py` (`DEEP_TUTOR_INSTRUCTIONS`, math/citation guidance)
- Modify: `src/services/chat/tests/test_tutor_prompt_contract.py` (budget ceiling)
- Test: `src/services/chat/tests/test_tutor_prompt_contract.py`

- [ ] **Step 1: Raise the budget ceiling + add presence test**

In `src/services/chat/tests/test_tutor_prompt_contract.py`, change:
```python
_PROMPT_BUDGET_CEILING = 19_200
```
to:
```python
_PROMPT_BUDGET_CEILING = 20_500
```
And add a new test in the same file:
```python
def test_deep_tutor_inline_delimiter_rule_present():
    from src.services.chat.prompts.deep_tutor import DEEP_TUTOR_INSTRUCTIONS as INSTR
    low = INSTR.lower()
    assert "wrap" in low and ("$…$" in INSTR or "$...$" in INSTR or "inline" in low)
    # bans bare commands / dangling citation after display block
    assert "bare" in low or "undelimited" in low
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest src/services/chat/tests/test_tutor_prompt_contract.py -k "inline_delimiter" -v`
Expected: FAIL (rule text not present yet).

- [ ] **Step 3: Read the math/citation block + insert rules**

Run `sed -n '180,232p' src/services/chat/prompts/deep_tutor.py` to find the `definition` math block and the math_format guidance. Mirror the existing 4-backslash source convention. Insert these compact rules (adapt placement to the math-format section; keep terse):

```python
    DELIMIT ALL MATH: every symbol or expression in prose MUST be wrapped —
    inline ``$…$`` or display ``$$…$$``. NEVER write a bare LaTeX command
    (``\\tilde``, ``\\hat``, ``\\beta``), a bare subscript/superscript
    (``x_1``, ``a^2``), or mix unicode glyphs (β, θ) with ``\\commands`` in one
    expression. A bare ``\\command`` in prose is a FAILURE.
    INLINE vs DISPLAY: a defining equation that completes a sentence is INLINE
    ``$…$`` so the prose flows; reserve ``$$…$$`` for standalone decompositions
    on their own line. Do not leave a dangling ``". [N]"`` after a display
    block — end the sentence AND place its ``[N]`` citation BEFORE the block,
    never alone on the line after ``$$…$$``.
```

- [ ] **Step 4: Verify import + budget + presence**

Run:
```bash
.venv/bin/python -c "import src.services.chat.prompts.deep_tutor as m; print(len(m.DEEP_TUTOR_INSTRUCTIONS))"
.venv/bin/pytest src/services/chat/tests/test_tutor_prompt_contract.py -q
```
Expected: char count < 20500; all prompt-contract tests pass (budget + new presence test + existing `### bias`/`### mse`/`centered display equations` assertions). If over 20500, compress the inserted wording (not the ceiling).

- [ ] **Step 5: Commit**
```bash
git add src/services/chat/prompts/deep_tutor.py src/services/chat/tests/test_tutor_prompt_contract.py
git commit -m "feat(prompt): delimit-all-math + inline-vs-display + citation-placement rules (budget 19200->20500)"
```

---

## Task 4: Figure dedupe / cap-per-aspect / drop-generic (defect D)

**Files:**
- Modify: `src/services/chat/agents/deep_tutor.py` (`_convert_to_tutor_answer`, the `figs_for_text` / `per_target` block ~lines 2120-2168)
- Test: `src/services/chat/tests/test_deep_tutor.py`

- [ ] **Step 1: Read the block** — `sed -n '2118,2170p' src/services/chat/agents/deep_tutor.py` to confirm current variable names (`figs_for_text`, `per_target`, `_choose_target_aspect`, `blocks`).

- [ ] **Step 2: Write failing test** — append to `src/services/chat/tests/test_deep_tutor.py`:

```python
def test_convert_dedupes_and_caps_figures_per_aspect():
    from src.services.chat.agents.deep_tutor import _convert_to_tutor_answer
    from src.services.chat.schemas.output import DeepTutorAnswer, FigureRef

    deep = DeepTutorAnswer(
        tldr="t", definition="d", formal_statement="", example_intuition="e",
        applications="a", further_reading="f", citations=[], math_blocks=[], figures=[],
    )
    aspects = {k: v for k, v in (
        ("tldr", "t"), ("definition", "d"), ("formal_statement", ""),
        ("example_intuition", "e"), ("applications", "a"), ("further_reading", "f"),
    )}
    figs = [
        FigureRef(ref="r1", book="islp", chapter="ch02", caption="bias variance plot",
                  url="/api/figures?path=a.jpg", judge_confidence=0.9,
                  judge_reason="plots bias and variance vs flexibility", figure_role="other"),
        FigureRef(ref="r2", book="islp", chapter="ch02", caption="",
                  url="/api/figures?path=b.jpg", judge_confidence=0.4,
                  judge_reason="The image visually represents the bias-variance tradeoff, which is relevant to the query.",
                  figure_role="other"),
    ]
    ans = _convert_to_tutor_answer(deep, aspects, sources=[], approved_figures=figs)
    # Exactly one "### Figure example" block across the whole answer.
    total = sum(v.count("### Figure example") for v in ans.aspects.values())
    assert total == 1, ans.aspects
```

- [ ] **Step 3: Run, verify failure** — `.venv/bin/pytest src/services/chat/tests/test_deep_tutor.py -k convert_dedupes -v` → FAIL (two figure blocks emitted).

- [ ] **Step 4: Implement dedupe + cap + drop-generic**

In `_convert_to_tutor_answer`, immediately after `figs_for_text` is computed and before the `per_target` loop, add dedupe-by-ref/url and a generic-caption filter; and in the `per_target` build, cap to the single highest-`judge_confidence` figure per target. Concretely:

(a) Add a module-level helper near `_wrap_bare_math` (top-level, before `_convert_to_tutor_answer`):
```python
_GENERIC_FIG_RE = re.compile(
    r"the image visually represents|which is relevant to the query"
    r"|the image illustrates",
    re.IGNORECASE,
)


def _is_generic_figure(f, vision_explanations: dict[str, str] | None) -> bool:
    """A figure whose only 'explanation' is a boilerplate judge/vision line
    that adds no specific content — drop it from the rendered answer."""
    url = getattr(f, "url", "") or ""
    text = ((vision_explanations or {}).get(url, "") or "") \
        + " " + (getattr(f, "judge_reason", "") or "") \
        + " " + (getattr(f, "caption", "") or "")
    has_specific = bool((getattr(f, "caption", "") or "").strip())
    return _GENERIC_FIG_RE.search(text) is not None and not has_specific
```

(b) Right after `figs_for_text = ...` is assigned, dedupe + drop generic:
```python
    # Dedupe by ref/url and drop boilerplate-only figures (defect D).
    _seen: set[str] = set()
    _deduped = []
    for f in figs_for_text:
        key = (getattr(f, "ref", "") or getattr(f, "url", "") or "")
        if key in _seen:
            continue
        _seen.add(key)
        if _is_generic_figure(f, vision_explanations):
            continue
        _deduped.append(f)
    figs_for_text = _deduped
```

(c) In the `per_target` loop, cap to one figure per target — replace `for f in figs:` iteration setup with a single best figure:
```python
        for target, figs in per_target.items():
            base = final_aspects.get(target, "").rstrip()
            blocks: list[str] = []
            # Cap: one figure block per aspect — keep highest judge_confidence.
            figs = sorted(
                figs, key=lambda f: float(getattr(f, "judge_confidence", 0.0) or 0.0),
                reverse=True,
            )[:1]
            for f in figs:
                ...  # (existing block-building body unchanged)
```

- [ ] **Step 5: Run tests** — `.venv/bin/pytest src/services/chat/tests/test_deep_tutor.py -q` → pass, no regressions.

- [ ] **Step 6: Commit**
```bash
git add src/services/chat/agents/deep_tutor.py src/services/chat/tests/test_deep_tutor.py
git commit -m "fix(tutor): dedupe figures, cap one per aspect, drop boilerplate-caption figures"
```

---

## Task 5: Full suite + lint

**Files:** none (verification)

- [ ] **Step 1: Full chat suite** — `.venv/bin/pytest src/services/chat/tests/ -q`
Expected: all pass (≈733+). If a prior test asserted the old budget 19200 or relied on 2 figure blocks, fix that test's expectation to match the new intended behavior (do NOT weaken the fix).

- [ ] **Step 2: Lint** — `~/.local/bin/ruff check src/services/chat/schemas/output.py src/services/chat/orchestrator.py src/services/chat/agents/deep_tutor.py src/services/chat/prompts/deep_tutor.py`
Expected: clean.

- [ ] **Step 3: Commit any fixups**
```bash
git add -A && git commit -m "test: fixups for deep-tutor formatting fixes"
```

---

## Task 6: Docs — changelog + invariant cross-reference

**Files:**
- Modify: `docs/system/changelog.md`
- Modify: `docs/system/invariants.md`

- [ ] **Step 1: Changelog entry (top, dated 2026-06-05)** describing: best-effort format validation (skip_format_checks context + orchestrator fallback → render imperfect, never blank); `_wrap_bare_math` unicode-greek support (inline-LaTeX leak fix); prompt rules (delimit-all-math, inline-vs-display, citation placement; budget 19200→20500); figure dedupe/cap-per-aspect/drop-generic. Reference spec `docs/superpowers/specs/2026-06-05-deep-tutor-formatting-fixes-design.md`.

- [ ] **Step 2: Invariant cross-refs** — in `docs/system/invariants.md`: (a) note on invariant 23 that the equation validator is now best-effort (skip_format_checks); (b) note on invariant 24 (citation/subsection layout) that `_wrap_bare_math` wraps unicode-greek+LaTeX runs and figures are deduped/capped one-per-aspect.

- [ ] **Step 3: Commit**
```bash
git add docs/system/changelog.md docs/system/invariants.md
git commit -m "docs: record deep-tutor formatting fixes (best-effort, math wrap, prompt rules, figures)"
```

---

## Manual verification (after implementation)

> On :5175 (dev.sh running), Tutor + orchestrator-deep + nano (use the (i) modal Default if a stage is on Groq): ask "What is the bias-variance tradeoff?" and confirm: (1) no raw `\tilde`/`x_1` in Case 1 — inline math renders; (2) Bias/Variance defining eqs read inline without an orphan ". [N]"; (3) no `[N]` alone on a line after a display block; (4) at most one "Figure example" block per section, no generic-caption figure.
