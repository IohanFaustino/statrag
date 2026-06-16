// @vitest-environment jsdom
import { render } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
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

  it("labels a wikipedia augment source with a 🌐 Wikipedia tag", () => {
    const src = makeSource({
      book: "wikipedia", chapter: "", section: "Bias of an estimator",
      url: "https://en.wikipedia.org/wiki/Bias_of_an_estimator",
    });
    const { container } = render(
      <ContextPanel
        sources={[src]}
        figures={[]}
        collapsed={false}
        onToggle={noop}
        onSourceClick={noop}
      />
    );
    const tag = container.querySelector(".book-tag--wikipedia");
    expect(tag).not.toBeNull();
    expect(tag!.textContent).toContain("Wikipedia");
  });
});

describe("ContextPanel — unique key prop (undefined rank)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("emits no 'unique key prop' warning when sources have undefined rank", () => {
    // Extension/wiki sources carry rank=undefined at runtime (type says number
    // but the backend omits the field). The key was key={s.rank} = key={undefined}
    // which is equivalent to a missing key — React fires a console.error warning.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    const srcA = makeSource({ rank: undefined as unknown as number, book: "wikipedia", section: "CLT" });
    const srcB = makeSource({ rank: undefined as unknown as number, book: "wikipedia", section: "LLN" });

    render(
      <ContextPanel
        sources={[srcA, srcB]}
        figures={[]}
        collapsed={false}
        onToggle={noop}
        onSourceClick={noop}
      />
    );

    const uniqueKeyWarning = spy.mock.calls.some((args) =>
      args.some((a) => typeof a === "string" && /unique.*key|key.*unique/i.test(a))
    );
    expect(uniqueKeyWarning).toBe(false);
  });
});
