---
name: synthesis
description: Integrate multiple authors' briefs into one comparative tutor answer with C-style bodies, component-defining LaTeX formulas ($...$ / $$...$$ math), and explicit author comparison.
---

# Synthesis skill

## When to use
When asked to synthesize author briefs (files under `/briefs/`) into a single tutor answer.

## Instructions
1. List `/briefs/` and READ every `/briefs/*.md` file in full before writing.
2. Write ONE coherent answer with a single throughline — not a per-author concatenation; COMPARE authors explicitly (agree / differ / why).
3. Retain every content-bearing key point; ground every claim in the briefs; never invent sources, formulas, or names. Skip "no-info" briefs.
4. STRUCTURE each subtopic for scanning: a short **bold lead sentence**, then **bold lead-in bullets** (`- **<claim>** — <explanation>`), one claim per line. Never a wall of text.
5. COMPONENT FORMULAS: when the concept decomposes into named components (e.g. bias / variance / MSE), give each component its own `### <Component>` whose first bullet STATES its defining formula inline, then a `### <central quantity>` stating the `$$decomposition$$`. See [formulas.md](references/formulas.md). Take each component's defining equation from the source briefs/bundle: copy it VERBATIM when given as LaTeX, otherwise reconstruct it from the stated definition; never omit it.
6. MATH DELIMITERS: inline `$...$`, display `$$...$$`. NEVER use plain-text math (write `$\alpha$`, not "alpha"); never emit `\(` or `\$(`.
7. Figures: keep any `[Fn]` figure marker from the briefs in the subtopic it belongs to.
