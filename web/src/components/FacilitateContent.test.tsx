// @vitest-environment jsdom
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import FacilitateContent, { normalizeMath } from "./FacilitateContent";
import type { ConceptAnchor } from "../types";

// ─── normalizeMath ──────────────────────────────────────────────────────────

describe("normalizeMath", () => {
  it("converts \\(a\\) to $a$", () => {
    expect(normalizeMath("\\(a\\)")).toBe("$a$");
  });

  it("converts \\[b\\] to $$b$$", () => {
    expect(normalizeMath("\\[b\\]")).toBe("$$b$$");
  });

  it("leaves existing $...$ untouched", () => {
    expect(normalizeMath("$x^2$")).toBe("$x^2$");
  });

  it("converts mixed delimiters in a longer string", () => {
    const input = "See \\(x^2\\) and \\[E=mc^2\\] for details.";
    const result = normalizeMath(input);
    expect(result).toBe("See $x^2$ and $$E=mc^2$$ for details.");
  });
});

// ─── Helper fixture ─────────────────────────────────────────────────────────

const makeConcept = (id: string, term: string): ConceptAnchor => ({
  id,
  term,
  kind: "concept",
  explanation: `Explanation for ${term}`,
  provenance: {
    book_slug: "test", book_name: "Test Book", authors_short: "Author",
    section: "1.1", page_from: 1, page_to: 1, chunk_id: "c1",
    same_author: true, fallback: false,
  },
});

// ─── Bullet list rendering ──────────────────────────────────────────────────

describe("FacilitateContent — bullet list", () => {
  it("renders two <li> elements for a two-item bullet list", () => {
    const { container } = render(
      <FacilitateContent text={"- one\n- two"} />,
    );
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain("one");
    expect(items[1].textContent).toContain("two");
  });
});

// ─── Paragraph + list are separate blocks ──────────────────────────────────

describe("FacilitateContent — block separation", () => {
  it("renders a paragraph and a list as separate blocks (not one run)", () => {
    const { container } = render(
      <FacilitateContent text={"Some intro text.\n\n- item one\n- item two"} />,
    );
    expect(container.querySelector("p")).not.toBeNull();
    expect(container.querySelector("ul")).not.toBeNull();
    // The list items should be in a <ul>, not inside the <p>
    const p = container.querySelector("p")!;
    expect(p.querySelectorAll("li")).toHaveLength(0);
    const ul = container.querySelector("ul")!;
    expect(ul.querySelectorAll("li")).toHaveLength(2);
  });
});

// ─── [[cN]] concept anchor ──────────────────────────────────────────────────

describe("FacilitateContent — concept anchors", () => {
  it("renders a button for a matched concept anchor that calls onPick on click", () => {
    const c1 = makeConcept("c1", "normality");
    const onPick = vi.fn();
    render(
      <FacilitateContent
        text="Relies on [[c1]] assumption."
        concepts={[c1]}
        onPick={onPick}
      />,
    );
    const btn = screen.getByRole("button", { name: "normality" });
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onPick).toHaveBeenCalledWith(c1);
  });

  it("renders unmatched [[c9]] as raw text without crashing", () => {
    render(
      <FacilitateContent
        text="Contains [[c9]] unknown anchor."
        concepts={[]}
      />,
    );
    // No button should exist
    expect(screen.queryByRole("button")).toBeNull();
    // The raw marker text should be present (no crash)
    expect(screen.getByText(/\[\[c9\]\]/)).toBeInTheDocument();
  });
});

// ─── Math rendering ─────────────────────────────────────────────────────────

describe("FacilitateContent — math rendering", () => {
  it("renders $x^2$ via KaTeX (raw tex literal absent, .katex present)", () => {
    const { container } = render(
      <FacilitateContent text="The formula $x^2$ is quadratic." />,
    );
    // The raw dollar-delimited text should NOT appear verbatim
    expect(screen.queryByText(/\$x\^2\$/)).toBeNull();
    // KaTeX renders a .katex element
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("renders \\(y\\) (normalized to $y$) via KaTeX", () => {
    const { container } = render(
      <FacilitateContent text={"Value \\(y\\) is shown."} />,
    );
    // After normalization \(y\) → $y$, KaTeX should render it
    expect(container.querySelector(".katex")).not.toBeNull();
    // Raw escaped-paren literal should not be visible as text
    expect(screen.queryByText(/\\\(y\\\)/)).toBeNull();
  });
});
