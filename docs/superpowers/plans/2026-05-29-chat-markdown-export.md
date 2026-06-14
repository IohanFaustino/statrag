# Chat Markdown Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user export chat content to `.md` — full active conversation (Topbar button) or a single answer (per-message icon).

**Architecture:** Frontend-only. One new pure module `web/src/lib/exportMarkdown.ts` serializes `Message[]` → markdown (handling block prose, math, figures, sources, and all 7 structured-output schemas faithfully) and triggers a Blob download. Topbar + MessageThread get thin UI hooks; `App.tsx` wires them to the active conversation slice. No backend, no SSE, no schema change — Chinese wall untouched.

**Tech Stack:** TypeScript, React 18, Vite, vitest. Types from `web/src/types.ts`.

---

## File Structure

- **Create** `web/src/lib/exportMarkdown.ts` — pure serializer + `downloadMarkdown` helper. Single responsibility: turn chat data into a markdown string and save it.
- **Create** `web/src/lib/exportMarkdown.test.ts` — vitest unit tests for the pure functions.
- **Modify** `web/src/components/Icons.tsx` — add `IconDownload`.
- **Modify** `web/src/components/Topbar.tsx` — add `onExportConversation` prop + button.
- **Modify** `web/src/components/MessageThread.tsx` — add `onExportMessage` prop + per-answer icon.
- **Modify** `web/src/App.tsx` — wire both handlers to the active slice `messages` + `activeConvTitle`.

Test commands (run from repo root unless noted):
- Frontend tests: `cd web && npx vitest run src/lib/exportMarkdown.test.ts`
- Typecheck: `cd web && npx tsc --noEmit`
- Dev stack (already running on :5175): `./scripts/dev.sh`

---

## Task 1: Pure serializer module (core blocks + helpers)

**Files:**
- Create: `web/src/lib/exportMarkdown.ts`
- Test: `web/src/lib/exportMarkdown.test.ts`

- [ ] **Step 1: Write the failing tests for helpers + block serialization**

