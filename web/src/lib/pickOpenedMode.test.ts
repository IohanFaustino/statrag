import { describe, it, expect } from "vitest";
import { pickOpenedMode } from "./pickOpenedMode";

const MODES = ["tutor", "qa", "facilitate", "resume"];

describe("pickOpenedMode", () => {
  it("returns the conversation's mode when it is a known mode", () => {
    // The bug: opening a tutor conversation while the global picker had drifted
    // to 'facilitate' must restore the picker to the conversation's own mode.
    expect(pickOpenedMode("tutor", MODES, "facilitate")).toBe("tutor");
    expect(pickOpenedMode("resume", MODES, "tutor")).toBe("resume");
  });

  it("falls back to the current mode when conv mode is missing/unknown", () => {
    expect(pickOpenedMode(undefined, MODES, "tutor")).toBe("tutor");
    expect(pickOpenedMode("", MODES, "qa")).toBe("qa");
    expect(pickOpenedMode("bogus", MODES, "facilitate")).toBe("facilitate");
  });
});
