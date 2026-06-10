// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
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

// ─── New UX improvement tests ─────────────────────────────────────────────────

const SAMPLE_DIGEST = {
  book: "hansen-probability",
  chapter: "ch07",
  points: [
    {
      title: "Law of Large Numbers",
      curated_text: "Sample mean converges to $\\mu$ as $n \\to \\infty$.",
      footnotes: [
        {
          marker: "a",
          body: "Also proven in Ross §5.2 using $\\bar X_n \\to \\mu$ in probability.",
          source: "ross-probability §5.2 The Weak Law of Large Numbers",
          kind: "corpus" as const,
        },
        {
          marker: "b",
          body: "Wikipedia: The law of large numbers is a theorem that describes the result of repeating the same experiment many times.",
          source: "https://en.wikipedia.org/wiki/Law_of_large_numbers",
          kind: "wikipedia" as const,
        },
      ],
    },
  ],
  unfilled_gaps: [],
};

it("renders point title", () => {
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  expect(screen.getByText("Law of Large Numbers")).toBeInTheDocument();
});

it("renders footnote markers", () => {
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  expect(screen.getByText("a")).toBeInTheDocument();
  expect(screen.getByText("b")).toBeInTheDocument();
});

it("truncates long corpus source to 40 chars", () => {
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  // Full source is "ross-probability §5.2 The Weak Law of Large Numbers" (51 chars)
  const sourceEls = document.querySelectorAll(".extension-footnote__source");
  const corpusSource = Array.from(sourceEls).find(el =>
    el.textContent?.includes("ross")
  );
  expect(corpusSource?.textContent?.includes("…")).toBe(true);
});

it("renders Wikipedia footnote source as clickable link", () => {
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  const link = screen.getByRole("link", { name: /wikipedia/i });
  expect(link).toHaveAttribute("href", "https://en.wikipedia.org/wiki/Law_of_large_numbers");
  expect(link).toHaveAttribute("target", "_blank");
});

it("Download button shows loading state while fetching", async () => {
  globalThis.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
  render(<ExtensionDigestCard digest={SAMPLE_DIGEST} />);
  const btn = screen.getByRole("button", { name: /download/i });
  fireEvent.click(btn);
  await waitFor(() => expect(btn).toBeDisabled());
  vi.restoreAllMocks();
});

// ─── Math delimiter normalization (persisted digests predate backend fix) ─────

it("renders \\(...\\) inline math in point titles as KaTeX, not raw text", () => {
  const d = {
    ...SAMPLE_DIGEST,
    points: [{ ...SAMPLE_DIGEST.points[0], title: "Worst-case tail rate (why \\(\\delta^{-2}\\) shows up)" }],
  };
  const { container } = render(<ExtensionDigestCard digest={d} />);
  const title = container.querySelector(".extension-point__title")!;
  expect(title.textContent).not.toContain("\\(");
  expect(title.querySelector(".katex")).not.toBeNull();
});

it("renders \\[...\\] as display math", () => {
  const d = {
    ...SAMPLE_DIGEST,
    points: [{ ...SAMPLE_DIGEST.points[0], curated_text: "Bound: \\[\\mathbb{P}(|X|\\ge t)\\le t^{-2}\\] holds." }],
  };
  const { container } = render(<ExtensionDigestCard digest={d} />);
  expect(container.querySelector(".math-block")).not.toBeNull();
  expect(container.querySelector(".extension-point__body")!.textContent).not.toContain("\\[");
});

it("renders $-on-own-line display blocks (newlines inside single-$ pair) as display math", () => {
  const body = "Then\n\n$\n\\mathbb{E}[Z^2]=\\mathbb{E}[X^2]-\\mu^2=\\operatorname{Var}(X).\n$\n\nFor any $t>0$ the bound holds.";
  const d = {
    ...SAMPLE_DIGEST,
    points: [{ ...SAMPLE_DIGEST.points[0], footnotes: [{ marker: "2", body, source: "wiki", kind: "wikipedia" as const }] }],
  };
  const { container } = render(<ExtensionDigestCard digest={d} />);
  const fn = container.querySelector(".extension-footnote__body")!;
  expect(fn.textContent).not.toContain("\n$\n");
  expect(container.querySelector(".extension-footnote__body .math-block")).not.toBeNull();
});

it("renders unfilled gaps with \\(...\\) math normalized", () => {
  const d = { ...SAMPLE_DIGEST, unfilled_gaps: ["WLLN under only \\(\\mathbb{E}|X|<\\infty\\): missing proof"] };
  const { container } = render(<ExtensionDigestCard digest={d} />);
  const gaps = container.querySelector(".extension-card__gaps")!;
  expect(gaps.textContent).not.toContain("\\(");
});

// ─── T2: Markdown bold/italic + strip duplicate markers + [^n] refs ───────────

