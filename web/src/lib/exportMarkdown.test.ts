import { describe, it, expect } from "vitest";
import {
  slugify,
  assistantMessageToMarkdown,
  userMessageToMarkdown,
  conversationToMarkdown,
} from "./exportMarkdown";
import type { AssistantMessage, UserMessage, FacilitateDigest } from "../types";

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
    expect(md).toMatch(/^> \*\*Fig 2\.1/m);
    expect(md).toContain("> ![A scatter plot](/img/fig.png)");
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
    expect(md.endsWith("\n")).toBe(true);
  });

  it("renders FacilitateDigest with key_points, footnote refs, and footnote defs", () => {
    const digest: FacilitateDigest = {
      mode: "facilitate",
      scope: { book_slug: "hansen", chapter_id: "ch07", requested_subtopics: [], resolution: [] },
      intro: "Intro text.",
      blocks: [
        {
          h2_path: "7.2 Variance",
          section_id: "s7.2",
          key_points: ["kp1"],
          body: "Uses [[c1]] here.",
          concepts: [
            {
              id: "c1",
              term: "Term",
              kind: "concept",
              explanation: "Expl.",
              provenance: {
                book_slug: "hansen", book_name: "Econometrics",
                authors_short: "Hansen", section: "7.2",
                page_from: 172, page_to: 173,
                chunk_id: "hansen_ch07_s7.2", same_author: true, fallback: false,
              },
            },
          ],
          page_from: 172,
          page_to: 175,
        },
      ],
      outro: "Outro text.",
      math_blocks: [],
      grounding: { ok: true, unsupported: [], confidence: 0.95 },
    };
    const msg = baseAssistant({
      mode: "facilitate",
      structuredOutput: { schema: "FacilitateDigest", data: digest },
    });
    const md = assistantMessageToMarkdown(msg);
    expect(md).toContain("- kp1");
    expect(md).toContain("[^b0c1]");
    expect(md).not.toContain("[[c1]]");
    const defLine = md.split("\n").find((l) => l.startsWith("[^b0c1]:"));
    expect(defLine).toBeDefined();
    expect(defLine).toContain("Term");
    expect(defLine).toContain("Expl.");
    expect(defLine).toContain("Hansen");
  });

  it("skips pending/streaming assistant turns", () => {
    const pending = baseAssistant({ status: "pending", blocks: [] });
    const mdPending = conversationToMarkdown([pending], { title: "x" });
    expect(mdPending.toLowerCase()).not.toContain("incomplete");
    expect(mdPending).not.toContain("## TUTOR");

    const streaming = baseAssistant({ status: "streaming", blocks: [] });
    const mdStreaming = conversationToMarkdown([streaming], { title: "x" });
    expect(mdStreaming.toLowerCase()).not.toContain("incomplete");
    expect(mdStreaming).not.toContain("## TUTOR");
  });
});
