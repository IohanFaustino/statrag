import { describe, it, expect } from "vitest";
import { structuredToMarkdown } from "./exportStructured";
import type { TutorAnswer, QAAnswer } from "../types";

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

describe("structuredToMarkdown — unknown schema", () => {
  it("falls back to a json fence", () => {
    const md = structuredToMarkdown({ schema: "Mystery", data: { x: 1 } });
    expect(md).toContain("```json");
    expect(md).toContain("\"x\": 1");
  });
});
