import { describe, it, expect } from "vitest";
import { normalizeMathDelimiters } from "./TutorView";

describe("normalizeMathDelimiters", () => {
  // ── Real LLM examples ────────────────────────────────────────────────────

  it("fixes real example 1: stray \\$( instead of \\(", () => {
    // Input: "...known distribution, \(p^*(D)\); this induces a distribution
    // over the estimand, \$(\hat{\theta}\), known as..."
    const input =
      "known distribution, \\(p^*(D)\\); this induces a distribution over the estimand, \\$(\\hat{\\theta}\\), known as";
    const result = normalizeMathDelimiters(input);
    // \$( should become \(
    expect(result).toContain("\\(\\hat{\\theta}\\)");
    // No stray \$( should remain
    expect(result).not.toContain("\\$(");
    // The first \(…\) span should be preserved intact
    expect(result).toContain("\\(p^*(D)\\)");
  });

  it("fixes real example 2: $…$ nested inside \\(…\\)", () => {
    // Input: "(sometimes denoted \($p(D\mid\theta)$\)) yields the sampling distribution"
    const input =
      "(sometimes denoted \\($p(D\\mid\\theta)$\\)) yields the sampling distribution";
    const result = normalizeMathDelimiters(input);
    // The inner $ delimiters should be stripped so we get \(p(D\mid\theta)\)
    expect(result).toContain("\\(p(D\\mid\\theta)\\)");
    // No dollar signs should remain inside the math span
    expect(result).not.toContain("\\($");
    expect(result).not.toContain("$\\)");
  });

  // ── Pass-through: clean inputs should be unchanged ───────────────────────

  it("leaves clean \\(…\\) untouched", () => {
    const input = "We have \\(\\hat{\\theta}\\) as the estimator.";
    expect(normalizeMathDelimiters(input)).toBe(input);
  });

  it("leaves clean $…$ untouched", () => {
    const input = "Let $x = 1$ and $y = 2$.";
    expect(normalizeMathDelimiters(input)).toBe(input);
  });

  it("leaves clean $$…$$ untouched (no LaTeX span open)", () => {
    const input = "Display math: $$E = mc^2$$";
    // Dollar signs outside a LaTeX span are not stripped
    expect(normalizeMathDelimiters(input)).toBe(input);
  });

  it("leaves plain text with no math untouched", () => {
    const input = "The quick brown fox jumps over the lazy dog.";
    expect(normalizeMathDelimiters(input)).toBe(input);
  });

  it("leaves clean \\[…\\] display math untouched", () => {
    const input = "Display: \\[\\int_0^1 f(x)\\,dx\\]";
    expect(normalizeMathDelimiters(input)).toBe(input);
  });

  // ── Additional edge cases ─────────────────────────────────────────────────

  it("fixes \\$) stray closer", () => {
    const input = "\\(\\hat{\\theta}\\$)";
    const result = normalizeMathDelimiters(input);
    // \$) → \)
    expect(result).toBe("\\(\\hat{\\theta}\\)");
    expect(result).not.toContain("\\$)");
  });

  it("fixes the real \\$( … \\)$ wrapper (stray $ on both delimiters)", () => {
    // Verbatim shape seen in stored answers: \$( \hat{\theta} \)$
    const input =
      "Let \\$( \\hat{\\theta} \\)$ be the estimator, and \\$( \\theta^* \\)$ be the estimand.";
    const result = normalizeMathDelimiters(input);
    expect(result).toBe(
      "Let \\( \\hat{\\theta} \\) be the estimator, and \\( \\theta^* \\) be the estimand.",
    );
    expect(result).not.toContain("$");
  });

  it("strips the trailing $ from a \\)$ closer", () => {
    const input = "value is \\$( \\text{Bias}^2 \\)$ here";
    expect(normalizeMathDelimiters(input)).toBe("value is \\( \\text{Bias}^2 \\) here");
  });

  it("handles multiple spans in the same string", () => {
    const input = "First \\($a$\\) and second \\($b$\\).";
    const result = normalizeMathDelimiters(input);
    expect(result).toBe("First \\(a\\) and second \\(b\\).");
  });

  it("strips multiple inner dollars in one span", () => {
    const input = "\\($x$ + $y$\\)";
    const result = normalizeMathDelimiters(input);
    expect(result).toBe("\\(x + y\\)");
  });

  it("does not strip $ outside a LaTeX span between two \\(…\\) spans", () => {
    const input = "\\(a\\) and $b$ and \\(c\\)";
    const result = normalizeMathDelimiters(input);
    // $b$ is outside any \(…\) span so must be preserved
    expect(result).toContain("$b$");
  });
});
