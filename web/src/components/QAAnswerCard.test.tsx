import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import QAAnswerCard from "./QAAnswerCard";
import type { QAAnswer } from "../types";

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
});
