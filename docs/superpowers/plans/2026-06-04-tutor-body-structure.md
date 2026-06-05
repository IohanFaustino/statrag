# Tutor In-Body C-Style Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each tutor `###` subsection body render as scannable Option-C text (bold lead + bold-lead-in bullets) with display math and figure markers placed inside the pertinent subtopic (esp. each Example case), without changing `##`/`###` layout, schema, or frontend.

**Architecture:** Pure prompt/skill change. Rewrite the body-format directives in the deep-tutor draft/synth system prompt and the L3b deepagents synthesis SKILL; the `TutorView` parser already renders `**bold**`, `- bullets`, `$…$`/`$$…$$`, `![](url)`. Lock the new contract with prompt-contract tests. Verify (not rebuild) the figure-attach path. Update invariant/changelog/feature docs in lockstep.

**Tech Stack:** Python 3.12, pytest. Prompt strings in `src/services/chat/prompts/deep_tutor.py`; deepagents skill markdown; gpt-5.4-nano governs synth/workers (unchanged).

---

## File Structure

- `src/services/chat/prompts/deep_tutor.py` — owns the draft/synth body-format directives (`<structure>`, `<math_format>`, `<figures>`, per-aspect rules). Primary change.
- `src/services/chat/tests/test_tutor_prompt_contract.py` — locks the format contract. Updated in lockstep (TDD gate).
- `src/services/chat/agents/ow_skills/synthesis/SKILL.md` — L3b synthesis body rules. Secondary change.
- `src/services/chat/tests/test_ow_harness.py` — add SKILL.md contract assert.
- `src/services/chat/agents/orchestrator_workers.py` / `ow_deepagents.py` — figure-bundle + schema-fill; **read-only verification** (no change unless a wiring gap is found).
- `docs/system/invariants.md`, `docs/system/changelog.md`, `docs/services/chat-features/56-deep-synthesis-l3b.md`, `docs/services/chat-features/36-deep-tutor.md` — docs lockstep.

No frontend file, no `tutorPipeline.ts`/`PipelineDiagram.tsx`, no schema file (no stage/schema change).

---

## Task 1: Flip the prompt-contract test to the C-style contract

**Files:**
- Modify: `src/services/chat/tests/test_tutor_prompt_contract.py:36-55`

- [ ] **Step 1: Update `test_structure_requires_subsection_headers` to the new contract**

Replace the body of the test (lines 36-55) with:

```python
def test_structure_requires_subsection_headers():
    assert "wall of text" in INSTR
    # ### H3 headers remain the backbone of each aspect body
    assert "left-aligned subsection headers" in INSTR
    # C-style: inside each ### subsection, use bold-lead-in bullets, one per claim
    assert "bold lead-in bullets" in INSTR
    assert "one claim per line" in INSTR
    # the old prose mandate is gone — no flat 3-5 sentence paragraph rule,
    # no blanket bullet ban
    assert "3-5 sentences" not in INSTR
    assert "not bullet lists" not in INSTR
    # definition gets a ### per component and a ### for the central quantity
    assert "### bias" in INSTR
    assert "### mse" in INSTR
    # component/decomposition formulas must be CENTERED DISPLAY equations ($$)
    assert "centered display equations" in INSTR
    assert "not inline" in INSTR
    # density: bullets must stay substantive and explain where the concept fits
    assert "depth over brevity" in INSTR
    assert "where it fits" in INSTR
    # draft is invited to be extensive — ranges are minimums, not caps
    assert "be extensive" in INSTR
    assert "minimums, not caps" in INSTR
```

- [ ] **Step 2: Add a math-placement + figure-in-example contract test**

Append after `test_structure_requires_subsection_headers`:

```python
def test_math_and_figures_placed_in_subsection():
    # display math is placed inside the ### subsection it belongs to,
    # never piled at the end
    assert "inside the" in INSTR and "subsection it belongs to" in INSTR
    # each Example case states its formula and carries its figure marker
    # within that case's subsection
    assert "each example" in INSTR
    assert "in that same subsection" in INSTR or "within that same subsection" in INSTR
```

