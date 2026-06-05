# Deep-Tutor Answer Formatting Fixes — Design

## Goal

Eliminate four rendering/formatting defects observed in the live deep-tutor
answer (conv on :5175, "What is the bias-variance tradeoff?"), with
**best-effort** enforcement that never converts a renderable answer into
"Failed to generate":

- **A. Raw inline-LaTeX leak** — an inline expression emitted without `$…$`
  delimiters renders as literal source (`\tilde y=\tilde β₀+\tilde β₁ x_1.`).
- **B. Sentence-breaking display equations** — short, sentence-completing
  defining equations emitted as `$$…$$`, leaving an orphan `" . [N]"`.
- **C. Orphan citation lines** — a `[N]` marker placed right after a `$$` block
  wraps onto its own line.
- **D. Duplicate / low-value figure blocks** — two near-duplicate `### Figure
  example` blocks for the same aspect, the second with a generic caption.

Display math itself (`$$…$$`) renders correctly; the problems are inline math,
layout, and figure assembly.

## Architecture

Defects A/B/C are *generation* problems → fixed with (1) prompt rules and
(2) a schema-time **leak validator** that, like the existing
`_require_component_equations`, raises so the orchestrator's ADR-005
`_validate_and_repair` runs one repair pass. Both format validators become
**best-effort**: gated by a pydantic validation `context` flag, so a final
fallback in `_validate_and_repair` accepts the imperfect-but-structurally-valid
answer instead of erroring. Defect D is an *assembly* problem → fixed in
`_explain_figures` (dedupe + cap one figure block per aspect + drop
generic-caption figures). No frontend change.

## Tech stack

Python 3.12, Pydantic v2 (`model_validator(mode="after")` with `ValidationInfo`
context), `re`, existing ADR-005 repair infra, pytest.

## Components

### 1. Prompt rules — `src/services/chat/prompts/deep_tutor.py`

In `DEEP_TUTOR_INSTRUCTIONS` (math-format / citation guidance):
- **A1 (delimit all math):** EVERY mathematical token in prose MUST be wrapped
  — inline `$…$`, display `$$…$$`. Never write a bare LaTeX command
  (`\tilde`, `\hat`, `\beta`, …), a bare subscript/superscript (`x_1`, `a^2`),
  or mix unicode math glyphs with LaTeX commands in one expression. A bare
  `\command` in prose is a failure.
- **B (inline vs display):** a defining equation that completes a sentence is
  **inline `$…$`** so the prose flows; reserve `$$…$$` for standalone
  decompositions on their own line. Do not leave a dangling `" . [N]"` after a
  display block — end the sentence (and its citation) *before* the block.
- **C (citation placement):** put `[N]` at the end of the text clause that
  *precedes* a display equation, never alone after `$$…$$`.

Backslash-escaping follows the block's existing 4-backslash source convention.
**Prompt budget:** `DEEP_TUTOR_INSTRUCTIONS` is at 19195/19200 chars; these
additions exceed it. Raise `_PROMPT_BUDGET_CEILING` in
`tests/test_tutor_prompt_contract.py` to **20500** (documented bump — the new
rules are load-bearing, not duplication) and keep the additions terse.

### 2a. Deterministic render fix for A — `src/services/chat/agents/deep_tutor.py`

The leak is the model mixing **unicode greek (`β`, `θ`, `σ`) with LaTeX
commands** (`\tilde`, `x_1`) in undelimited prose. `_convert_to_tutor_answer`
already post-processes each aspect with `_repair_latex_post` + `_wrap_bare_math`,
but `_wrap_bare_math`'s token regex (`_MATH_TOK`/`_MATH_RUN_RE`) breaks on
unicode greek, so a run like `\tilde y=\tilde β_0+\tilde β_1 x_1` is left raw.
**Fix:** extend `_MATH_TOK` to treat common unicode greek letters
(`α β γ δ ε θ λ μ σ τ φ ω Σ Π Δ Ω` …) and the unicode minus/middle-dot as math
tokens so a mixed run is recognized and wrapped as one `$…$` span. This is the
primary, deterministic fix (works regardless of model, no extra LLM call). The
proposed standalone leak *validator* is dropped — under best-effort it would not
change the render, and `_wrap_bare_math` fixes it deterministically.

