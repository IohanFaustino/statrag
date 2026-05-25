import { describe, it, expect } from "vitest";
import { splitIntoBlocks } from "./TutorView";

describe("splitIntoBlocks — blockquote (#7 verbatim formal statement)", () => {
  it("groups consecutive > lines into one quote block", () => {
    const blocks = splitIntoBlocks(
      "Intro line.\n\n> A theorem stated verbatim,\n> across two lines. [1]\n\nAfter.",
    );
    const quotes = blocks.filter((b) => b.kind === "quote");
    expect(quotes).toHaveLength(1);
    expect((quotes[0] as { text: string }).text).toContain("verbatim");
    expect((quotes[0] as { text: string }).text).toContain("[1]");
    // surrounding prose stays paragraphs
    expect(blocks.filter((b) => b.kind === "para")).toHaveLength(2);
  });

  it("does not treat normal prose as a quote", () => {
    const blocks = splitIntoBlocks("Plain paragraph with no marker.");
    expect(blocks.some((b) => b.kind === "quote")).toBe(false);
  });
});

describe("splitIntoBlocks — §12 ### subsection headers", () => {
  it("parses ### as an h3 block, distinct from ## (h2 section)", () => {
    const blocks = splitIntoBlocks(
      "## Definition\n\nFraming sentence.\n\n### Bias\n\nThe bias is E[θ̂]-θ. [1]\n\n### MSE\n\nMSE combines them.",
    );
    expect(blocks.filter((b) => b.kind === "h2")).toHaveLength(1);
    const h3 = blocks.filter((b) => b.kind === "h3");
    expect(h3).toHaveLength(2);
    expect((h3[0] as { text: string }).text).toBe("Bias");
    expect((h3[1] as { text: string }).text).toBe("MSE");
  });
});