describe("renderMathText — bold/italic rendering", () => {
  it("does NOT italicize mid-word asterisks like x*y*z (literal asterisks kept)", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        curated_text: "x*y*z stays literal here.",
        footnotes: [],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const body = container.querySelector(".extension-point__body")!;
    // No <em> element should be produced
    expect(body.querySelector("em")).toBeNull();
    // The asterisks remain in the text content
    expect(body.textContent).toContain("x*y*z");
  });

  it("renders *word* as <em> when standalone (not mid-word)", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        curated_text: "Apply *Chebyshev* here.",
        footnotes: [],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const body = container.querySelector(".extension-point__body")!;
    expect(body.querySelector("em")).not.toBeNull();
    expect(body.textContent).not.toContain("*Chebyshev*");
  });

  it("renders **bold** as <strong> in curated_text, no literal **", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        curated_text: "Apply the **Markov inequality** to $Z^2$.",
        footnotes: [],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const body = container.querySelector(".extension-point__body")!;
    expect(body.querySelector("strong")).not.toBeNull();
    expect(body.textContent).not.toContain("**");
  });

  it("renders **bold** interleaved with inline math: both render", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        curated_text: "a **b** $x^2$ c",
        footnotes: [],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const body = container.querySelector(".extension-point__body")!;
    expect(body.querySelector("strong")).not.toBeNull();
    expect(body.querySelector(".katex")).not.toBeNull();
    expect(body.textContent).not.toContain("**");
  });

  it("renders **bold** in unfilled_gaps", () => {
    const d = {
      ...SAMPLE_DIGEST,
      unfilled_gaps: ["Proof via **Borel-Cantelli** lemma still missing."],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const gaps = container.querySelector(".extension-card__gaps")!;
    expect(gaps.querySelector("strong")).not.toBeNull();
    expect(gaps.textContent).not.toContain("**");
  });

  it("renders **bold** in footnote body", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        footnotes: [{
          marker: "1",
          body: "Now apply the **Markov inequality** to the nonneg r.v.",
          source: "ross §5.1",
          kind: "corpus" as const,
        }],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const fnBody = container.querySelector(".extension-footnote__body")!;
    expect(fnBody.querySelector("strong")).not.toBeNull();
    expect(fnBody.textContent).not.toContain("**");
  });
});

describe("stripLeadingMarker — duplicate marker at footnote body start", () => {
  it("strips leading '2. ' from footnote body when marker is '2'", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        footnotes: [{
          marker: "2",
          body: "2. **Chebyshev proof step** details. Let $Z:=X-\\mu$ …",
          source: "ross §5.3",
          kind: "corpus" as const,
        }],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const fnBody = container.querySelector(".extension-footnote__body")!;
    // textContent should not start with "2."
    expect(fnBody.textContent?.trimStart()).not.toMatch(/^2\./);
  });

  it("does NOT strip leading '2. ' when marker is '3' (different marker)", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        footnotes: [{
          marker: "3",
          body: "2. This starts with 2 but marker is 3.",
          source: "ross §5.3",
          kind: "corpus" as const,
        }],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const fnBody = container.querySelector(".extension-footnote__body")!;
    expect(fnBody.textContent?.trimStart()).toMatch(/^2\./);
  });

  it("strips leading marker with dot then space (e.g. '7.4.1. ' when marker is '7.4.1')", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        footnotes: [{
          marker: "7.4.1",
          body: "7.4.1. Full proof of Chebyshev.",
          source: "ross §5.3",
          kind: "corpus" as const,
        }],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const fnBody = container.querySelector(".extension-footnote__body")!;
    expect(fnBody.textContent?.trimStart()).not.toMatch(/^7\.4\.1/);
  });

  it("strips leading marker with paren (e.g. '2) ' when marker is '2')", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        footnotes: [{
          marker: "2",
          body: "2) Another form of the footnote start.",
          source: "wiki",
          kind: "wikipedia" as const,
        }],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const fnBody = container.querySelector(".extension-footnote__body")!;
    expect(fnBody.textContent?.trimStart()).not.toMatch(/^2\)/);
  });
});

describe("[^n] footnote reference stripping", () => {
  it("removes [^3] from curated_text rendered output", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        curated_text: "This follows from Markov[^3] as shown above.",
        footnotes: [],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const body = container.querySelector(".extension-point__body")!;
    expect(body.textContent).not.toContain("[^");
  });

  it("removes [^12] from unfilled_gaps rendered output", () => {
    const d = {
      ...SAMPLE_DIGEST,
      unfilled_gaps: ["Proof of CLT[^12] still missing."],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const gaps = container.querySelector(".extension-card__gaps")!;
    expect(gaps.textContent).not.toContain("[^");
  });

  it("removes [^n] from footnote body rendered output", () => {
    const d = {
      ...SAMPLE_DIGEST,
      points: [{
        ...SAMPLE_DIGEST.points[0],
        footnotes: [{
          marker: "1",
          body: "This uses Chebyshev[^1] as cited above.",
          source: "ross §5.1",
          kind: "corpus" as const,
        }],
      }],
    };
    const { container } = render(<ExtensionDigestCard digest={d} />);
    const fnBody = container.querySelector(".extension-footnote__body")!;
    expect(fnBody.textContent).not.toContain("[^");
  });
});
