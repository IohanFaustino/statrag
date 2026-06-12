// @vitest-environment jsdom
import { render, screen, fireEvent, act } from "@testing-library/react";
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

  it("renders the seed brief + citation chip from a CRLF-framed SSE response", async () => {
    const sse =
      "event: concept_seed\r\n" +
      'data: {"type":"concept_seed","term":"X","brief":"A grounded brief about X.","citations":[{"kind":"wikipedia","label":"Wikipedia: X","url":"https://en.wikipedia.org/wiki/X"}]}\r\n\r\n' +
      "event: done\r\ndata: {\"type\":\"done\"}\r\n\r\n";
    const enc = new TextEncoder();
    let sent = false;
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      body: { getReader: () => ({ read: async () => (sent ? { done: true, value: undefined } : (sent = true, { done: false, value: enc.encode(sse) })) }) },
    })) as unknown as typeof fetch);

    render(<ConceptChat anchor={anchor} conversationId="abc" onClose={() => {}} />);
    expect(await screen.findByText(/A grounded brief about X/)).toBeInTheDocument();
    expect(screen.getByText(/Wikipedia: X/)).toBeInTheDocument();
  });

  it("renders math in the brief via KaTeX, not raw $ source", async () => {
    const sse =
      "event: concept_seed\r\n" +
      'data: {"type":"concept_seed","term":"X","brief":"The mean is $\\\\overline{X}_n$ here.","citations":[]}\r\n\r\n' +
      "event: done\r\ndata: {\"type\":\"done\"}\r\n\r\n";
    const enc = new TextEncoder();
    let sent = false;
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      body: { getReader: () => ({ read: async () => (sent ? { done: true, value: undefined } : (sent = true, { done: false, value: enc.encode(sse) })) }) },
    })) as unknown as typeof fetch);
    const { container } = render(<ConceptChat anchor={anchor} conversationId="abc" onClose={() => {}} />);
    await screen.findByText(/here\./);   // brief text present
    // Raw "$\overline" must NOT appear as visible text — MathText rendered it via KaTeX
    expect(screen.queryByText(/\$\\overline/)).toBeNull();
    // KaTeX rendered an element
    expect(container.querySelector(".katex")).toBeTruthy();
  });

  it("deepens with history on follow-up submit", async () => {
    await act(async () => {
      render(<ConceptChat anchor={anchor} conversationId="abc" onClose={() => {}} />);
    });
    const ta = screen.getByLabelText(/concept question input/i);
    await act(async () => {
      fireEvent.change(ta, { target: { value: "why does it converge?" } });
      fireEvent.keyDown(ta, { key: "Enter" });
    });
    const calls = (fetch as any).mock.calls;
    expect(calls.length).toBeGreaterThanOrEqual(2);
    const body = JSON.parse(calls[calls.length - 1][1].body);
    expect(Array.isArray(body.history)).toBe(true);
    expect(JSON.stringify(body.history)).toContain("why does it converge?");
  });
});
