# Resume digest → Facilitate document style + per-section math — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render `resume` mode as a flowing document like `facilitate` (no outer card, no per-section boxes) and render each section's formulas inside that section instead of in a trailing pile.

**Architecture:** Add a per-block `math_blocks` field threaded from the existing `map_sections` math output. The frontend renders each section's math via the existing `<MathBlock>` and drops the card-level math pile. CSS reuses facilitate's box-stripping rules for resume, keeping the amber "Resume" eyebrow as the only identity marker. No pipeline/prompt/diagram changes.

**Tech Stack:** Python 3.12 + Pydantic v2 + pytest (backend); React + TypeScript + Vitest + KaTeX (frontend).

Design spec: `docs/superpowers/specs/2026-06-03-resume-facilitate-layout-design.md`.

Run backend tests: `.venv/bin/python -m pytest <path> -q`
Run frontend tests: `cd web && npx vitest run <path>`

---

## File Structure

- **Modify** `src/services/chat/schemas/output.py` — add `math_blocks` to `ChapterBlock`.
- **Modify** `src/services/chat/agents/chapter.py` — pass `math_blocks` into the `ChapterBlock(...)` in `map_sections`.
- **Modify** `src/services/chat/tests/test_chapter_agent.py` — assert per-block math.
- **Modify** `web/src/types.ts` — add `math_blocks?` to `ChapterBlock`.
- **Modify** `web/src/components/ChapterDigestCard.tsx` — render per-section math; drop bottom pile.
- **Modify** `web/src/styles/chapter.css` — resume shares facilitate's document chrome.
- **Modify** `web/src/components/ChapterDigestCard.test.tsx` — per-section math + box-less resume assertions.

---

### Task 1: Per-block `math_blocks` on the backend

**Files:**
- Modify: `src/services/chat/schemas/output.py:310-318`
- Modify: `src/services/chat/agents/chapter.py:240-244`
- Test: `src/services/chat/tests/test_chapter_agent.py:179-182`

- [ ] **Step 1: Extend the existing map test to assert per-block math**

In `src/services/chat/tests/test_chapter_agent.py`, find `test_map_sections_preserves_order_and_uses_resume_prompt` (around line 165). It already returns `'{"body":"explained","citations":[],"math_blocks":["x^2"]}'` from `fake_chat`. After the existing line `assert "x^2" in math  # math_blocks are threaded through` (line 182), add:

```python
    assert blocks_fac[0].math_blocks == ["x^2"]  # per-block math, not just aggregate
    assert blocks_fac[1].math_blocks == ["x^2"]
```

- [ ] **Step 2: Run the test, verify it FAILS**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_chapter_agent.py::test_map_sections_preserves_order_and_uses_resume_prompt -q`
Expected: FAIL — `AttributeError: 'ChapterBlock' object has no attribute 'math_blocks'`.

- [ ] **Step 3: Add the schema field**

In `src/services/chat/schemas/output.py`, the `ChapterBlock` model (lines 310-318) ends with `page_to: int = -1`. Add one line after it:

```python
    math_blocks: list[str] = Field(default_factory=list)
```

(The file already imports `Field` — it is used throughout this module.)

- [ ] **Step 4: Populate the field in `map_sections`**

In `src/services/chat/agents/chapter.py`, the `map_sections` loop builds the block at lines 240-244:

```python
        blocks.append(ChapterBlock(
            h2_path=s.title, section_id=s.chunkId, body=body,
            page_from=s.page_from if s.page_from is not None else -1,
            page_to=s.page_to if s.page_to is not None else -1,
        ))
```

Add `math_blocks=math` to the constructor (the local `math` is already computed at line 235):

```python
        blocks.append(ChapterBlock(
            h2_path=s.title, section_id=s.chunkId, body=body,
            page_from=s.page_from if s.page_from is not None else -1,
            page_to=s.page_to if s.page_to is not None else -1,
            math_blocks=math,
        ))
```

Leave `all_math.extend(math)` and the returned aggregate `math` untouched (back-compat: `digest.math_blocks` stays populated).

- [ ] **Step 5: Run the test, verify it PASSES**

Run: `.venv/bin/python -m pytest src/services/chat/tests/test_chapter_agent.py -q`
Expected: PASS (the extended test + all existing chapter-agent tests, including `test_map_sections_fail_open_uses_excerpt` which builds a block with no math → defaults to `[]`).

- [ ] **Step 6: Commit**

```bash
git add src/services/chat/schemas/output.py src/services/chat/agents/chapter.py src/services/chat/tests/test_chapter_agent.py
git commit -m "feat(chapter): per-block math_blocks on ChapterBlock

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Frontend type + render math per section

