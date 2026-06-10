// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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

  it("curiosity box collapsed by default, expands on toggle, shows chips; aria-expanded flips", () => {
    const { container } = render(<StoryDigestCard digest={digest} />);
    expect(container.querySelector(".curiosity-box__items")).toBeNull();
    const toggleBtn = screen.getByText(/Curiosity box \(1\)/);
    expect(toggleBtn).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggleBtn);
    expect(toggleBtn).toHaveAttribute("aria-expanded", "true");
    const items = container.querySelector(".curiosity-box__items")!;
    expect(items.querySelector(".katex")).not.toBeNull();      // KaTeX in box
    expect(items.querySelector("strong")).not.toBeNull();      // markdown in box
    const wiki = items.querySelector("a.citation-chip--wiki")!;
    expect(wiki).toHaveAttribute("href", "https://en.wikipedia.org/wiki/X");
    expect(wiki).toHaveAttribute("target", "_blank");
    expect(items.textContent).toContain("Moss — Probability §6.5.2");
    fireEvent.click(toggleBtn);
    expect(toggleBtn).toHaveAttribute("aria-expanded", "false");
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

  describe("download error UX", () => {
    beforeEach(() => { vi.spyOn(globalThis, "fetch"); });
    afterEach(() => { vi.restoreAllMocks(); });

    it("shows alert with status when server returns !ok", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response);
      render(<StoryDigestCard digest={digest} />);
      expect(screen.queryByRole("alert")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: /download zip/i }));
      await waitFor(() =>
        expect(screen.getByRole("alert").textContent).toContain("Export failed (500)")
      );
    });

    it("shows network error alert when fetch rejects", async () => {
      vi.mocked(globalThis.fetch).mockRejectedValueOnce(new Error("Network error"));
      render(<StoryDigestCard digest={digest} />);
      fireEvent.click(screen.getByRole("button", { name: /download zip/i }));
      await waitFor(() =>
        expect(screen.getByRole("alert").textContent).toContain("Export failed — network error")
      );
    });

    it("clears previous error when download starts again", async () => {
      vi.mocked(globalThis.fetch)
        .mockResolvedValueOnce({ ok: false, status: 500 } as Response)
        .mockResolvedValueOnce({ ok: false, status: 503 } as Response);
      render(<StoryDigestCard digest={digest} />);
      fireEvent.click(screen.getByRole("button", { name: /download zip/i }));
      await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
      fireEvent.click(screen.getByRole("button", { name: /download zip/i }));
      // alert disappears momentarily (cleared at start) then reappears with new error
      await waitFor(() =>
        expect(screen.getByRole("alert").textContent).toContain("Export failed (503)")
      );
    });

    it("uses dynamic filename from digest book+chapter", async () => {
      // jsdom does not implement URL.createObjectURL; assign stubs directly
      URL.createObjectURL = vi.fn(() => "blob:fake");
      URL.revokeObjectURL = vi.fn();
      let capturedAnchor: HTMLAnchorElement | undefined;
      const createElementOrig = document.createElement.bind(document);
      const createElSpy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
        const el = createElementOrig(tag);
        if (tag === "a") {
          capturedAnchor = el as HTMLAnchorElement;
          // stub click+remove so jsdom's DOM invariants aren't triggered
          (el as HTMLAnchorElement).click = vi.fn();
          (el as HTMLAnchorElement).remove = vi.fn();
        }
        return el;
      });
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        blob: async () => new Blob(["zip"], { type: "application/zip" }),
      } as Response);
      render(<StoryDigestCard digest={digest} />);
      fireEvent.click(screen.getByRole("button", { name: /download zip/i }));
      await waitFor(() => expect(capturedAnchor).toBeDefined());
      await waitFor(() => expect(capturedAnchor!.click).toHaveBeenCalled());
      expect(capturedAnchor!.download).toBe(
        "hansen-probability-ch07 · 7.4–7.5-extended.zip"
      );
      createElSpy.mockRestore();
    });
  });
});
