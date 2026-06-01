// @vitest-environment jsdom
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import FacilitateDigestCard from "./FacilitateDigestCard";
import type { FacilitateDigest } from "../types";

const digest: FacilitateDigest = {
  mode: "facilitate",
  scope: { book_slug: "hansen", chapter_id: "ch07", requested_subtopics: [], resolution: [] } as any,
  intro: "", outro: "", math_blocks: [], grounding: { ok: true, confidence: 0.9 },
  blocks: [{
    h2_path: "7.1 INTRODUCTION", section_id: "s1", page_from: 176, page_to: 176,
    key_points: ["Sample means converge."],
    body: "We rely on the strong assumption of normality [[c1]].",
    concepts: [{ id: "c1", term: "strong assumption of normality", kind: "concept",
      explanation: "Assumes normal data.",
      provenance: { book_slug: "hansen", book_name: "P&S", authors_short: "Hansen",
        section: "7.2", page_from: 172, page_to: 172, chunk_id: "x",
        same_author: true, fallback: false } }],
  }],
};

const mathDigest: FacilitateDigest = {
  mode: "facilitate",
  scope: { book_slug: "hansen", chapter_id: "ch07", requested_subtopics: [], resolution: [] } as any,
  intro: "", outro: "", math_blocks: [], grounding: { ok: true, confidence: 0.9 },
  blocks: [{
    h2_path: "7.2 BOUNDS", section_id: "s2", page_from: 180, page_to: 180,
    key_points: [],
    body: "Bound $\\mathbb{P}(X)$ here [[c1]].",
    concepts: [{ id: "c1", term: "Markov bound", kind: "concept",
      explanation: "A bound on probability.",
      provenance: { book_slug: "hansen", book_name: "P&S", authors_short: "Hansen",
        section: "7.3", page_from: 173, page_to: 173, chunk_id: "y",
        same_author: true, fallback: false } }],
  }],
};

describe("FacilitateDigestCard", () => {
  it("renders key points and a clickable concept anchor that opens a modal", () => {
    render(<FacilitateDigestCard digest={digest} />);
    expect(screen.getByText(/Sample means converge/)).toBeInTheDocument();
    const anchor = screen.getByRole("button", { name: /strong assumption of normality/ });
    fireEvent.click(anchor);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Assumes normal data/)).toBeInTheDocument();
  });

  it("renders inline math in body text and still shows the concept anchor button", () => {
    const { container } = render(<FacilitateDigestCard digest={mathDigest} />);
    // The raw LaTeX literal must NOT appear as plain text — KaTeX transformed it.
    expect(screen.queryByText(/\$\\mathbb\{P\}\(X\)\$/)).toBeNull();
    // KaTeX renders into the DOM with a class containing "katex".
    expect(container.querySelector(".katex")).not.toBeNull();
    // The concept anchor button must still be present.
    expect(screen.getByRole("button", { name: /Markov bound/ })).toBeInTheDocument();
  });
});