### 2b. Schema best-effort gate — `src/services/chat/schemas/output.py`

- **Best-effort gate** on the existing `_require_component_equations`: take
  `ValidationInfo` and first check
  `if (info.context or {}).get("skip_format_checks"): return self`. Normal
  construction enforces; the final fallback passes the flag to bypass *only*
  this format check (required-fields/types still enforced). This removes the
  hard-fail availability risk observed when the one repair could not comply.

### 3. Orchestrator best-effort fallback — `src/services/chat/orchestrator.py`

In `_validate_and_repair`, before returning `(None, second_err)`: attempt a
**format-skipping** parse on the best available text (repaired text, else the
original `accumulated`):

```
try:
    obj = schema_cls.model_validate_json(best_text, context={"skip_format_checks": True})
    return obj.model_dump(), None      # best-effort: render imperfect answer
except Exception:
    return None, str(second_err)        # real structural failure → error as before
```

The `context` only affects `DeepTutorAnswer`'s two format validators; other
schemas ignore it. Result: format defects degrade to a rendered (imperfect)
answer; structural defects still surface the existing `SchemaValidationError`.

### 4. Figure assembly (D) — `src/services/chat/agents/deep_tutor.py` `_explain_figures`

- **Dedupe** figures by `ref` (and by near-identical url) before explaining.
- **Cap one figure block per aspect** — explain only the highest
  `judge_confidence` figure for a given `aspect_hint`; drop the rest.
- **Drop generic captions** — skip a figure whose explanation/vision text
  matches a generic template (e.g. starts with "The image visually represents"
  / "which is relevant to the query") and adds no specific content.

## Data flow

```
synth → DeepTutorAnswer JSON
  → orchestrator._validate_and_repair
     → model_validate_json (enforces format)  ── fail ─▶ repair call
        → model_validate_json (enforces)       ── fail ─▶ skip_format_checks parse
           → pass → render imperfect (best-effort)
           → fail → SchemaValidationError (structural)
figures → _explain_figures: dedupe + cap-per-aspect + drop-generic → ≤1 block/aspect
```

## Error handling

- Format validators raise `ValueError` → ADR-005 repair → best-effort accept.
- No new hard-failure mode; a previously-renderable answer always renders.
- Figure dedupe is pure list filtering; empty → no figure block (today's
  behavior).

## Testing

`src/services/chat/tests/test_component_equations.py` (extend) +
`test_tutor_prompt_contract.py` + a figure test:
1. `_no_raw_latex_leak`: aspect with bare `\tilde y=\tilde\beta_0` → reject;
   same wrapped in `$…$` → valid; prose with no LaTeX → valid.
2. Best-effort: a non-compliant `DeepTutorAnswer` JSON whose only defect is a
   format-validator failure, routed through `_validate_and_repair` with a repair
   stream that ALSO fails → returns a non-None dict (rendered), not an error.
3. Context flag: `DeepTutorAnswer.model_validate_json(bad, context={"skip_format_checks": True})`
   succeeds; without context raises.
4. Prompt budget: `len(DEEP_TUTOR_INSTRUCTIONS) < 20500`; the new rule substrings
   are present.
5. Figure: `_explain_figures` with two same-aspect figures → one block; a
   generic-caption figure → dropped.

## Out of scope

Frontend render sanitizer (A layer-3, deferred — best-effort backend covers it);
the `component_equations` structured field; image-judge model changes.

## Lockstep artifacts

Validators + prompt + orchestrator fallback are synth-internal (no pipeline
graph node added) → `tutorPipeline.ts` / mermaid unchanged. The figure-assembly
change (D) is within the existing vision-explain stage (no new node). Update
`docs/system/changelog.md` and cross-reference invariant 23 (formulas) +
invariant 24 (citation/subsection layout). Add a per-feature note if warranted.
