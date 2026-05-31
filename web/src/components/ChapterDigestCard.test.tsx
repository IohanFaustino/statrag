import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import ChapterDigestCard from "./ChapterDigestCard";
import type { ChapterDigest } from "../types";

const digest: ChapterDigest = {
  mode: "facilitate",
  scope: {
    book_slug: "islp",
    chapter_id: "ch02",
    requested_subtopics: ["the tradeoff"],
    resolution: [
      {
        asked: "the tradeoff",
        matched_h2: "2.2 | Bias-Variance",
        section_id: "2.2",
        score: 0.8,
      },
    ],
  },
  intro: "Covers A then B.",
  blocks: [
    {
      h2_path: "2.1 | A",
      section_id: "2.1",
      body: "first body",
      page_from: 10,
      page_to: 11,
    },
    {
      h2_path: "2.2 | Bias-Variance",
      section_id: "2.2",
      body: "second body",
      page_from: 12,
      page_to: 13,
    },
  ],
  outro: "They fit together.",
  citations: [],
  math_blocks: [],
  grounding: { ok: true, unsupported: [], confidence: 0.9 },
};

describe("ChapterDigestCard", () => {
  it("renders blocks in order", () => {
    const html = renderToStaticMarkup(<ChapterDigestCard digest={digest} />);
    // Use body text which is unique to each block (not repeated in resolution line)
    const aIdx = html.indexOf("first body");
    const bIdx = html.indexOf("second body");
    expect(aIdx).toBeGreaterThanOrEqual(0);
    expect(bIdx).toBeGreaterThan(aIdx);
  });

  it("shows the resolution line when a subtopic was fuzzy-matched", () => {
    const html = renderToStaticMarkup(<ChapterDigestCard digest={digest} />);
    expect(html.toLowerCase()).toContain("interpreted");
  });

  it("shows a grounding badge", () => {
    const html = renderToStaticMarkup(<ChapterDigestCard digest={digest} />);
    expect(html).toContain('data-testid="chapter-grounding-badge"');
  });
});