- [ ] **Step 3: Run the tests, verify they FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_prompt_contract.py::test_structure_requires_subsection_headers src/services/chat/tests/test_tutor_prompt_contract.py::test_math_and_figures_placed_in_subsection -v`
Expected: FAIL — `assert "bold lead-in bullets" in INSTR` (and the new placement phrases) not yet present.

- [ ] **Step 4: Commit**

```bash
git add src/services/chat/tests/test_tutor_prompt_contract.py
git commit -m "test(tutor): C-style body contract — bold-lead-in bullets + in-subsection math/figures"
```

---

## Task 2: Rewrite the body-format directives in the draft/synth prompt

**Files:**
- Modify: `src/services/chat/prompts/deep_tutor.py` — `<structure>` block (307-333), `<math_format>` (372-386), `<figures>` (388-406), and the per-aspect "3-5 sentence paragraph" phrasings in 150-300.

- [ ] **Step 1: Replace the `<structure>` block**

Replace lines 307-333 (the entire `<structure>…</structure>`) with:

```python
<structure>
- Never emit a wall of text. Each aspect body keeps LEFT-ALIGNED SUBSECTION
  HEADERS using Markdown ``### `` (H3) as its BACKBONE — one ``### Subheader``
  per perspective/part of the aspect (prefer 2-4 per aspect). The ``### ``
  headers are the structure; never collapse an aspect into a single flat
  paragraph.
- INSIDE each ``### `` subsection, write SCANNABLE text, not a dense block:
  - Open with ONE short BOLD lead sentence naming the point.
  - Then BOLD LEAD-IN BULLETS — ``- **<claim>** — <explanation> [N]`` — ONE
    CLAIM PER LINE, with the ``[N]`` citation marker at the end of the line the
    source supports. Bullets must be SUBSTANTIVE — carry the same depth a full
    paragraph would, not one-word fragments (DEPTH OVER BREVITY).
  - Keep a genuinely continuous argument as a 1-2 sentence prose run between
    bullets; use bullets for the enumerable/claim parts and prose for the
    connective tissue. Explain the mechanism and WHERE IT FITS.
