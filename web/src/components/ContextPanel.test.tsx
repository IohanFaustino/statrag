// @vitest-environment jsdom
import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ContextPanel from "./ContextPanel";
import type { Source } from "../types";

function makeSource(overrides: Partial<Source> = {}): Source {
  return {
    rank: 1,
    book: "moss",
    chapter: "ch05",
    section: "5.2 CLT",
    title: "Central Limit Theorem",
    excerpt: "The CLT establishes convergence in distribution.",
    score: 0.85,
    chunkId: "abc123",
    embedding: "",
    chunk: "",
    highlights: [],
    ...overrides,
  };
}

const noop = () => {};

describe("ContextPanel — SourceCard defensive rendering", () => {
  it("renders without crash when source.book is an empty string", () => {
    const src = makeSource({ book: "" });
    expect(() =>
      render(
        <ContextPanel
          sources={[src]}
          figures={[]}
          collapsed={false}
          onToggle={noop}
          onSourceClick={noop}
        />
      )
    ).not.toThrow();
  });

  it("omits the book tag (no '?' placeholder) when source.book is empty", () => {
    const src = makeSource({ book: "" });
    const { container } = render(
      <ContextPanel
        sources={[src]}
        figures={[]}
        collapsed={false}
        onToggle={noop}
        onSourceClick={noop}
      />
    );
    // Empty book → render nothing rather than a broken-looking "?" tag.
    expect(container.querySelector(".book-tag")).toBeNull();
  });

  it("renders a normal source with a known book key without crash", () => {
    const src = makeSource({ book: "HANSEN", rank: 2, score: 0.92 });
    const { container } = render(
      <ContextPanel
        sources={[src]}
        figures={[]}
        collapsed={false}
        onToggle={noop}
        onSourceClick={noop}
      />
    );
    expect(container.querySelector(".source-card")).not.toBeNull();
    // HANSEN gets mapped to "Hansen" label.
    expect(container.querySelector(".book-tag")!.textContent).toContain("Hansen");
  });

  it("renders corpus source with wikipedia-keyed book slug without crash", () => {
    // Extension evidence with book="wikipedia" (the fallback for wiki evidence).
    const src = makeSource({ book: "wikipedia", chapter: "", section: "Law of large numbers" });
    expect(() =>
      render(
        <ContextPanel
          sources={[src]}
          figures={[]}
          collapsed={false}
          onToggle={noop}
          onSourceClick={noop}
        />
      )
    ).not.toThrow();
  });
});
