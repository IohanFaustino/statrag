import { describe, expect, it } from "vitest";
import { stripTrailingMathPunct } from "./Math";

describe("stripTrailingMathPunct", () => {
  it("removes a trailing period", () => {
    expect(stripTrailingMathPunct("\\mathrm{MSE}(\\hat\\theta) = \\mathbb{E}[(\\hat\\theta - \\theta)^2]."))
      .toBe("\\mathrm{MSE}(\\hat\\theta) = \\mathbb{E}[(\\hat\\theta - \\theta)^2]");
  });

  it("removes trailing comma, semicolon, colon", () => {
    expect(stripTrailingMathPunct("E = mc^2,")).toBe("E = mc^2");
    expect(stripTrailingMathPunct("E = mc^2;")).toBe("E = mc^2");
    expect(stripTrailingMathPunct("E = mc^2:")).toBe("E = mc^2");
  });

  it("removes whitespace + punctuation", () => {
    expect(stripTrailingMathPunct("E = mc^2 .")).toBe("E = mc^2");
    expect(stripTrailingMathPunct("E = mc^2  ,  ")).toBe("E = mc^2");
  });

  it("removes runs of trailing punctuation", () => {
    expect(stripTrailingMathPunct("E = mc^2...")).toBe("E = mc^2");
    expect(stripTrailingMathPunct("E = mc^2,.")).toBe("E = mc^2");
  });

  it("leaves clean tex untouched", () => {
    expect(stripTrailingMathPunct("E = mc^2")).toBe("E = mc^2");
    expect(stripTrailingMathPunct("\\frac{a}{b}")).toBe("\\frac{a}{b}");
  });

  it("does not strip mid-string punctuation", () => {
    expect(stripTrailingMathPunct("a, b, c")).toBe("a, b, c");
    expect(stripTrailingMathPunct("f(x) = x^2 + 1")).toBe("f(x) = x^2 + 1");
  });

  it("does not strip closing braces or operators", () => {
    expect(stripTrailingMathPunct("\\mathbb{E}[X]")).toBe("\\mathbb{E}[X]");
    expect(stripTrailingMathPunct("x^2")).toBe("x^2");
  });
});
