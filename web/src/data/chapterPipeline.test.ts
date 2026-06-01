import { describe, it, expect } from "vitest";
import { CHAPTER_PIPELINE } from "./chapterPipeline";

describe("CHAPTER_PIPELINE", () => {
  it("has the main pipeline nodes in order ending at ground", () => {
    const ids = CHAPTER_PIPELINE.nodes.map((n) => n.id);
    expect(ids).toContain("parse");
    expect(ids).toContain("fetch");
    expect(ids).toContain("resolve");
    expect(ids).toContain("map");
    expect(ids).toContain("stitch");
    expect(ids).toContain("ground");
    // main chain order
    const mainIds = ids.filter((id) => id !== "clarify");
    expect(mainIds).toEqual(["parse", "fetch", "resolve", "map", "stitch", "ground"]);
  });

  it("edges include the main chain through every node", () => {
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "parse", to: "fetch" });
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "fetch", to: "resolve" });
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "resolve", to: "map" });
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "map", to: "stitch" });
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "stitch", to: "ground" });
  });

  it("parse node is relabeled to parse + resolve scope", () => {
    const parse = CHAPTER_PIPELINE.nodes.find((n) => n.id === "parse")!;
    expect(parse.label.toLowerCase()).toContain("resolve");
  });

  it("has a clarify node reachable from parse", () => {
    const clarify = CHAPTER_PIPELINE.nodes.find((n) => n.id === "clarify");
    expect(clarify).toBeTruthy();
    expect(CHAPTER_PIPELINE.edges).toContainEqual({ from: "parse", to: "clarify" });
  });
});
