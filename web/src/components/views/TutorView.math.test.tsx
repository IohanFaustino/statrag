/**
 * Tests for the inline-math tokenizer desync + prose-guard word-count fixes.
 *
 * Bug: renderInlineWithCites prose-guard (proseWords >= 3) did NOT consume the
 * rejected $…$ span, so i was advanced by only 1 (the opening `$` as plain
 * text), desyncing all subsequent `$` pairing.  Additionally, LaTeX command
 * names (\mathrm, \delta) were counted as prose words, causing valid math like
 * `\mathrm{Var}(X)/\delta^2` to trip the guard.
 *
 * Fix: (a) strip `\\[a-zA-Z]+` before counting; (b) on reject, emit the full
 * `$…$` span as text and advance i = end + 1.
 *
 * MathInline renders as <span></span> in renderToStaticMarkup (useEffect/ref
 * not called in SSR). We detect math slots by counting empty <span> elements.
 * Plain text from React.Fragment is emitted directly into the HTML without a
 * wrapper element, so it appears as bare text.
 */
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { renderInlineWithCites } from "./TutorView";
import type { TutorCitation } from "../../types";

function render(text: string, cites?: Map<number, TutorCitation>): string {
  const nodes = renderInlineWithCites(
    text,
    cites ?? new Map(),
    null,
    () => {},
  );
  return renderToStaticMarkup(<>{nodes}</>);
}

/**
 * MathInline renders as <span></span> (empty, no attributes) in static markup
 * because KaTeX is applied only inside useEffect. Count those empty spans as
 * math slots.
 */
function mathSpanCount(html: string): number {
  return (html.match(/<span><\/span>/g) ?? []).length;
}

describe("renderInlineWithCites — inline-math tokenizer (desync + word-count)", () => {
  describe("Chebyshev example: two math spans, no prose desync", () => {
    const input = String.raw`a $\mathrm{Var}(X)/\delta^2$. The parameter $\delta$ is x`;

    it("renders exactly TWO inline math spans", () => {
      const html = render(input);
      expect(mathSpanCount(html)).toBe(2);
    });

    it("'. The parameter ' appears as plain text in the output", () => {
      const html = render(input);
      expect(html).toContain(". The parameter ");
    });

    it("no literal $ remains in the rendered output (outside data-* attrs)", () => {
      const html = render(input);
      // React.Fragment plain text is emitted bare — any $ in output is a bug.
      expect(html).not.toContain("$");
    });
  });

  describe("prose guard: genuine $…$ prose consumed as text, no desync", () => {
    it("prose span with >=3 words emitted as literal text (dollar signs visible)", () => {
      // "for the item and more" has 5 natural-language words → guard fires.
      const input = "cost is $5 for the item and more$ then $x$ wins";
      const html = render(input);
      // The prose span must appear verbatim, delimiters included.
      expect(html).toContain("$5 for the item and more$");
    });

    it("following $x$ after prose span still renders as math (no desync)", () => {
      const input = "cost is $5 for the item and more$ then $x$ wins";
      const html = render(input);
      // After the prose span is correctly consumed, $x$ is the next pair and
      // must be rendered as math (one empty <span> in output).
      expect(mathSpanCount(html)).toBe(1);
    });
  });

  describe("latex-heavy math is not mistaken for prose", () => {
    it("\\frac{1}{n}\\sum renders as math (not literal text)", () => {
      const input = String.raw`The mean is $\frac{1}{n}\sum_{i=1}^{n} X_i$ exactly`;
      const html = render(input);
      // Should produce one math span, not spill the $ into plain text.
      expect(mathSpanCount(html)).toBe(1);
      // No stray $ in output.
      expect(html).not.toContain("$");
    });

    it("\\sigma^2 / n renders as math", () => {
      const input = String.raw`Variance is $\sigma^2 / n$ per sample`;
      const html = render(input);
      expect(mathSpanCount(html)).toBe(1);
      expect(html).not.toContain("$");
    });
  });
});
