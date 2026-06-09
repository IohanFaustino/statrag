import type { ModeMeta } from "../components/ModePicker";

// Canonical frontend mode list. Mirrors the backend ModeId Literal in
// src/services/chat/schemas/_core.py — the parity tests
// (web/src/lib/modeParity.test.ts + src/services/chat/tests/test_mode_parity.py)
// fail if these drift.
export const STATRAG_MODES: ModeMeta[] = [
  { id: "tutor", label: "Tutor", glyph: "T" },
  { id: "qa", label: "Q&A", glyph: "?" },
  { id: "facilitate", label: "Facilitate", glyph: "F" },
  { id: "resume", label: "Resume", glyph: "R" },
  { id: "extension", label: "Extension", glyph: "E" },
];
