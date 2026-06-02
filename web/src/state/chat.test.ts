import { describe, it, expect } from "vitest";
import { storeReducer, initialStore, DRAFT_KEY } from "./chat";
import type { Action } from "./chat";
import type { ChatEvent, ClarifyData, FacilitateDigest } from "../types";

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

  it("clarify event attaches a Clarify structuredOutput and completes the turn", () => {
    // Build state with an in-flight assistant message: USER_SENT creates the
    // placeholder, then a token arrives to confirm streaming — same pattern as
    // the "done" test above.
    let s = run([send("A"), event("A", { type: "token", text: "pick one", seq: 1 })]);

    const clarify: ChatEvent = {
      type: "clarify",
      reason: "book_unknown",
      message: "Pick one:",
      candidates: [{ slug: "islp", name: "ISL", authors_short: "James et al.", chapters: ["ch02"] }],
      chapter_guess: "ch07",
      sections_guess: ["7.2", "7.3"],
    };

    s = storeReducer(s, event("A", clarify));

    const last = s.byConv["A"].messages.at(-1) as any;
    expect(last.structuredOutput.schema).toBe("Clarify");
    expect((last.structuredOutput.data as ClarifyData).candidates[0].slug).toBe("islp");
    expect(last.status).toBe("complete");
    expect(s.byConv["A"].status).toBe("idle");
  });

  it("STOP marks the last assistant message stopped=true and idles the slice", () => {
    // Build a slice with a streaming assistant message via USER_SENT
    let s = run([send("A"), event("A", { type: "token", text: "partial", seq: 1 })]);
    // Sanity: slice is streaming
    expect(s.byConv["A"].status).toBe("streaming");

    s = storeReducer(s, { type: "SLICE", convId: "A", action: { type: "STOP" } });

    const last = s.byConv["A"].messages.at(-1) as any;
    expect(last.stopped).toBe(true);
    expect(last.status).toBe("complete");
    expect(s.byConv["A"].status).toBe("idle");
  });

  it("structured_output FacilitateDigest attaches schema and data to the last assistant message", () => {
    let s = run([send("A"), event("A", { type: "token", text: "loading", seq: 1 })]);

    const digest: FacilitateDigest = {
      mode: "facilitate",
      scope: {
        book_slug: "islp",
        chapter_id: "ch03",
        requested_subtopics: ["regression"],
        resolution: [],
      },
      intro: "",
      blocks: [
        {
          h2_path: "3.1 Simple Linear Regression",
          section_id: "islp-ch03-s1",
          key_points: ["k"],
          body: "b [[c1]]",
          concepts: [],
          page_from: 1,
          page_to: 1,
        },
      ],
      outro: "",
      math_blocks: [],
      grounding: { ok: true },
    };

    const ev: ChatEvent = { type: "structured_output", schema: "FacilitateDigest", data: digest };
    s = storeReducer(s, event("A", ev));

    const last = s.byConv["A"].messages.at(-1) as any;
    expect(last.structuredOutput.schema).toBe("FacilitateDigest");
  });
});
