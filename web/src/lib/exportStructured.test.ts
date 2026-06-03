import { describe, it, expect } from "vitest";
import { structuredToMarkdown } from "./exportStructured";
import type { TutorAnswer, QAAnswer, ChapterDigest } from "../types";

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

describe("structuredToMarkdown — QAAnswer", () => {
  it("renders prose + scope + citations as markdown (not a json fence)", () => {
    const data: QAAnswer = {
      text: "The tradeoff arises from minimising total error.",
      scope: {
        target_gap: "why bias and variance trade off",
        assumed_known: ["what bias is", "what variance is"],
        answer_form: "explanation",
      },
      citations: [
        { index: 1, book_name: "ESL", chapter: "Ch7", section: "§7.3", authors_short: "Hastie", year: 2009 },
      ],
      math_blocks: ["\\text{MSE} = \\text{Bias}^2 + \\text{Var}"],
      grounding: { ok: true, unsupported: [], confidence: 0.92 },
    };
    const md = structuredToMarkdown({ schema: "QAAnswer", data });
    // Prose is present
    expect(md).toContain("minimising total error");
    // Scope line is present
    expect(md).toContain("why bias and variance trade off");
    expect(md).toContain("assuming you know");
    // Citations section is present
    expect(md).toContain("Citations");
    expect(md).toContain("Hastie");
    expect(md).toContain("§7.3");
    // Math section is present
    expect(md).toContain("Math");
    expect(md).toContain("$$");
    expect(md).toContain("\\text{MSE}");
    // NOT a json fence
    expect(md).not.toContain("```json");
  });

  it("omits Citations and Math sections when arrays are empty", () => {
    const data: QAAnswer = {
      text: "Short answer.",
      scope: { target_gap: "some gap", assumed_known: [], answer_form: "definition" },
      citations: [],
      math_blocks: [],
      grounding: { ok: true, unsupported: [], confidence: 1.0 },
    };
    const md = structuredToMarkdown({ schema: "QAAnswer", data });
    expect(md).toContain("Short answer.");
    expect(md).not.toContain("Citations");
    expect(md).not.toContain("Math");
  });
});

describe("structuredToMarkdown — ChapterDigest (resume / facilitate-chapter)", () => {
  const data: ChapterDigest = {
    mode: "resume",
    scope: { book_slug: "hansen", chapter_id: "ch07", requested_subtopics: [], resolution: [] },
    intro: "This chapter recaps asymptotic theory.",
    blocks: [
      { h2_path: "7.2 ASYMPTOTIC LIMITS", section_id: "s2", body: "A sequence **converges** when $|a_n-a|\\le\\delta$.", page_from: 1, page_to: 2 },
      { h2_path: "7.3 CONVERGENCE IN PROBABILITY", section_id: "s3", body: "Probabilistic closeness.", page_from: 3, page_to: 4 },
    ],
    outro: "Together these build the WLLN.",
    citations: [
      { index: 1, book_name: "Econometrics", chapter: "Ch7", section: "§7.2", authors_short: "Hansen", year: 2022, quote: "limit def" },
    ],
    math_blocks: ["\\bar{X}_n \\xrightarrow{p} \\mu"],
    grounding: { ok: true, unsupported: [], confidence: 0.9 },
  };

  it("renders intro, per-section headings + bodies, outro, citations, math as markdown", () => {
    const md = structuredToMarkdown({ schema: "ChapterDigest", data });
    expect(md).toContain("This chapter recaps asymptotic theory.");
    expect(md).toContain("## 7.2 ASYMPTOTIC LIMITS");
    expect(md).toContain("converges");
    expect(md).toContain("## 7.3 CONVERGENCE IN PROBABILITY");
    expect(md).toContain("Together these build the WLLN.");
    expect(md).toContain("Citations");
    expect(md).toContain("Hansen");
    expect(md).toContain("§7.2");
    expect(md).toContain("Math");
    expect(md).toContain("$$");
    expect(md).toContain("\\bar{X}_n");
  });

  it("does NOT emit a raw json fence (the bug)", () => {
    const md = structuredToMarkdown({ schema: "ChapterDigest", data });
    expect(md).not.toContain("```json");
    expect(md).not.toContain("\"section_id\"");
  });

  it("preserves block order (chapter order is list order)", () => {
    const md = structuredToMarkdown({ schema: "ChapterDigest", data });
    expect(md.indexOf("7.2 ASYMPTOTIC LIMITS")).toBeLessThan(md.indexOf("7.3 CONVERGENCE IN PROBABILITY"));
  });
});

describe("structuredToMarkdown — unknown schema", () => {
  it("falls back to a json fence", () => {
    const md = structuredToMarkdown({ schema: "Mystery", data: { x: 1 } });
    expect(md).toContain("```json");
    expect(md).toContain("\"x\": 1");
  });
});
