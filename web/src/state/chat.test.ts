import { describe, it, expect } from "vitest";
import { storeReducer, initialStore, DRAFT_KEY } from "./chat";
import type { Action } from "./chat";
import type { ChatEvent } from "../types";

// Helpers ────────────────────────────────────────────────────────────────────

function send(convId: string): Action {
  return {
    type: "SLICE",
    convId,
    action: { type: "USER_SENT", text: "q", userId: "u1", assistantId: "a1", time: "12:00" },
  };
}

function event(convId: string, ev: ChatEvent): Action {
  return { type: "SLICE", convId, action: { type: "EVENT", ev } };
}

function run(actions: Action[]) {
  return actions.reduce(storeReducer, initialStore);
}

// Tests ────────────────────────────────────────────────────────────────────

describe("storeReducer (§13 multi-conversation)", () => {
  it("routes events to the matching conversation slice", () => {
    const s = run([
      send("A"),
      send("B"),
      event("A", { type: "token", text: "alpha", seq: 1 }),
      event("B", { type: "token", text: "beta", seq: 1 }),
    ]);
    const a = s.byConv["A"].messages.at(-1) as any;
    const b = s.byConv["B"].messages.at(-1) as any;
    expect(a.blocks[0].text).toBe("alpha");
    expect(b.blocks[0].text).toBe("beta");
  });

  it("tracks lastSeq as the max applied seq", () => {
    const s = run([
      send("A"),
      event("A", { type: "token", text: "x", seq: 1 }),
      event("A", { type: "token", text: "y", seq: 2 }),
    ]);
    expect(s.byConv["A"].lastSeq).toBe(2);
  });

  it("keeps a streaming slice intact when switching away and back", () => {
    let s = run([send("A"), event("A", { type: "token", text: "partial", seq: 1 })]);
    expect(s.byConv["A"].status).toBe("streaming");
    // Switch to B and stream there; A must be untouched.
    s = storeReducer(s, { type: "SET_ACTIVE", id: "B" });
    s = storeReducer(s, send("B"));
    s = storeReducer(s, event("B", { type: "token", text: "bbb", seq: 1 }));
    // Switch back to A.
    s = storeReducer(s, { type: "SET_ACTIVE", id: "A" });
    expect(s.active).toBe("A");
    const a = s.byConv["A"].messages.at(-1) as any;
    expect(a.blocks[0].text).toBe("partial");
    expect(s.byConv["A"].status).toBe("streaming");
  });

  it("RESET_DRAFT clears the draft but leaves other runs alive", () => {
    let s = run([send("A"), event("A", { type: "token", text: "live", seq: 1 })]);
    s = storeReducer(s, { type: "RESET_DRAFT" });
    expect(s.active).toBe(DRAFT_KEY);
    expect(s.byConv[DRAFT_KEY].messages).toHaveLength(0);
    expect(s.byConv["A"].status).toBe("streaming"); // untouched
  });

  it("BEGIN_RESUME appends an assistant placeholder for replay", () => {
    let s = storeReducer(initialStore, {
      type: "SLICE",
      convId: "A",
      action: { type: "LOAD_CONVERSATION", id: "A", messages: [
        { role: "user", id: "u", time: "12:00", timestamp: "t", text: "q" },
      ] },
    });
    s = storeReducer(s, {
      type: "SLICE",
      convId: "A",
      action: { type: "BEGIN_RESUME", assistantId: "a9", time: "12:01" },
    });
    const msgs = s.byConv["A"].messages;
    expect(msgs).toHaveLength(2);
    expect(msgs[1].role).toBe("assistant");
    expect(s.byConv["A"].status).toBe("streaming");
    // A replayed token lands on the placeholder.
    s = storeReducer(s, event("A", { type: "token", text: "replayed", seq: 1 }));
    const a = s.byConv["A"].messages.at(-1) as any;
    expect(a.blocks[0].text).toBe("replayed");
  });

  it("done idles the slice (drops from streamingIds) without affecting others", () => {
    let s = run([send("A"), send("B"), event("A", { type: "token", text: "x", seq: 1 })]);
    s = storeReducer(s, event("A", { type: "done", seq: 2 }));
    expect(s.byConv["A"].status).toBe("idle"); // no longer streaming
    expect((s.byConv["A"].messages.at(-1) as any).status).toBe("complete");
    expect(s.byConv["B"].status).toBe("streaming"); // untouched
  });
});
