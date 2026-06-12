import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import QAAnswerCard from "./QAAnswerCard";
import type { QAAnswer, QAStoryAnswer, StoryCitation, TutorCitation } from "../types";

const base: QAAnswer = {
  text: "The tradeoff arises because lowering one raises the other.",
  scope: { target_gap: "why bias and variance trade off", assumed_known: ["what bias is"], answer_form: "explanation" },
  citations: [],
  math_blocks: [],
  grounding: { ok: true, unsupported: [], confidence: 0.95 },
};

describe("QAAnswerCard — legacy QAAnswer shape", () => {
  it("renders the answer text", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={base} />);
    expect(html).toContain("lowering one raises the other");
  });

  it("shows the scope line with target gap", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={base} />);
    expect(html).toContain("why bias and variance trade off");
  });

  it("shows a grounded badge when grounding.ok", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={base} />);
    expect(html.toLowerCase()).toContain("grounded");
  });

  it("shows a partial badge when grounding fails", () => {
    const html = renderToStaticMarkup(
      <QAAnswerCard answer={{ ...base, grounding: { ok: false, unsupported: ["x"], confidence: 0.3 } }} />
    );
    expect(html.toLowerCase()).toContain("partial");
  });

  it("does not show 'assuming you know' when assumed_known is empty", () => {
    const explicitScope = { target_gap: "why bias and variance trade off", assumed_known: [], answer_form: "explanation" as const };
    const html = renderToStaticMarkup(
      <QAAnswerCard answer={{ ...base, scope: explicitScope }} />
    );
    expect(html).not.toContain("assuming you know");
  });

  it("renders a deepagent answer (thesis/deepening/synthesis, no scope) without crashing", () => {
    const answer: QAAnswer = {
      thesis: "The bias of an estimator is its expected error.",
      deepening: "It is defined as E[theta_hat] minus theta.",
      synthesis: "Unbiased means this quantity is zero.",
      sub_queries: ["define bias"],
      citations: [],
      math_blocks: [],
      grounding: { ok: true, unsupported: [], confidence: 0.9 },
    };
    const html = renderToStaticMarkup(<QAAnswerCard answer={answer} />);
    expect(html).toContain("expected error");
    expect(html).toContain("Unbiased means");
    // No scope → no "Answering:" line, and no crash.
    expect(html).not.toContain("Answering:");
  });

  it("renders inline [1] citation marker as a citation pill (not literal '[1]') when a matching citation exists", () => {
    const citations: TutorCitation[] = [
      { index: 1, book_name: "Stats 101", chapter: "Ch3", authors_short: "Freedman", year: 2009 },
    ];
    const answer: QAAnswer = {
      ...base,
      text: "See [1] for the derivation.",
      citations,
    };
    const html = renderToStaticMarkup(<QAAnswerCard answer={answer} />);
    // The [1] marker should be rendered as an anchor linking to #cite-1, not as the literal text "[1]"
    expect(html).toContain('href="#cite-1"');
    // The pill should carry the citation index text
    expect(html).toContain("[1]");
  });

  it("does NOT render [1] as a raw string when a citation is present", () => {
    const citations: TutorCitation[] = [
      { index: 1, book_name: "Stats 101", chapter: "Ch3", authors_short: "Freedman", year: 2009 },
    ];
    const answer: QAAnswer = {
      ...base,
      text: "See [1] for the derivation.",
      citations,
    };
    const html = renderToStaticMarkup(<QAAnswerCard answer={answer} />);
    // There must be a link element, not just bare literal text outside a link
    expect(html).toContain('href="#cite-1"');
  });

  it("renders math_blocks entries via MathBlock (produces a math-block container)", () => {
    const answer: QAAnswer = {
      ...base,
      math_blocks: ["E = mc^2", "\\sigma^2"],
    };
    const html = renderToStaticMarkup(<QAAnswerCard answer={answer} />);
    // MathBlock renders inside .math-block divs; the qa-card wrapper should be present
    expect(html).toContain("qa-card__math-blocks");
    expect(html).toContain("qa-card__math-block");
  });

  it("does not render math_blocks section when array is empty", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={base} />);
    expect(html).not.toContain("qa-card__math-blocks");
  });

  it("does not render grounding badge when grounding field is absent", () => {
    const answer: QAAnswer = { ...base, grounding: undefined };
    const html = renderToStaticMarkup(<QAAnswerCard answer={answer} />);
    expect(html).not.toContain("qa-card__badge");
    expect(html).not.toContain("grounded");
    expect(html).not.toContain("partial");
  });
});