- Concretely (see the per-field rules above for the full spec):
  - ``definition`` → ``### `` per component + one for the central quantity
    (e.g. ``### Bias``, ``### Variance``, ``### MSE``); each subsection's
    bullets define the quantity and its role.
  - ``applications`` → one ``### `` per concrete cited case (name the case in
    the header, e.g. ``### Ridge vs. OLS on the prostate data``).
  - ``example_intuition`` → keep its three-move shape; one ``### `` per case
    plus a final ``### The intuition``. EACH EXAMPLE case states the
    ``$$display formula$$`` of its DGP/model IN THAT SAME SUBSECTION and carries
    any ``[Fn]`` figure marker for that case (see <math_format>, <figures>).
  - ``further_reading`` → a short ``### Adjacent concepts`` and an
    ``### Open questions`` block.
- ``### `` headers are SHORT (≤ 6 words), left-aligned, no trailing colon,
  no bold. The opening framing sentence of the aspect comes BEFORE the first
  ``### ``.
- For a genuine ordered procedure or derivation inside a subsection, a short
  ``1.``/``2.`` numbered list is still allowed; reserve it for true sequences.
- Ranges given above are MINIMUMS, NOT CAPS — you are invited to BE EXTENSIVE.
</structure>
```

- [ ] **Step 2: Add the placement rule to `<math_format>`**

Inside the `<math_format>` block (after the line `- Display math: ``$$y = X\\beta + \\varepsilon$$``` at ~374), add:

```python
- PLACEMENT: put each ``$$display$$`` block INSIDE the ``### `` subsection it
  belongs to — these are CENTERED DISPLAY EQUATIONS ($$), NOT INLINE. Each
  Example ``### Case`` states its model/DGP formula in that case's subsection.
  Never collect formulas at the end of the answer.
```

(Keep the existing "centered display equations" / "not inline" wording elsewhere if present; this line guarantees both phrases survive for the contract test.)

- [ ] **Step 3: Add the figure-in-example rule to `<figures>`**

Inside the `<figures>` block (after the "CONNECT the figure…" bullet at ~399), add:

```python
- An Example ``### Case`` that has an approved figure carries BOTH the case's
  ``$$formula$$`` AND the ``[Fn]`` marker WITHIN THAT SAME SUBSECTION, so the
  formula, its figure, and the explanation sit together.
```

- [ ] **Step 4: Relax the per-aspect prose mandate (150-300)**

Find every directive that mandates flat prose / bans bullets in a subsection body and convert it to the C rule:

Run: `.venv/bin/grep -n "3-5 sentence\|3-5 sentences\|SUBSTANTIVE paragraph\|Do NOT use \`\`- \`\`\|not bullet lists\|paragraph of 3" src/services/chat/prompts/deep_tutor.py`

For each hit, edit so the subsection body is described as "a short bold lead sentence + SUBSTANTIVE bold lead-in bullets (one claim per line, ``[N]`` at line end)" instead of "a SUBSTANTIVE paragraph of 3-5 sentences" / "not bullet lists". Preserve the surrounding intent (framing sentence first, graphical hand-off, formulas-have-a-home, depth). Do NOT remove the phrases the other passing contract tests need: `open with one framing sentence`, `one ``### `` subsection per named component`, `graphical hand-off`, `formulas have a home here`, `do not defer the formulas`, `depth over brevity`, `where it fits`, `be extensive`, `minimums, not caps`.

- [ ] **Step 5: Run the full prompt-contract suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_tutor_prompt_contract.py -v`
Expected: PASS — all contract tests green, including the two updated in Task 1. If `test_deep_tutor_instructions_within_token_budget` fails (over budget), tighten the new wording (the rewrite should be net-neutral or shorter than the removed prose mandate).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/prompts/deep_tutor.py
git commit -m "feat(tutor): C-style subsection bodies — bold-lead-in bullets + in-subsection display math + figure-in-Example"
```

---

## Task 3: Apply the C rules to the L3b deepagents synthesis skill

**Files:**
- Modify: `src/services/chat/agents/ow_skills/synthesis/SKILL.md`
- Modify: `src/services/chat/tests/test_ow_harness.py`

- [ ] **Step 1: Write the failing SKILL.md contract test**

Add to `src/services/chat/tests/test_ow_harness.py`:

```python
def test_synthesis_skill_requires_c_style_body():
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "agents" / "ow_skills" / "synthesis" / "SKILL.md"
    md = p.read_text(encoding="utf-8").lower()
    assert "bold lead-in bullets" in md
    assert "$$" in md          # display math allowed, not just inline
    assert "[fn]" in md or "figure marker" in md
```

- [ ] **Step 2: Run it, verify FAIL**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py::test_synthesis_skill_requires_c_style_body -v`
Expected: FAIL — phrases absent from current SKILL.md.

- [ ] **Step 3: Update SKILL.md instructions**

Replace the `## Instructions` list (lines 11-18) of `src/services/chat/agents/ow_skills/synthesis/SKILL.md` with:

```markdown
## Instructions
1. List `/briefs/` and READ every `/briefs/*.md` file in full before writing.
2. Write ONE coherent answer with a single throughline — not a per-author concatenation.
3. COMPARE the authors explicitly: where they agree, where they differ, and why.
4. Retain every content-bearing key point from the briefs; do not drop facts to be brief.
5. Ground every claim in the briefs. Never invent sources, formulas, or names.
6. Skip "no-info" briefs (a brief stating the source does not discuss the topic).
7. STRUCTURE each subtopic for scanning: open with a short **bold lead sentence**,
   then **bold lead-in bullets** — `- **<claim>** — <explanation>` — one claim per
   line. Use prose only for connective tissue between bullets. Never a wall of text.
8. Math: `$...$` for inline, `$$...$$` for display. Place each `$$display$$` formula
   inside the subtopic it supports — for a worked example, state the model/DGP formula
   in that example's subtopic, not at the end.
9. Figures: keep any `[Fn]` figure marker from the briefs in the subtopic it belongs to.
```

- [ ] **Step 4: Run the test, verify PASS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_harness.py::test_synthesis_skill_requires_c_style_body -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/agents/ow_skills/synthesis/SKILL.md src/services/chat/tests/test_ow_harness.py
git commit -m "feat(ow): L3b synthesis skill emits C-style bodies + in-subtopic math/figures"
```

---

## Task 4: Verify schema-fill preserves structure and figure-attach fires on the OW-deep path

**Files:**
- Read: `src/services/chat/agents/ow_deepagents.py` (`_schema_fill`, `_stream_structured`)
- Read: `src/services/chat/agents/orchestrator_workers.py:242` (`_format_figure_bundle`), `deep_tutor.py` figure-attach
- Modify (test only): `src/services/chat/tests/test_ow_deepagents_compare.py`

- [ ] **Step 1: Confirm `_schema_fill` re-express uses the draft system prompt**

Run: `.venv/bin/grep -n "_schema_fill\|_stream_structured\|DEEP_TUTOR_INSTRUCTIONS\|system" src/services/chat/agents/ow_deepagents.py`
Confirm the schema-fill call passes `DEEP_TUTOR_INSTRUCTIONS` (the Task 2 prompt) as the system message, so the C structure, `$$`, and `[Fn]` markers in the free-text synthesis survive the re-express. If it does NOT pass that system prompt, note it as a wiring gap and add a step here to pass it.

- [ ] **Step 2: Confirm figures flow into the OW-deep synth prompt**

Run: `.venv/bin/grep -n "_format_figure_bundle\|figures" src/services/chat/agents/orchestrator_workers.py`
Confirm `run_orchestrator_workers` injects `_format_figure_bundle(figures)` into the synth user message (line ~242) and that the deep-synth branch passes `figures` through. Record the finding (it already does at 242; verify the `deep_synth=True` branch is on the same prompt path).

- [ ] **Step 3: Write a structure-survival test**

Add to `src/services/chat/tests/test_ow_deepagents_compare.py`:

```python
def test_schema_fill_uses_draft_system_prompt(monkeypatch):
    """The L3b schema-fill must re-express via the draft system prompt so the
    C-style bullets, $$display$$ math, and [Fn] markers survive into the schema."""
    import src.services.chat.agents.ow_deepagents as owd
    from src.services.chat.prompts.deep_tutor import DEEP_TUTOR_INSTRUCTIONS

    captured = {}

    async def fake_stream(messages, model, on_aspect_delta):
        captured["messages"] = messages
        from src.services.chat.schemas.output import DeepTutorAnswer
        return DeepTutorAnswer.model_construct()

    monkeypatch.setattr(owd, "_stream_structured", fake_stream)
    import asyncio
    asyncio.run(owd._schema_fill("q", "- **claim** — body\n\n$$y=x$$\n\n[F1]", "gpt-5.4-nano", lambda *_: None))
    sys_msgs = [m for m in captured["messages"] if m.get("role") == "system"]
    assert any(DEEP_TUTOR_INSTRUCTIONS[:40] in m["content"] for m in sys_msgs)
```

(If Step 1 shows `_schema_fill` builds messages differently, adapt the assertion to the actual system-message source — the point is: the draft contract governs the fill.)

- [ ] **Step 4: Run it**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_ow_deepagents_compare.py::test_schema_fill_uses_draft_system_prompt -v`
Expected: PASS. If FAIL because the system prompt is not wired in, fix `_schema_fill` to pass `DEEP_TUTOR_INSTRUCTIONS`, then re-run to PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/chat/tests/test_ow_deepagents_compare.py src/services/chat/agents/ow_deepagents.py
git commit -m "test(ow): schema-fill re-expresses via draft contract; verify figure bundle on deep path"
```

---

## Task 5: Docs lockstep

**Files:**
- Modify: `docs/system/invariants.md:33` (invariant 24)
- Modify: `docs/system/changelog.md`
- Modify: `docs/services/chat-features/56-deep-synthesis-l3b.md`
- Modify: `docs/services/chat-features/36-deep-tutor.md`

- [ ] **Step 1: Update invariant 24 body-format clause**

In `docs/system/invariants.md` invariant 24, change the clause "Aspect bodies are structured with left-aligned `### ` (H3) SUBSECTION headers, not bullet lists" to:

```
Aspect bodies keep left-aligned `### ` (H3) SUBSECTION headers as the backbone; INSIDE each subsection the body is C-style — a short **bold** lead sentence + bold lead-in bullets (one claim per line, `[N]` at line end), display math `$$…$$` and any `[Fn]` figure marker placed in the subsection they belong to (each Example `### Case` carries its own formula + figure).
```

Update the test pointer in the same row from `test_structure_requires_subsection_headers` to also list `test_math_and_figures_placed_in_subsection`.

- [ ] **Step 2: Add a changelog entry**

Prepend under the latest dated heading in `docs/system/changelog.md`:

```markdown
### 2026-06-04 — Tutor C-style subsection bodies
- Draft/synth prompt (`prompts/deep_tutor.py`) and L3b synthesis SKILL now emit
  scannable bodies: bold lead sentence + bold lead-in bullets per `### ` subsection
  (was a dense 3-5 sentence paragraph). Display math and `[Fn]` figure markers are
  placed inside the pertinent subsection; each Example `### Case` carries its own
  `$$formula$$` + figure. No `##`/`###` layout, schema, or frontend change.
- Contract: `test_structure_requires_subsection_headers` (rewritten),
  `test_math_and_figures_placed_in_subsection`, `test_synthesis_skill_requires_c_style_body`.
```

- [ ] **Step 3: Update feature docs**

In `docs/services/chat-features/56-deep-synthesis-l3b.md` and `36-deep-tutor.md`, update any prose describing the answer body format (paragraph-based) to the C-style description above. Do not touch the mermaid pipeline graphs (no stage change).

- [ ] **Step 4: Commit**

```bash
git add docs/system/invariants.md docs/system/changelog.md docs/services/chat-features/56-deep-synthesis-l3b.md docs/services/chat-features/36-deep-tutor.md
git commit -m "docs(tutor): C-style body format — invariant 24, changelog, feature docs"
```

---

## Task 6: Full suite + manual browser verification

**Files:** none (verification)

- [ ] **Step 1: Run the chat test suite**

Run: `.venv/bin/python -m pytest src/services/chat/tests/ -q`
Expected: all green (no regressions).

- [ ] **Step 2: Manual verify on :5175**

With `./scripts/dev.sh` running, ask the DGP question (or any concept) in tutor mode with `tutorWorkflow="orchestrator-deep"`. Confirm: each `###` subsection renders as bold lead + bullets; an Example case shows its `$$formula$$` and (when a figure matches) a figure card; sections/subsections layout unchanged. Note the result in the PR/commit message.

- [ ] **Step 3: (No commit — verification only.)**

---

## Self-Review

- **Spec coverage:** Change 1 (prompt) → Task 2; Change 2 (SKILL.md) → Task 3; Change 3 (schema-fill verify) → Task 4; Change 4 (figure attach verify) → Task 4 Steps 2; model unchanged → noted; docs lockstep → Task 5; manual verify → Task 6. All spec sections covered.
- **Placeholders:** none — every prompt/test edit shows exact text; the one investigate step (Task 4) has a concrete grep + a fix-if-gap branch with the exact remedy.
- **Type/name consistency:** contract phrases used in Task 1 tests (`bold lead-in bullets`, `one claim per line`, `inside the … subsection it belongs to`, `each example`, `in that same subsection`) all appear verbatim in the Task 2 prompt text. `_schema_fill`/`_stream_structured`/`DEEP_TUTOR_INSTRUCTIONS` names match the source.
