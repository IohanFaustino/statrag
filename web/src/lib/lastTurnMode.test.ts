import { describe, it, expect } from "vitest";
import { lastTurnMode } from "./lastTurnMode";
import type { Message } from "../types";

const asst = (mode: string): Message =>
  ({ role: "assistant", id: "a", time: "", timestamp: "", mode, model: "", books: [],
     sourceCount: 0, latencyMs: 0, blocks: [], status: "complete" } as Message);
const user = (): Message =>
  ({ role: "user", id: "u", time: "", timestamp: "", text: "x" } as Message);

describe("lastTurnMode", () => {
  it("returns the most recent assistant message's mode", () => {
    expect(lastTurnMode([user(), asst("tutor"), user(), asst("facilitate")], "tutor"))
      .toBe("facilitate");
  });
  it("falls back when there is no assistant message", () => {
    expect(lastTurnMode([user()], "resume")).toBe("resume");
  });
});