Create `web/src/lib/exportMarkdown.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  slugify,
  assistantMessageToMarkdown,
  userMessageToMarkdown,
  conversationToMarkdown,
} from "./exportMarkdown";
import type { AssistantMessage, UserMessage } from "../types";

function baseAssistant(partial: Partial<AssistantMessage>): AssistantMessage {
  return {
    role: "assistant",
    id: "a1",
    time: "10:00",
    timestamp: "2026-05-29T10:00:00Z",
    mode: "tutor",
    model: "gpt-5.4-nano",
    books: ["HANSEN"],
    sourceCount: 2,
    latencyMs: 1234,
    blocks: [],
    status: "complete",
    ...partial,
  };
}

describe("slugify", () => {
  it("lowercases, replaces non-alnum with hyphen, collapses repeats", () => {
    expect(slugify("Hello, World!  Foo")).toBe("hello-world-foo");
  });
  it("caps length around 40 chars and trims trailing hyphen", () => {
    const out = slugify("a".repeat(60));
    expect(out.length).toBeLessThanOrEqual(40);
    expect(out.endsWith("-")).toBe(false);
  });
  it("falls back to 'conversation' on empty", () => {
    expect(slugify("!!!")).toBe("conversation");
  });
});

describe("userMessageToMarkdown", () => {
  it("renders a You heading and the text", () => {
    const u: UserMessage = {
      role: "user", id: "u1", time: "10:00",
      timestamp: "2026-05-29T10:00:00Z", text: "What is variance?",
    };
    const md = userMessageToMarkdown(u);
    expect(md).toContain("## You · 10:00");
    expect(md).toContain("What is variance?");
  });
});

describe("assistantMessageToMarkdown — blocks", () => {
  it("renders paragraphs and preserves bold", () => {
    const msg = baseAssistant({
      blocks: [{ type: "p", text: "Variance is **spread**." }],
    });
    const md = assistantMessageToMarkdown(msg);
    expect(md).toContain("Variance is **spread**.");
  });

  it("renders a math block as $$tex$$", () => {
    const msg = baseAssistant({
      blocks: [{ type: "math", tex: "\\sigma^2 = E[(X-\\mu)^2]" }],
    });
    const md = assistantMessageToMarkdown(msg);
    expect(md).toContain("$$");
    expect(md).toContain("\\sigma^2 = E[(X-\\mu)^2]");
  });

  it("renders a figure block as a caption line", () => {
    const msg = baseAssistant({
      blocks: [{
        type: "figure", ref: "Fig 2.1", book: "HANSEN",
        chapter: "Ch2", caption: "A scatter plot", chart: "/img/fig.png",
      }],
    });
    const md = assistantMessageToMarkdown(msg);
    expect(md).toContain("Fig 2.1");
    expect(md).toContain("A scatter plot");
    expect(md).toContain("/img/fig.png");
  });

  it("renders a sources block as a chip list", () => {
    const msg = baseAssistant({
      blocks: [{ type: "sources", chips: [
        { book: "HANSEN", section: "§2.1" },
        { book: "WOOLDRIDGE", section: "§3.4" },
      ] }],
    });
    const md = assistantMessageToMarkdown(msg);
    expect(md).toContain("HANSEN");
    expect(md).toContain("§2.1");
    expect(md).toContain("§3.4");
  });

  it("drops empty paragraphs", () => {
    const msg = baseAssistant({
      blocks: [{ type: "p", text: "" }, { type: "p", text: "Real." }],
    });
    const md = assistantMessageToMarkdown(msg);
    expect(md).not.toMatch(/\n\n\n\n/);
    expect(md).toContain("Real.");
  });

  it("emits an incomplete note for a non-complete message", () => {
    const msg = baseAssistant({ status: "streaming", blocks: [] });
    const md = assistantMessageToMarkdown(msg);
    expect(md.toLowerCase()).toContain("incomplete");
  });
});

describe("conversationToMarkdown", () => {
  it("emits a header then user + assistant turns in order", () => {
    const u: UserMessage = {
      role: "user", id: "u1", time: "10:00",
      timestamp: "2026-05-29T10:00:00Z", text: "Define mean.",
    };
    const a = baseAssistant({ blocks: [{ type: "p", text: "The mean is the average." }] });
    const md = conversationToMarkdown([u, a], { title: "Stats Q&A", date: "2026-05-29" });
    expect(md.startsWith("# Stats Q&A")).toBe(true);
    expect(md).toContain("Exported from statrag");
    const youIdx = md.indexOf("## You");
    const tutorIdx = md.indexOf("## TUTOR");
    expect(youIdx).toBeGreaterThan(-1);
    expect(tutorIdx).toBeGreaterThan(youIdx);
  });

  it("skips pending/streaming assistant turns", () => {
    const a = baseAssistant({ status: "pending", blocks: [] });
    const md = conversationToMarkdown([a], { title: "x" });
    expect(md.toLowerCase()).not.toContain("incomplete");
    expect(md).not.toContain("## TUTOR");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/lib/exportMarkdown.test.ts`
Expected: FAIL — `Failed to resolve import "./exportMarkdown"`.

- [ ] **Step 3: Implement the module (helpers + blocks + conversation; structured stub)**

Create `web/src/lib/exportMarkdown.ts`:

```ts
// Pure markdown serializer for chat export. No React. The only DOM-touching
// function is downloadMarkdown (covered by browser-verify, not unit tests).
import type {
  Message, UserMessage, AssistantMessage, AssistantBlock,
} from "../types";
import { structuredToMarkdown } from "./exportStructured";

const MODE_LABEL: Record<string, string> = {
  tutor: "TUTOR", compare: "COMPARE", figures: "FIGURES", quiz: "QUIZ",
  navigate: "NAVIGATE", prereqs: "PREREQS", annotate: "ANNOTATE",
  research: "RESEARCH", math: "MATH", path: "PATH", roadmap: "ROADMAP",
};

export function slugify(s: string): string {
  const cleaned = s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/g, "");
  return cleaned || "conversation";
}

function blockToMarkdown(block: AssistantBlock): string {
  switch (block.type) {
    case "p":
      return block.text.trim() ? block.text.trim() : "";
    case "math":
      return "$$\n" + block.tex.trim() + "\n$$";
    case "figure": {
      const tag = `**${block.ref}** — ${block.caption} (${block.book} · ${block.chapter})`;
      const isUrl = block.chart && (block.chart.startsWith("/") || block.chart.startsWith("http"));
      const img = isUrl ? `\n\n![${block.caption}](${block.chart})` : "";
      return `> ${tag}${img}`;
    }
    case "sources": {
      const chips = block.chips.map((c) => `\`${c.book} · ${c.section}\``).join(" ");
      return `**Sources:** ${chips}`;
    }
    default:
      return "";
  }
}

