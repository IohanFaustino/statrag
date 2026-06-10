// @vitest-environment jsdom
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import StoryDigestCard from "./StoryDigestCard";
import type { StoryDigest } from "../types";

const digest: StoryDigest = {
  book: "hansen-probability", chapter: "ch07 · 7.4–7.5",
  takes: [
    { heading: "Chebyshev $\\delta^{-2}$", story: "The chapter **opens** with $\\mu$.",
      items: [{ subject: "Why $\\delta^{-2}$", body: "Because **worst-case**…",
                citations: [
                  { kind: "corpus", label: "Moss — Probability §6.5.2, pp. 142–144" },
                  { kind: "wikipedia", label: "Wikipedia: Chebyshev's inequality",
                    url: "https://en.wikipedia.org/wiki/X" }] }] },
    { heading: "WLLN", story: "Then…", items: [] },
  ],
  unfilled_subjects: ["history of LLN"],
};

describe("StoryDigestCard", () => {
  it("renders rail nodes, headings, justified story with KaTeX + markdown", () => {
    const { container } = render(<StoryDigestCard digest={digest} />);
    expect(container.querySelectorAll(".story-take").length).toBe(2);
    expect(container.querySelectorAll(".story-take__num").length).toBe(2);
    const story = container.querySelector(".story-take__story")!;
    expect(story.querySelector(".katex")).not.toBeNull();      // KaTeX in story
    expect(story.querySelector("strong")).not.toBeNull();      // markdown in story
  });

  it("curiosity box collapsed by default, expands on toggle, shows chips", () => {
    const { container } = render(<StoryDigestCard digest={digest} />);
    expect(container.querySelector(".curiosity-box__items")).toBeNull();
    fireEvent.click(screen.getByText(/Curiosity box \(1\)/));
    const items = container.querySelector(".curiosity-box__items")!;
    expect(items.querySelector(".katex")).not.toBeNull();      // KaTeX in box
    expect(items.querySelector("strong")).not.toBeNull();      // markdown in box
    const wiki = items.querySelector("a.citation-chip--wiki")!;
    expect(wiki).toHaveAttribute("href", "https://en.wikipedia.org/wiki/X");
    expect(wiki).toHaveAttribute("target", "_blank");
    expect(items.textContent).toContain("Moss — Probability §6.5.2");
  });

  it("expand-all / collapse-all toggles every box", () => {
    const { container } = render(<StoryDigestCard digest={digest} />);
    fireEvent.click(screen.getByRole("button", { name: /expand all/i }));
    expect(container.querySelectorAll(".curiosity-box__items").length).toBe(1); // take 2 has none
    fireEvent.click(screen.getByRole("button", { name: /collapse all/i }));
    expect(container.querySelectorAll(".curiosity-box__items").length).toBe(0);
  });

  it("no curiosity toggle when take has no items; unfilled subjects listed", () => {
    render(<StoryDigestCard digest={digest} />);
    expect(screen.getAllByText(/Curiosity box/).length).toBe(1);
    expect(screen.getByText(/history of LLN/)).toBeInTheDocument();
  });

  it("shows download control", () => {
    render(<StoryDigestCard digest={digest} />);
    expect(screen.getByRole("button", { name: /download/i })).toBeInTheDocument();
  });
});
