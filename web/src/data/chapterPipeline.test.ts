import { describe, it, expect } from "vitest";
import { CHAPTER_PIPELINE } from "./chapterPipeline";

describe("CHAPTER_PIPELINE", () => {
  it("has six ordered nodes ending at ground", () => {
    const ids = CHAPTER_PIPELINE.nodes.map((n) => n.id);
    expect(ids).toEqual(["parse", "fetch", "resolve", "map", "stitch", "ground"]);
  });

  it("edges form a single chain through every node", () => {
    expect(CHAPTER_PIPELINE.edges).toEqual([
      { from: "parse", to: "fetch" },
      { from: "fetch", to: "resolve" },
      { from: "resolve", to: "map" },
      { from: "map", to: "stitch" },
      { from: "stitch", to: "ground" },
    ]);
  });
});
