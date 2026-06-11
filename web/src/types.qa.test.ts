import { describe, it, expect } from "vitest";
import type { ModeId, QAAnswer, QAScope, QAStoryAnswer, StoryCitation } from "./types";

describe("qa types", () => {
  it("ModeId includes qa", () => {
    const m: ModeId = "qa";
    expect(m).toBe("qa");
  });
  it("QAAnswer shape", () => {
    const scope: QAScope = { target_gap: "x", assumed_known: [], answer_form: "explanation" };
    const a: QAAnswer = { text: "t", scope, citations: [], math_blocks: [], grounding: { ok: true, unsupported: [], confidence: 0.9 } };
    expect(a.scope?.target_gap).toBe("x");
  });
  it("QAScope has wiki_terms field", () => {
    const scope: QAScope = {
      target_gap: "bias vs variance",
      assumed_known: ["OLS"],
      answer_form: "explanation",
      wiki_terms: ["bias-variance tradeoff", "regularization"],
    };
    expect(scope.wiki_terms).toHaveLength(2);
    expect(scope.wiki_terms![0]).toBe("bias-variance tradeoff");
  });
  it("QAStoryAnswer typechecks with all fields", () => {
    const cite: StoryCitation = {
      kind: "corpus",
      label: "Hansen Ch3",
      book_slug: "hansen",
      book_name: "Econometrics",
      authors: "Hansen",
      year: 2022,
      chapter: "ch03",
      section_id: "3.1",
      pages: "45-50",
      title: "Bias",
      url: undefined,
      chunk_id: "hansen-ch03-3.1",
    };
    const wikiCite: StoryCitation = {
      kind: "wikipedia",
      label: "Bias-variance tradeoff",
      url: "https://en.wikipedia.org/wiki/Bias-variance_tradeoff",
      title: "Bias-variance tradeoff",
    };
    const answer: QAStoryAnswer = {
      intro: "Bias and variance are fundamental concepts.",
      deepening: "The tradeoff arises because [1] reduces bias at the cost of variance.",
      conclusion: "Understanding this tradeoff guides model selection.",
      scope: {
        target_gap: "bias vs variance",
        assumed_known: ["OLS"],
        answer_form: "explanation",
        wiki_terms: ["bias-variance tradeoff"],
      },
      citations: [cite, wikiCite],
      math_blocks: ["\\hat{\\beta} = (X^T X)^{-1} X^T y"],
      grounding: {
        ok: true,
        unsupported: [],
        confidence: 0.92,
        unbound_markers: 0,
        lints: [],
        corpus_weak: false,
        wiki_unavailable: false,
      },
    };
    expect(answer.intro).toBeTruthy();
    expect(answer.conclusion).toBeTruthy();
    expect(answer.citations).toHaveLength(2);
    expect(answer.scope?.wiki_terms).toHaveLength(1);
    expect(answer.grounding?.unbound_markers).toBe(0);
  });
});
