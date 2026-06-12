// @vitest-environment jsdom
// web/src/components/FacilitateStoryCard.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import FacilitateStoryCard from "./FacilitateStoryCard";
import type { FacilitateStory } from "../types";

const story: FacilitateStory = {
  mode: "facilitate_story",
  scope: { book_slug: "hansen", chapter_id: "ch07", section_id: "7.4",
           requested_subtopics: [], resolution: [] },
  hook: "Why averages stabilise.",
  movements: [
    { prose: "The [[c1]] is the engine here.", formal: null },
    { prose: "", formal: { kind: "theorem", statement: "$$\\bar X_n \\to \\mu$$",
                           explanation: "Elements: the mean. Intuition: it converges." } },
  ],
  takeaway: "You can now justify averaging.",
  concepts: [{ id: "c1", term: "law of large numbers", kind: "theorem",
               explanation: "converges", provenance: { book_slug: "hansen", book_name: "Probability",
               authors_short: "Hansen", section: "7.4", page_from: 120, page_to: 122,
               chunk_id: "x", same_author: true, fallback: false } }],
  citations: [{ kind: "wikipedia", label: "Wikipedia: LLN", url: "https://en.wikipedia.org/wiki/LLN" }],
  math_blocks: [], grounding: { ok: true, unsupported: [], confidence: 1 },
};

describe("FacilitateStoryCard", () => {
  it("renders hook, takeaway, and a formal statement block with kind badge", () => {
    render(<FacilitateStoryCard story={story} onConcept={() => {}} />);
    expect(screen.getByText(/Why averages stabilise/)).toBeInTheDocument();
    expect(screen.getByText(/You can now justify/)).toBeInTheDocument();
    expect(screen.getByText(/theorem/i)).toBeInTheDocument();
    expect(document.querySelector(".math-block, .katex")).toBeTruthy();
  });

  it("fires onConcept when a concept pill is clicked", () => {
    const onConcept = vi.fn();
    render(<FacilitateStoryCard story={story} onConcept={onConcept} />);
    fireEvent.click(screen.getByRole("button", { name: /law of large numbers/i }));
    expect(onConcept).toHaveBeenCalledWith(expect.objectContaining({ id: "c1" }));
  });

  it("renders a wikipedia citation chip", () => {
    render(<FacilitateStoryCard story={story} onConcept={() => {}} />);
    expect(screen.getByText(/Wikipedia: LLN/)).toBeInTheDocument();
  });

  it("shows the grounding warning when grounding.ok is false", () => {
    const ungrounded = { ...story, grounding: { ok: false, unsupported: ["x"], confidence: 0.4 } };
    render(<FacilitateStoryCard story={ungrounded} onConcept={() => {}} />);
    expect(screen.getByText(/not be fully grounded/i)).toBeInTheDocument();
  });
});
