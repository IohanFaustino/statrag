import { describe, it, expect } from "vitest";
import { structuredToMarkdown } from "./exportStructured";
import type { Quiz, StudyPlan, DAG, TutorAnswer } from "../types";

describe("structuredToMarkdown — TutorAnswer", () => {
  it("renders prose then a numbered citations section", () => {
    const data: TutorAnswer = {
      text: "Variance measures spread.",
      citations: [
        { index: 1, book_name: "Econometrics", chapter: "Ch2", section: "§2.1", authors_short: "Hansen", year: 2022, quote: "var def" },
      ],
    };
    const md = structuredToMarkdown({ schema: "TutorAnswer", data });
    expect(md).toContain("Variance measures spread.");
    expect(md).toContain("Citations");
    expect(md).toContain("Hansen");
    expect(md).toContain("§2.1");
  });
});

describe("structuredToMarkdown — Quiz", () => {
  it("renders numbered questions with lettered options and answer", () => {
    const data: Quiz = {
      questions: [{
        stem: "What is the mean?",
        options: ["Sum", "Average", "Median", "Mode"],
        answer_idx: 1,
        rubric: "Average of values.",
        source: { book: "HANSEN", chapter: "Ch1", section: "§1.2" },
        difficulty: "easy",
      }],
    };
    const md = structuredToMarkdown({ schema: "Quiz", data });
    expect(md).toContain("1. What is the mean?");
    expect(md).toContain("- B. Average");
    expect(md).toContain("**Answer:** B");
    expect(md).toContain("easy");
  });
});

describe("structuredToMarkdown — StudyPlan", () => {
  it("renders a week table", () => {
    const data: StudyPlan = {
      goal: "Master regression",
      weeks: [{ week: 1, sections: [{ book: "HANSEN", chapter: "Ch3", section: "§3.1" }], hours_est: 5 }],
      coverage_gaps: ["nonlinear models"],
      replanned_from_version: 0,
    };
    const md = structuredToMarkdown({ schema: "StudyPlan", data });
    expect(md).toContain("Master regression");
    expect(md).toContain("| Week |");
    expect(md).toContain("HANSEN");
    expect(md).toContain("nonlinear models");
  });
});

describe("structuredToMarkdown — DAG", () => {
  it("renders nodes and edges", () => {
    const data: DAG = {
      nodes: [{ id: "a", label: "Mean", source: null }, { id: "b", label: "Variance", source: null }],
      edges: [{ from_id: "a", to_id: "b", weight: 0.9 }],
      cycles_broken: [],
    };
    const md = structuredToMarkdown({ schema: "DAG", data });
    expect(md).toContain("Mean");
    expect(md).toContain("Variance");
    expect(md).toContain("a → b");
  });
});

describe("structuredToMarkdown — unknown schema", () => {
  it("falls back to a json fence", () => {
    const md = structuredToMarkdown({ schema: "Mystery", data: { x: 1 } });
    expect(md).toContain("```json");
    expect(md).toContain("\"x\": 1");
  });
});