describe("QAAnswerCard — QAStoryAnswer shape", () => {
  const corpusCite: StoryCitation = {
    kind: "corpus",
    label: "Hansen Ch3",
    book_slug: "hansen",
    book_name: "Econometrics",
    authors: "Hansen",
    year: 2022,
    chapter: "ch03",
  };
  const wikiCite: StoryCitation = {
    kind: "wikipedia",
    label: "Bias-variance tradeoff",
    url: "https://en.wikipedia.org/wiki/Bias-variance_tradeoff",
    title: "Bias-variance tradeoff",
  };
  const storyAnswer: QAStoryAnswer = {
    intro: "Bias and variance are foundational concepts in statistics.",
    deepening: "The tradeoff arises because [1] reducing model complexity increases bias while decreasing variance.",
    conclusion: "Understanding this tradeoff guides model selection and regularization.",
    citations: [corpusCite, wikiCite],
    math_blocks: ["\\hat{\\beta} = (X^T X)^{-1} X^T y"],
    grounding: { ok: true, unsupported: [], confidence: 0.9 },
  };

  it("renders intro text in story mode", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    expect(html).toContain("foundational concepts in statistics");
  });

  it("renders deepening text in story mode", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    expect(html).toContain("reducing model complexity");
  });

  it("renders conclusion text in story mode", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    expect(html).toContain("guides model selection");
  });

  it("renders a corpus chip (📕) for corpus citations", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    expect(html).toContain("📕");
    expect(html).toContain("Hansen Ch3");
  });

  it("renders a wikipedia chip (🌐) as an <a> with the wiki url", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    expect(html).toContain("🌐");
    expect(html).toContain("https://en.wikipedia.org/wiki/Bias-variance_tradeoff");
    // wiki chip is an anchor
    expect(html).toMatch(/<a[^>]*href="https:\/\/en\.wikipedia\.org[^"]*"[^>]*>/);
  });

  it("renders math_blocks in story mode", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    expect(html).toContain("qa-card__math-blocks");
  });

  it("renders corpus and wikipedia citation chips (not a redundant count hint)", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    // The footer states the source count; the card shows 📕/🌐 chips instead.
    expect(html).toContain("citation-chip--corpus");
    expect(html).toContain("citation-chip--wiki");
    expect(html).not.toContain("corpus +"); // old "N corpus + N wikipedia sources" hint gone
  });

  it("shows grounding badge in story mode", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    expect(html.toLowerCase()).toContain("grounded");
  });

  it("does NOT render story as legacy text path", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    // Story mode should use qa-card__story-* classes, not the legacy body
    expect(html).toContain("qa-card__story");
    // Must not trip on undefined 'text' field
    expect(html).not.toContain("undefined");
  });

  it("story answer does not bleed into deepagent path (no thesis heading)", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    // There should be no scope/Answering line (story has no scope header)
    expect(html).not.toContain("Answering:");
  });

  // ── Finding 3: corpus_weak caveat ────────────────────────────────────────────

  it("shows corpus_weak caveat when grounding.corpus_weak is true", () => {
    const weakAnswer: QAStoryAnswer = {
      ...storyAnswer,
      grounding: { ok: true, corpus_weak: true },
    };
    const html = renderToStaticMarkup(<QAAnswerCard answer={weakAnswer} />);
    expect(html).toContain("Not found in your textbooks");
    expect(html).toContain("answered from Wikipedia");
  });

  it("does NOT show corpus_weak caveat when grounding.corpus_weak is false", () => {
    const strongAnswer: QAStoryAnswer = {
      ...storyAnswer,
      grounding: { ok: true, corpus_weak: false },
    };
    const html = renderToStaticMarkup(<QAAnswerCard answer={strongAnswer} />);
    expect(html).not.toContain("Not found in your textbooks");
  });

  it("does NOT show corpus_weak caveat when grounding.corpus_weak is absent", () => {
    const html = renderToStaticMarkup(<QAAnswerCard answer={storyAnswer} />);
    // storyAnswer.grounding has no corpus_weak field
    expect(html).not.toContain("Not found in your textbooks");
  });
});