export function assistantMessageToMarkdown(msg: AssistantMessage): string {
  if (msg.status !== "complete") {
    return "> _(answer incomplete — not exported)_";
  }
  if (msg.structuredOutput) {
    const structured = structuredToMarkdown(msg.structuredOutput);
    if (structured) return structured;
  }
  const parts = msg.blocks.map(blockToMarkdown).filter((s) => s.length > 0);
  return parts.join("\n\n");
}

export function userMessageToMarkdown(msg: UserMessage): string {
  return `## You · ${msg.time}\n\n${msg.text.trim()}`;
}

export function conversationToMarkdown(
  messages: Message[],
  meta: { title: string; date?: string },
): string {
  const date = meta.date ?? new Date().toISOString().slice(0, 10);
  const head = `# ${meta.title}\n\n> Exported from statrag · ${date}`;
  const turns: string[] = [];
  for (const m of messages) {
    if (m.role === "user") {
      turns.push(userMessageToMarkdown(m));
    } else {
      if (m.status !== "complete") continue; // skip in-flight/errored turns
      const label = MODE_LABEL[m.mode] ?? m.mode.toUpperCase();
      const heading = `## ${label} · ${m.model || "?"} · ${m.time}`;
      turns.push(`${heading}\n\n${assistantMessageToMarkdown(m)}`);
    }
  }
  return [head, ...turns].join("\n\n---\n\n") + "\n";
}

export function downloadMarkdown(filename: string, content: string): void {
  try {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    // Best-effort, mirrors persist.ts: never throw from a UI handler.
    // eslint-disable-next-line no-console
    console.warn("[exportMarkdown] download failed", err);
  }
}
```

> Note: this imports `./exportStructured` which is created in Task 2. To keep Task 1 self-contained and green, create a minimal stub now (it is fully implemented in Task 2):
>
> Create `web/src/lib/exportStructured.ts`:
> ```ts
> import type { AssistantMessage } from "../types";
> // Implemented in Task 2. Returns "" when no faithful renderer applies.
> export function structuredToMarkdown(
>   _structured: NonNullable<AssistantMessage["structuredOutput"]>,
> ): string {
>   return "";
> }
> ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/lib/exportMarkdown.test.ts`
Expected: PASS (all describe blocks green).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/exportMarkdown.ts web/src/lib/exportStructured.ts web/src/lib/exportMarkdown.test.ts
git commit -m "feat(web): markdown serializer core for chat export

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Faithful structured-output serializers

**Files:**
- Modify: `web/src/lib/exportStructured.ts` (replace the stub)
- Test: `web/src/lib/exportStructured.test.ts` (create)

- [ ] **Step 1: Write the failing tests**

Create `web/src/lib/exportStructured.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { structuredToMarkdown } from "./exportStructured";
import type { Quiz, StudyPlan, DAG, TutorAnswer } from "../types";

describe("structuredToMarkdown — TutorAnswer", () => {
  it("renders prose then a numbered citations section", () => {
    const data: TutorAnswer = {
      text: "Variance measures spread.",
      citations: [
        { index: 1, book_name: "Econometrics", chapter: "Ch2", section: "§2.1", authors_short: "Hansen", year: 2022, quote: "var def" },
      ],
    };
    const md = structuredToMarkdown({ schema: "TutorAnswer", data });
    expect(md).toContain("Variance measures spread.");
    expect(md).toContain("Citations");
    expect(md).toContain("Hansen");
    expect(md).toContain("§2.1");
  });
});

