/**
 * Tests for the Phase-1 citation regex robustness upgrade.
 *
 * renderInlineWithCites must now handle:
 *   - single [N]         → 1 pill
 *   - comma list [1, 2]  → 2 pills separated by ","
 *   - range [1]–[3]      → 3 pills (indices 1, 2, 3)
 *   - dash range [1-3]   → 3 pills
 *   - [F1] figure branch → unchanged (not affected)
 *   - malformed []       → literal text
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

/** Count how many citation pills (<a href="#cite-N">) appear in the HTML. */
function countPills(html: string): number {
  return (html.match(/href="#cite-\d+"/g) ?? []).length;
}

/** Collect all pill href values */
function pillHrefs(html: string): string[] {
  return (html.match(/href="#cite-\d+"/g) ?? []);
}

describe("renderInlineWithCites — citation regex (Phase 1)", () => {
  it("[1] single → 1 pill linking #cite-1", () => {
    const html = render("See [1] for details.");
    expect(countPills(html)).toBe(1);
    expect(html).toContain('href="#cite-1"');
  });

  it("[1, 2] comma list → 2 pills", () => {
    const html = render("Sources [1, 2] show this.");
    expect(countPills(html)).toBe(2);
    expect(html).toContain('href="#cite-1"');
    expect(html).toContain('href="#cite-2"');
  });

  it("[1,2,3] comma list no spaces → 3 pills", () => {
    const html = render("[1,2,3]");
    expect(countPills(html)).toBe(3);
    expect(pillHrefs(html)).toContain('href="#cite-1"');
    expect(pillHrefs(html)).toContain('href="#cite-2"');
    expect(pillHrefs(html)).toContain('href="#cite-3"');
  });

  it("[1]–[3] en-dash range → 3 pills (1, 2, 3)", () => {
    // En-dash range expansion: [1–3] expands to indices 1, 2, 3
    const html = render("[1–3]");
    expect(countPills(html)).toBe(3);
    expect(html).toContain('href="#cite-1"');
    expect(html).toContain('href="#cite-2"');
    expect(html).toContain('href="#cite-3"');
  });

  it("[1-3] hyphen range → 3 pills (1, 2, 3)", () => {
    const html = render("[1-3]");
    expect(countPills(html)).toBe(3);
    expect(html).toContain('href="#cite-1"');
    expect(html).toContain('href="#cite-2"');
    expect(html).toContain('href="#cite-3"');
  });

  it("[5] single → 1 pill linking #cite-5", () => {
    const html = render("See [5].");
    expect(countPills(html)).toBe(1);
    expect(html).toContain('href="#cite-5"');
  });

  it("[F1] figure branch unchanged — renders fig link not cite", () => {
    const html = render("See [F1] for the diagram.");
    // Figure pill uses href="#fig-1", NOT "#cite-1"
    expect(html).toContain('href="#fig-1"');
    expect(countPills(html)).toBe(0); // no cite pills
  });

  it("comma separator rendered between pills in multi-citation", () => {
    const html = render("[1, 2]");
    // Both pills appear and a comma is present between them
    expect(html).toContain('href="#cite-1"');
    expect(html).toContain('href="#cite-2"');
    expect(html).toContain(",");
  });

  it("malformed [] falls through to literal text", () => {
    const html = render("Text [] here.");
    expect(countPills(html)).toBe(0);
    expect(html).toContain("[]");
  });
});
