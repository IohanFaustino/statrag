import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import QAAnswerCard from "./QAAnswerCard";
import type { QAAnswer, TutorCitation } from "../types";

const base: QAAnswer = {
  text: "The tradeoff arises because lowering one raises the other.",
  scope: { target_gap: "why bias and variance trade off", assumed_known: ["what bias is"], answer_form: "explanation" },
  citations: [],
  math_blocks: [],
  grounding: { ok: true, unsupported: [], confidence: 0.95 },
};

describe("QAAnswerCard", () => {
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
    const html = renderToStaticMarkup(
      <QAAnswerCard answer={{ ...base, scope: { ...base.scope, assumed_known: [] } }} />
    );
    expect(html).not.toContain("assuming you know");
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
});
