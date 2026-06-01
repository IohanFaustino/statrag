// @vitest-environment jsdom
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ConceptModal from "./ConceptModal";
import type { ConceptAnchor } from "../types";

const anchor: ConceptAnchor = {
  id: "c1", term: "strong assumption of normality", kind: "concept",
  explanation: "Assumes the data are normally distributed.",
  provenance: { book_slug: "hansen", book_name: "P&S", authors_short: "Hansen",
    section: "7.2 ASSUMPTIONS", page_from: 172, page_to: 172, chunk_id: "x",
    same_author: true, fallback: false },
};

describe("ConceptModal", () => {
  it("shows term, explanation, provenance", () => {
    render(<ConceptModal anchor={anchor} onClose={() => {}} />);
    expect(screen.getByText(/strong assumption of normality/)).toBeInTheDocument();
    expect(screen.getByText(/normally distributed/)).toBeInTheDocument();
    expect(screen.getByText(/Hansen/)).toBeInTheDocument();
  });
  it("calls onClose on overlay click", () => {
    const onClose = vi.fn();
    render(<ConceptModal anchor={anchor} onClose={onClose} />);
    fireEvent.click(screen.getByTestId("concept-modal-overlay"));
    expect(onClose).toHaveBeenCalled();
  });
});