**Files:**
- Modify: `web/src/types.ts:177-183`
- Modify: `web/src/components/ChapterDigestCard.tsx:51-76`
- Test: `web/src/components/ChapterDigestCard.test.tsx`

- [ ] **Step 1: Write a failing test — math renders inside its section, no bottom pile**

In `web/src/components/ChapterDigestCard.test.tsx`, add a new test inside the `describe("ChapterDigestCard", ...)` block. It builds a resume digest where block 0 carries `math_blocks` and the card-level `math_blocks` is empty, and asserts the formula renders. KaTeX renders the TeX source into a `<annotation encoding="application/x-tex">` node, so we assert on that.

```typescript
  it("renders a block's math inside its section (not in a trailing pile)", () => {
    const d: ChapterDigest = {
      mode: "resume",
      scope: {
        book_slug: "hansen",
        chapter_id: "ch07",
        requested_subtopics: [],
        resolution: [],
      },
      intro: "Recap.",
      blocks: [
        {
          h2_path: "7.1 | A",
          section_id: "7.1",
          body: "alpha body",
          page_from: 1,
          page_to: 2,
          math_blocks: ["a^2 + b^2"],
        },
        {
          h2_path: "7.2 | B",
          section_id: "7.2",
          body: "beta body",
          page_from: 3,
          page_to: 4,
          math_blocks: [],
        },
      ],
      outro: "Done.",
      citations: [],
      math_blocks: [],
      grounding: { ok: true, unsupported: [], confidence: 0.9 },
    };
    const html = renderToStaticMarkup(<ChapterDigestCard digest={d} />);
    // KaTeX emits the TeX source in an annotation node.
    expect(html).toContain("a^2 + b^2");
    // Math sits before the second block's body → inside section 7.1, not at the end.
    expect(html.indexOf("a^2 + b^2")).toBeLessThan(html.indexOf("beta body"));
  });
```

- [ ] **Step 2: Run the test, verify it FAILS**

Run: `cd web && npx vitest run src/components/ChapterDigestCard.test.tsx`
Expected: FAIL — the TeX source `a^2 + b^2` is not in the output (card-level `math_blocks` is empty and per-block math is not yet rendered). A TypeScript error on the `math_blocks` block property is also acceptable as a failure signal.

- [ ] **Step 3: Add `math_blocks` to the frontend `ChapterBlock` type**

In `web/src/types.ts`, the `ChapterBlock` interface (lines 177-183) is:

```typescript
export interface ChapterBlock {
  h2_path: string;
  section_id: string;
  body: string;
  page_from: number;
  page_to: number;
}
```

Add the optional field before the closing brace:

```typescript
export interface ChapterBlock {
  h2_path: string;
  section_id: string;
  body: string;
  page_from: number;
  page_to: number;
  math_blocks?: string[];
}
```

- [ ] **Step 4: Render per-section math; remove the bottom pile**

In `web/src/components/ChapterDigestCard.tsx`, the section render (lines 51-66) currently is:

```tsx
        {digest.blocks.map((b, i) => (
          <section key={`${b.section_id}-${i}`} className="chapter-block">
            <h3 className="chapter-block__h">{b.h2_path}</h3>
            {b.page_from > 0 && (
              <span className="chapter-block__pages">
                pp. {b.page_from}
                {b.page_to > b.page_from ? `–${b.page_to}` : ""}
              </span>
            )}
            <div className="chapter-block__body">
              {renderInlineWithCites(b.body, citationsByIndex, hoveredIdx, setHoveredIdx)}
            </div>
          </section>
        ))}
```

Add a per-section math render after `chapter-block__body`:

```tsx
        {digest.blocks.map((b, i) => (
          <section key={`${b.section_id}-${i}`} className="chapter-block">
            <h3 className="chapter-block__h">{b.h2_path}</h3>
            {b.page_from > 0 && (
              <span className="chapter-block__pages">
                pp. {b.page_from}
                {b.page_to > b.page_from ? `–${b.page_to}` : ""}
              </span>
            )}
            <div className="chapter-block__body">
              {renderInlineWithCites(b.body, citationsByIndex, hoveredIdx, setHoveredIdx)}
            </div>
            {(b.math_blocks?.length ?? 0) > 0 && (
              <div className="chapter-block__math">
                {b.math_blocks!.map((tex, mi) => (
                  <div key={mi} className="chapter-card__math-block">
                    <MathBlock tex={tex} />
                  </div>
                ))}
              </div>
            )}
          </section>
        ))}
```

