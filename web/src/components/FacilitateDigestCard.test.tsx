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

describe("FacilitateDigestCard", () => {
  it("renders key points and a clickable concept anchor that opens a modal", () => {
    render(<FacilitateDigestCard digest={digest} />);
    expect(screen.getByText(/Sample means converge/)).toBeInTheDocument();
    const anchor = screen.getByRole("button", { name: /strong assumption of normality/ });
    fireEvent.click(anchor);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Assumes normal data/)).toBeInTheDocument();
  });
});
