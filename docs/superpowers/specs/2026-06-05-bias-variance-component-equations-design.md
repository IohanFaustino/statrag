# Bias-Variance Per-Component Equation Enforcement — Design

## Goal

Force every component `### ` subsection inside a *mathematical* `definition`
aspect of a deep-tutor answer to carry a real `$$…$$` defining equation, and
reject + auto-repair answers that omit it. Fixes conv `9e0a393d`
("What is the bias-variance tradeoff?"), where `### Bias` and `### Variance`
rendered as prose with no defining equation, and a word-form pseudo-equation
(`Squared bias + Variance ≈ Test MSE`) appeared in place of a symbolic one.

## Architecture

The deep-tutor synthesizer emits a `DeepTutorAnswer` JSON which the orchestrator
validates post-stream at `orchestrator.py:403` via `_validate_and_repair`
(ADR-005). On a `ValidationError` it runs one free-form schema-repair LLM call
(`build_repair_prompt(err)`). We add a Pydantic `model_validator` to
`DeepTutorAnswer` that raises when a mathematical `definition` has a `### `
subsection without a `$$…$$` block — turning the existing (but currently
inert) repair path into the enforcement mechanism. Native `response_format`
constrained decoding (ADR-008) guarantees only JSON validity, not this semantic
rule, so the validator can still fail under structured output and trigger
repair. No frontend change — `definition` stays a markdown string.

## Tech stack

Python 3.12, Pydantic v2 (`model_validator(mode="after")`), existing
ADR-005 repair infra. Tests: pytest under `src/services/chat/tests/`.

## Components

### 1. Schema validator — `src/services/chat/schemas/output.py`

Add `@model_validator(mode="after")` `_require_component_equations` to
`DeepTutorAnswer`:

- **Math-answer gate.** Enforce only when the answer is mathematical:
  `bool(self.math_blocks)` OR `"$$" in self.definition`. Otherwise no-op
  (pure-conceptual answers — e.g. "what is overfitting?" — are exempt).
- **Per-subsection rule.** Split `definition` on lines beginning `### `. For
  each subsection body, require at least one `$$…$$` display block. First
  offender raises:
  `ValueError("definition subsection '### {name}' is missing its required $$display equation$$ — every component subsection in a mathematical definition must state its defining formula symbolically")`.
- **Pseudo-equation ban.** A `$$…$$` whose body contains no mathematical
  symbol (only words, `\text{}`, whitespace, and connective glyphs like
  `≈`/`\approx`/`+`) does NOT count as an equation and is rejected with a
  message directing the repair to use real symbols
  (e.g. `\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2`). "Has a math
  symbol" = contains a backslash-command other than `\text`/`\approx`, or any
  of `=^_\\frac\\hat\\mathbb\\mathrm\\sigma\\theta` etc., or a digit/greek.
- **Robustness.** Gating + "no `### ` headers ⇒ no-op" keep directly
  constructed fallbacks (`_wrap_text_answer`, degraded paths with empty or
  header-less `definition`) from raising.

### 2. Prompt nudge — `src/services/chat/prompts/deep_tutor.py`

In the `definition` per-field block (~lines 206-221), add one explicit negative
example: word-form pseudo-equations such as `Squared bias + Variance ≈ Test MSE`
are a FAILURE. The central-quantity subsection must show the symbolic
decomposition (`$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$`), and
`### Bias` / `### Variance` must each show their symbolic defining equation
(`$$\mathrm{Bias}(\hat\theta)=\mathbb{E}[\hat\theta]-\theta$$`,
`$$\mathrm{Var}(\hat\theta)=\mathbb{E}[(\hat\theta-\mathbb{E}[\hat\theta])^2]$$`).

## Data flow

```
synth → DeepTutorAnswer JSON (accumulated_text)
      → orchestrator.py:403 _validate_and_repair
        → DeepTutorAnswer.model_validate_json
          → _require_component_equations raises (math def, missing $$)
        → build_repair_prompt(err) → one free-form repair call backfills eqs
      → validated → structured_output event → streamed
```

## Error handling

- Validator raises `ValueError` (Pydantic wraps as `ValidationError`) → caught
  by `_validate_and_repair`'s existing try/except → single repair attempt.
- If repair still fails, the orchestrator emits the existing
  `SchemaValidationError` error event — no new failure mode introduced.
- Fallback constructors never raise (gating).

## Testing

`src/services/chat/tests/test_*.py`:

1. Math `definition` with `### Variance` lacking `$$` → `ValidationError`.
2. Same definition with each subsection carrying a `$$` → valid.
3. Pure-conceptual answer (no `math_blocks`, no `$$`) with header-less or
   formula-free `### ` subsections → valid (no-op gate).
4. Pseudo-equation `$$\text{Squared bias}+\text{Variance}\approx\text{Test MSE}$$`
   → rejected; symbolic `$$\mathrm{MSE}=\mathrm{Bias}^2+\mathrm{Var}+\sigma^2$$`
   → accepted.
5. `_wrap_text_answer` / empty-`definition` construction → does not raise.
6. (integration) Non-compliant `DeepTutorAnswer` JSON routed through
   `_validate_and_repair` triggers exactly one repair call.

## Out of scope

Per the chosen narrow scope: formula-recovery rewiring, worker
preserve-equations, frontend rendering, and any new `component_equations`
schema field. This change is synth prompt + schema only.

## Lockstep artifacts

Synth-internal validation + prompt; no pipeline-stage graph node changes, so
`tutorPipeline.ts` / `PipelineDiagram.tsx` / the 36-deep-tutor mermaid are
unaffected. Update `docs/system/changelog.md` and, if an invariant codifies
"every component subsection states its defining equation," cross-reference
invariant 23/37 in `docs/system/invariants.md`.
