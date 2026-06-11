// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ExtensionPipelineDiagram from "./ExtensionPipelineDiagram";

describe("ExtensionPipelineDiagram", () => {
  it("renders v2 stage names", () => {
    render(<ExtensionPipelineDiagram />);
    for (const label of [
      "Scope",
      "Fetch",
      "Storyteller",
      "Story editor",
      "Subject miner",
      "Researcher",
      "Curiosity writer",
      "Citation binder",
      "Judge",
    ]) {
      const matches = screen.getAllByText(new RegExp(label, "i"));
      expect(matches.length).toBeGreaterThanOrEqual(1);
    }
  });

  it("does not render v1 deepagents stage names", () => {
    const { container } = render(<ExtensionPipelineDiagram />);
    const html = container.innerHTML;
    expect(html).not.toMatch(/\banalyst\b/i);
    expect(html).not.toMatch(/\baugmentor\b/i);
    expect(html).not.toMatch(/\bpolish\b/i);
  });

  it("marks the two pure-code stages", () => {
    const { container } = render(<ExtensionPipelineDiagram />);
    const html = container.innerHTML;
    // Both researcher and citation_binder descs include "PURE CODE"
    const pureCodeCount = (html.match(/PURE CODE/g) ?? []).length;
    expect(pureCodeCount).toBeGreaterThanOrEqual(2);
  });

  it("renders StoryDigest as the output label", () => {
    render(<ExtensionPipelineDiagram />);
    expect(screen.getByText("StoryDigest")).toBeTruthy();
  });
});
