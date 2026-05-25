import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { renderInlineWithCites } from "./TutorView";

// Render the inline tokenizer output to static HTML for assertion.
function render(text: string): string {
  const nodes = renderInlineWithCites(text, new Map(), null, () => {});
  return renderToStaticMarkup(<>{nodes}</>);
}

describe("renderInlineWithCites — emphasis", () => {
  it("renders single-asterisk italic as <em>", () => {
    const html = render("the *sampling distribution* is key");
    expect(html).toContain("<em");
    expect(html).toContain("sampling distribution");
    expect(html).not.toContain("*sampling distribution*");
  });

  it("renders double-asterisk bold as <strong> (not em)", () => {
    const html = render("this is **important** text");
    expect(html).toContain("<strong");
    expect(html).toContain("important");
    expect(html).not.toContain("<em");
  });

  it("handles bold and italic in the same line", () => {
    const html = render("**bold** and *italic* together");
    expect(html).toContain("<strong");
    expect(html).toContain("<em");
  });

  it("leaves an unmatched single asterisk as literal text", () => {
    const html = render("2 * 3 = 6");
    expect(html).not.toContain("<em");
    expect(html).toContain("*");
  });
});