describe("structuredToMarkdown — Quiz", () => {
  it("renders numbered questions with lettered options and answer", () => {
    const data: Quiz = {
      questions: [{
        stem: "What is the mean?",
        options: ["Sum", "Average", "Median", "Mode"],
        answer_idx: 1,
        rubric: "Average of values.",
        source: { book: "HANSEN", chapter: "Ch1", section: "§1.2" },
        difficulty: "easy",
      }],
    };
    const md = structuredToMarkdown({ schema: "Quiz", data });
    expect(md).toContain("1. What is the mean?");
    expect(md).toContain("- B. Average");
    expect(md).toContain("**Answer:** B");
    expect(md).toContain("easy");
  });
});

describe("structuredToMarkdown — StudyPlan", () => {
  it("renders a week table", () => {
    const data: StudyPlan = {
      goal: "Master regression",
      weeks: [{ week: 1, sections: [{ book: "HANSEN", chapter: "Ch3", section: "§3.1" }], hours_est: 5 }],
      coverage_gaps: ["nonlinear models"],
      replanned_from_version: 0,
    };
    const md = structuredToMarkdown({ schema: "StudyPlan", data });
    expect(md).toContain("Master regression");
    expect(md).toContain("| Week |");
    expect(md).toContain("HANSEN");
    expect(md).toContain("nonlinear models");
  });
});

describe("structuredToMarkdown — DAG", () => {
  it("renders nodes and edges", () => {
    const data: DAG = {
      nodes: [{ id: "a", label: "Mean", source: null }, { id: "b", label: "Variance", source: null }],
      edges: [{ from_id: "a", to_id: "b", weight: 0.9 }],
      cycles_broken: [],
    };
    const md = structuredToMarkdown({ schema: "DAG", data });
    expect(md).toContain("Mean");
    expect(md).toContain("Variance");
    expect(md).toContain("a → b");
  });
});

