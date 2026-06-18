/**
 * Tests for the TutorFormalDef structured render path.
 *
 * Verifies that formal_statements[] in TutorAnswer are rendered as
 * labelled verbatim blockquotes with cite markers, distinct from the
 * legacy text-based formal_statement fallback.
 */
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { renderFormalStatements } from "./TutorView";
import type { TutorFormalDef } from "../../types";

function renderFormalStatementsTest(defs: TutorFormalDef[]): string {
  const nodes = renderFormalStatements(
    defs,
    new Map(),
    null,
    () => {},
  );
  return renderToStaticMarkup(<>{nodes}</>);
}

describe("renderFormalStatements", () => {
  it("renders a single formal definition as a blockquote with citation", () => {
    const defs: TutorFormalDef[] = [
      {
        kind: "definition",
        label: "Definition 14.1",
        statement: "$$F(x_{t})=F(x_{t+h})$$",
        cite: 1,
      },
    ];
    const html = renderFormalStatementsTest(defs);
    // renderFormalStatements uses renderInlineWithCites which renders
    // **bold** as <strong>, not raw markdown. Verify the label appears
    // inside a <strong> element within a <blockquote>.
    expect(html).toContain("<strong");
    expect(html).toContain("Definition 14.1.");
    // x_{t} and x_{t+h} are bare-math atoms rendered as KaTeX (<span> slots),
    // not literal text. Verify KaTeX slots exist alongside the label.
    expect(html).toContain("<span></span>");
    expect(html).toContain("[1]");
  });

  it("uses kind as label when label is empty", () => {
    const defs: TutorFormalDef[] = [
      {
        kind: "theorem",
        label: "",
        statement: "E[x_t] = μ for all t",
        cite: 2,
      },
    ];
    const html = renderFormalStatementsTest(defs);
    // Kind is capitalised as the label when label is empty
    expect(html).toContain("Theorem.");
    // x_t is a bare-math atom rendered as KaTeX, not literal text.
    expect(html).toContain("Theorem.");
    expect(html).toContain("<span></span>");
  });

  it("renders multiple formal statements as separate blockquotes", () => {
    const defs: TutorFormalDef[] = [
      {
        kind: "definition",
        label: "Definition 14.1",
        statement: "strictly stationary if $$F(x_{t})=F(x_{t+h})$$",
        cite: 1,
      },
      {
        kind: "definition",
        label: "Definition 14.2",
        statement: "weakly stationary if $$E[x_t]=\\mu$$",
        cite: 2,
      },
    ];
    const html = renderFormalStatementsTest(defs);
    // Should have two blockquote elements
    const quoteCount = (html.match(/<blockquote/g) || []).length;
    expect(quoteCount).toBe(2);
    expect(html).toContain("Definition 14.1");
    expect(html).toContain("Definition 14.2");
  });

  it("renders formal statements with LaTeX inline math", () => {
    const defs: TutorFormalDef[] = [
      {
        kind: "theorem",
        label: "Theorem 2.1",
        statement: "MSE = bias² + variance + irreducible error",
        cite: 3,
      },
    ];
    const html = renderFormalStatementsTest(defs);
    expect(html).toContain("Theorem 2.1.");
    expect(html).toContain("MSE = bias² + variance + irreducible error");
  });

  it("renders formal statements with LaTeX commands via the existing render path", () => {
    const defs: TutorFormalDef[] = [
      {
        kind: "definition",
        label: "Definition 3.3",
        statement: "Var(X) = E[X²] − (E[X])²",
        cite: 4,
      },
    ];
    const html = renderFormalStatementsTest(defs);
    expect(html).toContain("Definition 3.3.");
  });

  it("handles empty formal_statements array gracefully", () => {
    const defs: TutorFormalDef[] = [];
    const html = renderFormalStatementsTest(defs);
    // Empty array should produce no blockquotes
    expect(html).not.toContain("<blockquote");
  });
});