Then DELETE the trailing card-level math pile (lines 68-76):

```tsx
      {digest.math_blocks.length > 0 && (
        <div className="chapter-card__math-blocks">
          {digest.math_blocks.map((tex, i) => (
            <div key={i} className="chapter-card__math-block">
              <MathBlock tex={tex} />
            </div>
          ))}
        </div>
      )}
```

`MathBlock` is already imported at the top of the file; leave the import.

- [ ] **Step 5: Run the test, verify it PASSES**

Run: `cd web && npx vitest run src/components/ChapterDigestCard.test.tsx`
Expected: PASS (new test + existing "renders blocks in order" etc.).

- [ ] **Step 6: Commit**

```bash
git add web/src/types.ts web/src/components/ChapterDigestCard.tsx web/src/components/ChapterDigestCard.test.tsx
git commit -m "feat(web): render resume math per section, drop card-level math pile

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Resume shares facilitate's document chrome (CSS)

**Files:**
- Modify: `web/src/styles/chapter.css:19-61,114-117,218-224,257`
- Test: `web/src/components/ChapterDigestCard.test.tsx`

- [ ] **Step 1: Write a failing test — resume header has no card chrome / box markers**

CSS isn't exercised by jsdom computed styles, so assert on the structural class wiring the CSS keys off. The resume card root has `chapter-card--resume`; after the change there must be no resume-only `border-left` stripe class hook left in the markup beyond the shared variant, and the section still uses `chapter-block`. We assert the resume variant class is applied (the CSS selector target) and the facilitate-style is shared. Add:

```typescript
  it("applies the resume variant class so it shares facilitate document chrome", () => {
    const d: ChapterDigest = {
      mode: "resume",
      scope: { book_slug: "hansen", chapter_id: "ch07", requested_subtopics: [], resolution: [] },
      intro: "i",
      blocks: [{ h2_path: "7.1 | A", section_id: "7.1", body: "x", page_from: 1, page_to: 2, math_blocks: [] }],
      outro: "o",
      citations: [],
      math_blocks: [],
      grounding: { ok: true, unsupported: [], confidence: 0.9 },
    };
    const html = renderToStaticMarkup(<ChapterDigestCard digest={d} />);
    expect(html).toContain("chapter-card--resume");
    expect(html).toContain("chapter-block");
  });
```

- [ ] **Step 2: Run the test, verify it PASSES already (guard test) then proceed to CSS**

Run: `cd web && npx vitest run src/components/ChapterDigestCard.test.tsx`
Expected: PASS — this test guards the class hooks the CSS depends on; it must stay green through the CSS edit. (The visual change itself is verified in the browser at Step 6.)

- [ ] **Step 3: Make facilitate's chrome-strip rules also target resume**

In `web/src/styles/chapter.css`, add `.chapter-card--resume` to each facilitate strip selector. Apply these exact edits:

Lines 19-25 (root chrome strip) — change the selector to cover both:

```css
/* Facilitate + Resume variant: headered document — strip the card chrome */
.chapter-card--facilitate,
.chapter-card--resume {
  border: none;
  background: none;
  box-shadow: none;
  padding: 0;
}
```

Lines 28-32 (header separator):

```css
.chapter-card--facilitate .chapter-card__hd,
.chapter-card--resume .chapter-card__hd {
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 14px;
  padding-bottom: 8px;
}
```

Lines 35-40 (intro lead):

```css
.chapter-card--facilitate .chapter-card__intro,
.chapter-card--resume .chapter-card__intro {
  margin: 4px 0 18px;
  font-style: italic;
  line-height: 1.6;
  color: var(--text-secondary);
}
```

Lines 43-50 (box-less section):

```css
.chapter-card--facilitate .chapter-block,
.chapter-card--resume .chapter-block {
  padding: 0;
  background: none;
  border: none;
  border-left: none;
  border-radius: 0;
  margin: 0 0 22px;
}
```

Lines 53-61 (flowing accent heading):

```css
.chapter-card--facilitate .chapter-block__h,
.chapter-card--resume .chapter-block__h {
  font-size: var(--text-base);
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0.01em;
  color: var(--accent-primary);
  margin-top: 24px;
  margin-bottom: 2px;
}
```

Lines 64-66 (pages caption spacing):

```css
.chapter-card--facilitate .chapter-block__pages,
.chapter-card--resume .chapter-block__pages {
  margin-bottom: 10px;
}
```

- [ ] **Step 4: Remove the resume-only left stripe and justified body**

In `web/src/styles/chapter.css`, lines 114-117 are the resume left-stripe:

```css
/* Resume variant: secondary accent stripe */
.chapter-card--resume {
  border-left: 3px solid var(--accent-secondary);
}
```

Delete this rule (the `--resume` chrome is now the shared box-less treatment; the amber eyebrow at lines 146-150 stays as the identity marker).

Then the body justify at lines 257 (`text-align: justify; hyphens: auto;` inside `.chapter-block__body`) must not apply to resume. Add an override after the `.chapter-block__body` rule block (after line 258):

```css
/* Resume/facilitate document body reads left-aligned like prose */
.chapter-card--facilitate .chapter-block__body,
.chapter-card--resume .chapter-block__body {
  text-align: left;
  line-height: 1.6;
}
```

- [ ] **Step 5: Run tests + typecheck, verify green**

Run: `cd web && npx vitest run src/components/ChapterDigestCard.test.tsx && npx tsc --noEmit`
Expected: PASS + no type errors.

- [ ] **Step 6: Browser-verify on :5175**

With `./scripts/dev.sh` running, open `http://localhost:5175`. Run a Resume turn (e.g. select Resume mode, ask "resume hansen ch7"). Confirm:
- document layout — no outer card border, no per-section boxes;
- each formula renders inside its section (not piled at the end);
- amber "Resume" eyebrow present; grounding badge + resolution note intact;
- compare against a Facilitate turn — chrome should match.

