// @vitest-environment jsdom
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ConceptChat from "./ConceptChat";
import type { ConceptAnchor } from "../types";

const anchor: ConceptAnchor = {
  id: "c1", term: "law of large numbers", kind: "theorem", explanation: "",
  provenance: { book_slug: "hansen", book_name: "Probability", authors_short: "Hansen",
    section: "7.4", page_from: 120, page_to: 122, chunk_id: "x", same_author: true, fallback: false },
};

describe("ConceptChat", () => {
  beforeEach(() => {
    // Minimal fetch stub: returns an empty SSE body so mount doesn't throw.
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      body: { getReader: () => ({ read: async () => ({ done: true, value: undefined }) }) },
    })) as unknown as typeof fetch);
  });

  it("renders the concept term as the panel title and a close button works", () => {
    const onClose = vi.fn();
    render(<ConceptChat anchor={anchor} conversationId="abc" onClose={onClose} />);
    expect(screen.getByText(/law of large numbers/i)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/close/i));
    expect(onClose).toHaveBeenCalled();
  });

  it("POSTs to /api/concept/explore with the concept term + provenance on mount", () => {
    render(<ConceptChat anchor={anchor} conversationId="abc" onClose={() => {}} />);
    expect(fetch).toHaveBeenCalledWith(
      "/api/concept/explore",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse((fetch as any).mock.calls[0][1].body);
    expect(body.term).toBe("law of large numbers");
    expect(body.book_slug).toBe("hansen");
    expect(body.section_id).toBe("7.4");
  });
});
