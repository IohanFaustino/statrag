// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ExtensionDigestCard from "./ExtensionDigestCard";
import StructuredErrorBoundary from "./StructuredErrorBoundary";

const digest = {
  book: "hansen-probability", chapter: "ch07",
  points: [{ title: "LLN", curated_text: "The mean converges.",
    footnotes: [{ marker: "1", body: "x to mu", source: "ross §5.1", kind: "corpus" as const }] }],
  unfilled_gaps: [],
};

describe("ExtensionDigestCard", () => {
  it("renders points, titles, curated text and footnotes", () => {
    render(<ExtensionDigestCard digest={digest} />);
    expect(screen.getByText("LLN")).toBeInTheDocument();
    expect(screen.getByText(/mean converges/)).toBeInTheDocument();
    expect(screen.getByText(/ross §5.1/)).toBeInTheDocument();
  });

  it("shows a download control", () => {
    render(<ExtensionDigestCard digest={digest} />);
    expect(screen.getByRole("button", { name: /download/i })).toBeInTheDocument();
  });
});

describe("StructuredErrorBoundary", () => {
  it("StructuredErrorBoundary renders children normally", () => {
    const { getByText } = render(
      <StructuredErrorBoundary>
        <span>child content</span>
      </StructuredErrorBoundary>
    );
    expect(getByText("child content")).toBeInTheDocument();
  });
});
