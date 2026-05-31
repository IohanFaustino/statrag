import { describe, it, expect } from "vitest";
import { structuredToMarkdown } from "./exportStructured";
import type { TutorAnswer } from "../types";

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

describe("structuredToMarkdown — unknown schema", () => {
  it("falls back to a json fence", () => {
    const md = structuredToMarkdown({ schema: "Mystery", data: { x: 1 } });
    expect(md).toContain("```json");
    expect(md).toContain("\"x\": 1");
  });
});