describe("structuredToMarkdown — unknown schema", () => {
  it("falls back to a json fence", () => {
    const md = structuredToMarkdown({ schema: "Mystery", data: { x: 1 } });
    expect(md).toContain("```json");
    expect(md).toContain("\"x\": 1");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/lib/exportStructured.test.ts`
Expected: FAIL — assertions fail because the stub returns `""`.

- [ ] **Step 3: Implement the faithful serializers**

Replace the entire contents of `web/src/lib/exportStructured.ts`:

```ts
import type {
  AssistantMessage, Citation, TutorAnswer, Quiz, NavigationList,
  DAG, Report, StudyPlan, Roadmap, AnnotatedReading,
} from "../types";

type Structured = NonNullable<AssistantMessage["structuredOutput"]>;

function citeLine(c: Citation): string {
  const page = c.page != null ? `, p.${c.page}` : "";
  return `${c.book} · ${c.chapter} · ${c.section}${page}`;
}

const LETTERS = "ABCDEFGHIJ";

function tutor(d: TutorAnswer): string {
  const parts: string[] = [d.text.trim()];
  if (d.citations && d.citations.length) {
    const lines = d.citations.map((c) => {
      const who = [c.authors_short, c.year].filter(Boolean).join(" ");
      const loc = [c.book_name, c.chapter, c.section].filter(Boolean).join(" · ");
      const quote = c.quote ? ` — "${c.quote}"` : "";
      return `${c.index}. ${[who, loc].filter(Boolean).join(" — ")}${quote}`;
    });
    parts.push("### Citations\n\n" + lines.join("\n"));
  }
  if (d.figures && d.figures.length) {
    const figs = d.figures.map((f) => `- **${f.ref}** ${f.caption} (${f.book} · ${f.chapter})`);
    parts.push("### Figures\n\n" + figs.join("\n"));
  }
  return parts.join("\n\n");
}

function quiz(d: Quiz): string {
  const blocks = d.questions.map((q, i) => {
    const opts = q.options.map((o, j) => `- ${LETTERS[j]}. ${o}`).join("\n");
    const ans = LETTERS[q.answer_idx] ?? "?";
    return [
      `${i + 1}. ${q.stem}`,
      opts,
      `**Answer:** ${ans}`,
      q.rubric ? `_${q.rubric}_` : "",
      `(${q.difficulty} · ${citeLine(q.source)})`,
    ].filter(Boolean).join("\n\n");
  });
  return blocks.join("\n\n");
}

function navigation(d: NavigationList): string {
  const rows = d.results.map(
    (r) => `| ${r.book} | ${r.chapter} | ${r.section} | ${r.title} | ${r.score.toFixed(2)} |`,
  );
  return [
    "| Book | Chapter | Section | Title | Score |",
    "|---|---|---|---|---|",
    ...rows,
  ].join("\n");
}

function dag(d: DAG): string {
  const nodes = d.nodes.map((n) => `- \`${n.id}\` ${n.label}`).join("\n");
  const edges = d.edges.map((e) => `- ${e.from_id} → ${e.to_id} (${e.weight})`).join("\n");
  const parts = [`### Nodes\n\n${nodes}`, `### Edges\n\n${edges}`];
  if (d.cycles_broken.length) parts.push(`### Cycles broken\n\n${d.cycles_broken.join(", ")}`);
  return parts.join("\n\n");
}

function report(d: Report): string {
  const claims = d.claims.map((c) => {
    const ev = c.evidence.map((e) => `  - ${citeLine(e)}`).join("\n");
    return `- **${c.stance}** (${c.confidence}): ${c.claim}${ev ? "\n" + ev : ""}`;
  });
  const parts = [`### Claims\n\n${claims.join("\n")}`, `### Synthesis\n\n${d.synthesis}`];
  if (d.coverage_gaps.length) parts.push(`### Coverage gaps\n\n${d.coverage_gaps.map((g) => `- ${g}`).join("\n")}`);
  return parts.join("\n\n");
}

function studyPlan(d: StudyPlan): string {
  const rows = d.weeks.map((w) => {
    const secs = w.sections.map(citeLine).join("; ");
    return `| ${w.week} | ${secs} | ${w.hours_est} |`;
  });
  const table = ["| Week | Sections | Hours |", "|---|---|---|", ...rows].join("\n");
  const parts = [`**Goal:** ${d.goal}`, table];
  if (d.coverage_gaps.length) parts.push(`**Coverage gaps:** ${d.coverage_gaps.join(", ")}`);
  return parts.join("\n\n");
}

function roadmap(d: Roadmap): string {
  const scenes = d.scenes.map((s) => {
    return [
      `### Scene ${s.id}: ${s.title}`,
      `- Concept: ${s.concept}`,
      `- Visual: ${s.suggested_visual}`,
      `- Duration: ${s.duration_hint}`,
      s.figure ? `- Figure: ${s.figure}` : "",
      `- Source: ${citeLine(s.source)}`,
    ].filter(Boolean).join("\n");
  });
  return [`**Topic:** ${d.topic} (${d.duration_total_min} min)`, ...scenes].join("\n\n");
}

function annotated(d: AnnotatedReading): string {
  return d.annotations
    .map((a) => `- **${a.term}** — ${a.definition}${a.source ? ` (${citeLine(a.source)})` : ""}`)
    .join("\n");
}

export function structuredToMarkdown(structured: Structured): string {
  const { schema, data } = structured;
  switch (schema) {
    case "TutorAnswer": return tutor(data as TutorAnswer);
    case "Quiz": return quiz(data as Quiz);
    case "NavigationList": return navigation(data as NavigationList);
    case "DAG": return dag(data as DAG);
    case "Report": return report(data as Report);
    case "StudyPlan": return studyPlan(data as StudyPlan);
    case "Roadmap": return roadmap(data as Roadmap);
    case "AnnotatedReading": return annotated(data as AnnotatedReading);
    default:
      return "```json\n" + JSON.stringify(data, null, 2) + "\n```";
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/lib/exportStructured.test.ts src/lib/exportMarkdown.test.ts`
Expected: PASS for both files.

- [ ] **Step 5: Typecheck + commit**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

```bash
git add web/src/lib/exportStructured.ts web/src/lib/exportStructured.test.ts
git commit -m "feat(web): faithful markdown for structured chat outputs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Download icon + Topbar button (full conversation)

**Files:**
- Modify: `web/src/components/Icons.tsx` (add `IconDownload`)
- Modify: `web/src/components/Topbar.tsx`

- [ ] **Step 1: Add the icon**

In `web/src/components/Icons.tsx`, add after `IconBook` (mirrors the `base` pattern):

```tsx
export function IconDownload(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="M8 2.5v8" />
      <path d="M4.5 7 8 10.5 11.5 7" />
      <path d="M3 13h10" />
    </svg>
  );
}
```

- [ ] **Step 2: Add prop + button to Topbar**

In `web/src/components/Topbar.tsx`:

Add to the `TopbarProps` interface (after `onToggleTheme(): void;`):

```tsx
  onExportConversation?(): void;
  exportDisabled?: boolean;
```

Add `IconDownload` to the import from `./Icons`:

```tsx
import { IconMenu, IconLogo, IconSun, IconMoon, IconGear, IconBook, IconDownload } from "./Icons";
```

Destructure the new props in the `Topbar` function signature (after `onToggleTheme,`):

```tsx
  onExportConversation,
  exportDisabled,
```

In the `topbar__right` block, insert the export button **immediately before** the theme toggle `<button>`:

```tsx
        {onExportConversation && (
          <button
            className="icon-btn icon-btn--export"
            onClick={onExportConversation}
            disabled={exportDisabled}
            aria-label="Export conversation as Markdown"
            title="Export conversation (.md)"
            type="button"
          >
            <IconDownload />
          </button>
        )}
```

- [ ] **Step 3: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors (props are optional; App wiring lands in Task 5).

- [ ] **Step 4: Commit**

```bash
git add web/src/components/Icons.tsx web/src/components/Topbar.tsx
git commit -m "feat(web): topbar export-conversation button

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Per-answer export icon (single answer)

**Files:**
- Modify: `web/src/components/MessageThread.tsx`

- [ ] **Step 1: Thread the prop through MessageThread → AssistantMessageView**

In `web/src/components/MessageThread.tsx`:

Add `IconDownload` to the icon import block:

```tsx
import {
  IconBook, IconCompare, IconImage, IconQuiz, IconSearch,
  IconTree, IconPen, IconFlask, IconMath, IconCal, IconFilm, IconDownload,
} from "./Icons";
```

Add to `AssistantMessageViewProps` (after `forkDisabled?: boolean;`):

```tsx
  onExport?: (idx: number) => void;
```

Add `onExport` to the `AssistantMessageView` destructured params (after `forkDisabled,`):

```tsx
  onExport,
```

In `AssistantMessageView`, place the export button **immediately before** the existing `{!forkDisabled && (` fork button block, and gate it on a complete message:

```tsx
      {onExport && msg.status === "complete" && (
        <button
          className="msg__export"
          type="button"
          onClick={() => onExport(idx)}
          title="Export this answer (.md)"
          aria-label="Export this answer as Markdown"
        >
          <IconDownload width={14} height={14} />
        </button>
      )}
```

Add to `MessageThreadProps` (after `forkDisabled?: boolean;`):

```tsx
  onExportMessage?: (idx: number) => void;
```

Destructure it in the `MessageThread` function signature (after `forkDisabled = false,`):

```tsx
  onExportMessage,
```

Pass it to `AssistantMessageView` in the `thread.map` (after `onFork={onFork}`):

```tsx
              onExport={onExportMessage}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/MessageThread.tsx
git commit -m "feat(web): per-answer export icon

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Wire handlers in App.tsx

**Files:**
- Modify: `web/src/App.tsx`

- [ ] **Step 1: Import the serializer**

Near the top imports of `web/src/App.tsx`, add:

```tsx
import { conversationToMarkdown, assistantMessageToMarkdown, slugify, downloadMarkdown } from "./lib/exportMarkdown";
```

- [ ] **Step 2: Add the two handlers**

Add just above the `return (` (after `const activeConvTitle = …` / `const bookSnapshots = …`):

```tsx
  const handleExportConversation = useCallback(() => {
    if (messages.length === 0) return;
    const slug = slugify(activeConvTitle);
    const md = conversationToMarkdown(messages, { title: activeConvTitle });
    downloadMarkdown(`statrag-${slug}.md`, md);
  }, [messages, activeConvTitle]);

  const handleExportMessage = useCallback((idx: number) => {
    const msg = messages[idx];
    if (!msg || msg.role !== "assistant") return;
    const slug = slugify(activeConvTitle);
    // 1-based ordinal of this answer among assistant messages.
    let n = 0;
    for (let i = 0; i <= idx; i++) if (messages[i].role === "assistant") n++;
    const nn = String(n).padStart(2, "0");
    downloadMarkdown(`statrag-${slug}-a${nn}.md`, assistantMessageToMarkdown(msg));
  }, [messages, activeConvTitle]);
```

> If `useCallback` is not already imported in `App.tsx`, add it to the React import. Check the existing top import line for `react`.

- [ ] **Step 3: Pass props to Topbar and MessageThread**

On `<Topbar … />`, add (after `onToggleTheme={…}`):

```tsx
        onExportConversation={handleExportConversation}
        exportDisabled={messages.length === 0}
```

On `<MessageThread … />`, add (after `onFork={handleFork}`):

```tsx
              onExportMessage={handleExportMessage}
```

- [ ] **Step 4: Typecheck + run all frontend tests**

Run: `cd web && npx tsc --noEmit && npx vitest run`
Expected: typecheck clean; all vitest suites green (including the two new files).

- [ ] **Step 5: Commit**

```bash
git add web/src/App.tsx
git commit -m "feat(web): wire chat markdown export handlers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Browser-verify on :5175 (Chrome MCP) + docs

**Files:**
- Modify: `docs/services/chat.md`
- Modify: `docs/system/changelog.md`
- Modify: `docs/common ground/Elements/index.html` (add §N for export; pill → ✓ after verify)

- [ ] **Step 1: Confirm dev stack is up**

Run: `curl -s http://localhost:8766/api/health && curl -s -o /dev/null -w "%{http_code}" http://localhost:5175/`
Expected: `{"status":"ok"}` and `200`. If not, run `./scripts/dev.sh` in the background.

- [ ] **Step 2: Browser-verify the per-answer export (Chrome MCP)**

Open `http://localhost:5175/`. Type a real tutor question (real keystrokes — `form_input` does NOT fire React onChange) e.g. "What is variance?" and submit. Wait for the answer to complete. Click the per-answer export icon. Confirm a `statrag-*-a01.md` download. Open it and confirm: answer text present, math as `$$…$$` if any, citations section if TutorAnswer, **no raw JSON leakage**.

- [ ] **Step 3: Browser-verify the full-conversation export**

Click the Topbar download button. Confirm a `statrag-<slug>.md` download with the `# title` header, `> Exported from statrag` line, and both `## You` and `## TUTOR` turns in order.

- [ ] **Step 4: Verify a structured mode**

Switch to Quiz mode (⌘K or mode picker), ask for a quiz, wait for the structured view, export the answer. Confirm numbered questions + lettered options + `**Answer:**` lines in the `.md` (faithful markdown, not JSON).

- [ ] **Step 5: Monitor console for errors**

Use Chrome MCP `read_console_messages` during the run. Expected: no errors from export. Note any warnings.

- [ ] **Step 6: Update docs**

- `docs/services/chat.md`: add a short "Markdown export" subsection — Topbar button exports the active conversation; per-answer icon exports one answer; pure frontend (`web/src/lib/exportMarkdown.ts`), no backend.
- `docs/system/changelog.md`: prepend a dated (2026-05-29) entry summarizing the feature and the verified browser result.
- `docs/common ground/Elements/index.html`: add a `§N` section documenting the export feature; set its pill to "✓ implemented (2026-05-29)".

- [ ] **Step 7: Commit**

```bash
git add docs/services/chat.md docs/system/changelog.md "docs/common ground/Elements/index.html"
git commit -m "docs: chat markdown export — chat.md, changelog, reference graph

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Definition of Done

- [ ] `exportMarkdown.ts` + `exportStructured.ts` implemented; all unit tests green.
- [ ] `tsc --noEmit` clean; `vitest run` fully green.
- [ ] Topbar button exports full conversation; per-answer icon exports one answer.
- [ ] Browser-verified on :5175: prose, math, citations, and a structured mode all render faithfully in the downloaded `.md`; no JSON leakage; console clean.
- [ ] `docs/services/chat.md`, `changelog.md`, and reference graph `index.html` §N updated (pill → ✓).
- [ ] Chinese wall intact (no `src/` change).