Then commit:

```bash
git add web/src/styles/chapter.css web/src/components/ChapterDigestCard.test.tsx
git commit -m "style(web): resume digest shares facilitate document chrome (no card/boxes)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Docs — note the layout change

**Files:**
- Modify: `docs/system/changelog.md`
- Modify: the resume/chapter per-feature doc under `docs/services/chat-features/` (the chapter-modes / resume doc)

- [ ] **Step 1: Find the right per-feature doc**

Run: `grep -rln "resume" docs/services/chat-features/ | head`
Pick the chapter/resume feature doc (e.g. the chapter-modes one). Open it.

- [ ] **Step 2: Add a short note**

In that per-feature doc, add a line under the resume rendering description:

```markdown
- **Layout:** Resume renders as a flowing document (shares `.chapter-card--facilitate` chrome — no outer card, no per-section boxes). Formulas render **inside their section** via per-block `ChapterBlock.math_blocks`, not in a trailing pile. The amber "Resume" eyebrow is the only chrome difference from Facilitate.
```

- [ ] **Step 3: Add a changelog entry**

In `docs/system/changelog.md`, add a dated entry at the top of the most recent section:

```markdown
- 2026-06-03: Resume digest adopts Facilitate's document layout (no card/boxes); per-section math via `ChapterBlock.math_blocks` (renders inside each section, not a trailing pile). Frontend-only render + CSS + one schema field; no pipeline/prompt/diagram change.
```

- [ ] **Step 4: Commit**

```bash
git add docs/system/changelog.md docs/services/chat-features/
git commit -m "docs(resume): note facilitate-style layout + per-section math

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Layout/CSS — resume shares facilitate strip rules, amber eyebrow kept, justify dropped → Task 3. ✔
- Per-section math data model (schema + chapter.py + frontend type + render, drop pile) → Tasks 1, 2. ✔
- Per-element parity (citations, inline math) needs no change — `renderInlineWithCites` unchanged → covered by leaving it. ✔
- Export excluded (raw JSON dump, YAGNI) → not a task, matches corrected spec. ✔
- Tests: backend per-block math, frontend per-section math + box-less guards → Tasks 1, 2, 3. ✔
- Docs/changelog → Task 4. ✔

**Placeholder scan:** none. Task 4 Step 1 asks the implementer to `grep` for the exact per-feature doc rather than guessing a filename — a deliberate locate step (the chat-features docs are numbered and the resume one must be confirmed), not a placeholder.

**Type consistency:** `math_blocks: list[str]` (backend `ChapterBlock`) ↔ `math_blocks?: string[]` (frontend `ChapterBlock`) ↔ `b.math_blocks` render. `<MathBlock tex={...}>` and class `chapter-card__math-block` reused from the deleted pile. `.chapter-card--resume` / `.chapter-block` class hooks consistent across Tasks 2–3 and tests. Backend `map_sections` local `math` (line 235) feeds `math_blocks=math` (Task 1 Step 4).

**Not touched (asserted):** prompts, `tutorPipeline.ts`, `PipelineDiagram.tsx`, pipeline graph docs — no stage change.
