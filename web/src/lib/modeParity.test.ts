import { describe, it, expect } from "vitest";
import { STATRAG_MODES } from "../App";

// MUST stay in sync with CANONICAL_MODES in
// src/services/chat/tests/test_mode_parity.py — both fail if the sets drift.
const CANONICAL_MODES = ["tutor", "qa", "facilitate", "resume"];

describe("mode parity (frontend <-> backend)", () => {
  it("STATRAG_MODES ids equal the canonical backend mode set", () => {
    const ids = STATRAG_MODES.map((m) => m.id).sort();
    expect(ids).toEqual([...CANONICAL_MODES].sort());
  });
});
