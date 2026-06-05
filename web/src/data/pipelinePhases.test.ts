import { describe, it, expect } from "vitest";
import { phaseOf, PHASE_META, type Phase } from "./pipelinePhases";

describe("phaseOf", () => {
  it("maps tutor nodes to phases", () => {
    expect(phaseOf("input")).toBe("io");
    expect(phaseOf("output")).toBe("io");
    expect(phaseOf("expansion")).toBe("planning");
    expect(phaseOf("plan")).toBe("planning");
    expect(phaseOf("retrieval")).toBe("retrieval");
    expect(phaseOf("rerank")).toBe("retrieval");
    expect(phaseOf("diversity")).toBe("retrieval");
    expect(phaseOf("coverage")).toBe("retrieval");
    expect(phaseOf("drafting")).toBe("generation");
    expect(phaseOf("draft")).toBe("generation");
    expect(phaseOf("orchestrator")).toBe("generation");
    expect(phaseOf("worker1")).toBe("generation");
    expect(phaseOf("synthesizer")).toBe("generation");
    expect(phaseOf("image_judge")).toBe("vision");
    expect(phaseOf("formula_recovery")).toBe("vision");
    expect(phaseOf("vision_explain")).toBe("vision");
  });

  it("maps qa + chapter nodes to phases", () => {
    expect(phaseOf("scope")).toBe("planning");
    expect(phaseOf("clarify")).toBe("planning");
    expect(phaseOf("resolve")).toBe("planning");
    expect(phaseOf("parse")).toBe("planning");
    expect(phaseOf("map")).toBe("planning");
    expect(phaseOf("retrieve")).toBe("retrieval");
    expect(phaseOf("fetch")).toBe("retrieval");
    expect(phaseOf("generate")).toBe("generation");
    expect(phaseOf("teach")).toBe("generation");
    expect(phaseOf("stitch")).toBe("generation");
    expect(phaseOf("ground")).toBe("generation");
    expect(phaseOf("verify")).toBe("generation");
  });

  it("falls back to generation for unknown ids", () => {
    expect(phaseOf("totally-new-node")).toBe("generation");
  });

  it("has a chip label for every phase", () => {
    const phases: Phase[] = ["io", "planning", "retrieval", "generation", "vision"];
    for (const p of phases) expect(PHASE_META[p].label.length).toBeGreaterThan(0);
  });
});
