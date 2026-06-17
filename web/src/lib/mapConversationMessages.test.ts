import { describe, it, expect } from "vitest";
import {
  mapConversationMessages,
  parseConvMode,
} from "./mapConversationMessages";
import type { RawConversationResponse } from "./mapConversationMessages";
import type { AssistantMessage } from "../types";

// ---------------------------------------------------------------------------
// parseConvMode
// ---------------------------------------------------------------------------

describe("parseConvMode", () => {
  it("returns 'tutor' for undefined", () => {
    expect(parseConvMode(undefined)).toBe("tutor");
  });

  it("returns 'tutor' for an unknown mode string", () => {
    expect(parseConvMode("deep_dive")).toBe("tutor");
  });

  it("returns 'tutor' for a number", () => {
    expect(parseConvMode(42)).toBe("tutor");
  });

  it.each(["tutor", "qa", "facilitate", "resume"] as const)(
    "accepts valid mode '%s' as-is",
    (mode) => {
      expect(parseConvMode(mode)).toBe(mode);
    },
  );
});

// ---------------------------------------------------------------------------
// mapConversationMessages — mode propagation (the regression guard)
// ---------------------------------------------------------------------------

const BASE_MSG = {
  id: "m1",
  role: "assistant",
  content: { text: "Some digest body." },
  timestamp: "2024-01-01T12:00:00Z",
};

describe("mapConversationMessages — assistant message mode", () => {
  it("stamps 'facilitate' mode on assistant messages when conversation mode is facilitate", () => {
    const data: RawConversationResponse = {
      id: "conv1",
      mode: "facilitate",
      messages: [BASE_MSG],
    };
    const msgs = mapConversationMessages(data);
    expect(msgs).toHaveLength(1);
    const msg = msgs[0] as any;
    expect(msg.role).toBe("assistant");
    expect(msg.mode).toBe("facilitate");
  });

  it("stamps 'resume' mode on assistant messages when conversation mode is resume", () => {
    const data: RawConversationResponse = {
      id: "conv2",
      mode: "resume",
      messages: [BASE_MSG],
    };
    const msgs = mapConversationMessages(data);
    const msg = msgs[0] as any;
    expect(msg.mode).toBe("resume");
  });

  it("stamps 'qa' mode on assistant messages when conversation mode is qa", () => {
    const data: RawConversationResponse = {
      id: "conv3",
      mode: "qa",
      messages: [BASE_MSG],
    };
    const msgs = mapConversationMessages(data);
    const msg = msgs[0] as any;
    expect(msg.mode).toBe("qa");
  });

  it("falls back to 'tutor' when mode is absent", () => {
    const data: RawConversationResponse = {
      id: "conv4",
      messages: [BASE_MSG],
    };
    const msgs = mapConversationMessages(data);
    const msg = msgs[0] as any;
    expect(msg.mode).toBe("tutor");
  });

  it("falls back to 'tutor' for an unknown mode string", () => {
    const data: RawConversationResponse = {
      id: "conv5",
      mode: "unsupported_future_mode",
      messages: [BASE_MSG],
    };
    const msgs = mapConversationMessages(data);
    const msg = msgs[0] as any;
    expect(msg.mode).toBe("tutor");
  });

  it("all assistant messages in a multi-turn facilitate conversation get the correct mode", () => {
    const data: RawConversationResponse = {
      id: "conv6",
      mode: "facilitate",
      messages: [
        { id: "u1", role: "user", content: "Explain chapter 3", timestamp: "2024-01-01T12:00:00Z" },
        { id: "a1", role: "assistant", content: { text: "Sure, chapter 3 covers…" }, timestamp: "2024-01-01T12:01:00Z" },
        { id: "u2", role: "user", content: "Can you give an example?", timestamp: "2024-01-01T12:02:00Z" },
        { id: "a2", role: "assistant", content: { text: "Here is an example…" }, timestamp: "2024-01-01T12:03:00Z" },
      ],
    };
    const msgs = mapConversationMessages(data);
    expect(msgs).toHaveLength(4);
    const assistants = msgs.filter((m) => m.role === "assistant") as any[];
    expect(assistants).toHaveLength(2);
    for (const a of assistants) {
      expect(a.mode).toBe("facilitate");
    }
  });
});

// ---------------------------------------------------------------------------
// mapConversationMessages — user messages are unaffected
// ---------------------------------------------------------------------------

describe("mapConversationMessages — user messages", () => {
  it("user messages have role 'user' and carry text", () => {
    const data: RawConversationResponse = {
      id: "conv7",
      mode: "facilitate",
      messages: [
        { id: "u1", role: "user", content: "Hello", timestamp: "2024-01-01T10:00:00Z" },
      ],
    };
    const msgs = mapConversationMessages(data);
    const m = msgs[0] as any;
    expect(m.role).toBe("user");
    expect(m.text).toBe("Hello");
    // User messages have no mode field
    expect("mode" in m).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// mapConversationMessages — structured content still works
// ---------------------------------------------------------------------------

describe("mapConversationMessages — structured content", () => {
  it("maps metadata.stopped onto the assistant message", () => {
    const data: RawConversationResponse = {
      id: "conv-stopped",
      mode: "tutor",
      messages: [
        {
          id: "a1",
          role: "assistant",
          content: { text: "Partial answer." },
          timestamp: "2024-01-01T12:00:00Z",
          metadata: { stopped: true },
        },
      ],
    };
    const out = mapConversationMessages(data);
    const assistant = out.find((m) => m.role === "assistant") as AssistantMessage;
    expect(assistant.stopped).toBe(true);
  });

  it("leaves stopped undefined when metadata has no stopped flag", () => {
    const data: RawConversationResponse = {
      id: "conv-not-stopped",
      mode: "tutor",
      messages: [
        {
          id: "a1",
          role: "assistant",
          content: { text: "Full answer." },
          timestamp: "2024-01-01T12:00:00Z",
          metadata: {},
        },
      ],
    };
    const out = mapConversationMessages(data);
    const assistant = out.find((m) => m.role === "assistant") as AssistantMessage;
    expect(assistant.stopped).toBeUndefined();
  });

  it("assistant message with object content gets structuredOutput", () => {
    const data: RawConversationResponse = {
      id: "conv8",
      mode: "facilitate",
      messages: [
        {
          id: "a1",
          role: "assistant",
          content: { text: "Chapter summary.", _schema: "ChapterDigest", digest: "…" },
          timestamp: "2024-01-01T12:00:00Z",
        },
      ],
    };
    const msgs = mapConversationMessages(data);
    const msg = msgs[0] as any;
    expect(msg.mode).toBe("facilitate");
    expect(msg.structuredOutput).toBeDefined();
    expect(msg.structuredOutput.schema).toBe("ChapterDigest");
    // _schema marker should be stripped from the data payload
    expect(msg.structuredOutput.data._schema).toBeUndefined();
  });

  it("uses per-message metadata.turnMode, falling back to the conversation mode", () => {
    const out = mapConversationMessages({
      mode: "tutor",
      messages: [
        { role: "user", content: "q" },
        { role: "assistant", content: "digest", metadata: { turnMode: "facilitate" } },
        { role: "user", content: "q2" },
        { role: "assistant", content: "ans" }, // legacy: no turnMode
      ],
    } as never);
    const assistants = out.filter((m) => m.role === "assistant") as AssistantMessage[];
    expect(assistants[0].mode).toBe("facilitate"); // from metadata.turnMode
    expect(assistants[1].mode).toBe("tutor");      // fallback to convMode
  });

  it("persisted StoryDigest (object) revives to structuredOutput.schema === 'StoryDigest'", () => {
    const storyDigest = {
      _schema: "StoryDigest",
      book: "hansen-probability",
      chapter: "ch07 · 7.4–7.5",
      takes: [{ heading: "Chebyshev", story: "Opens…", items: [] }],
      unfilled_subjects: [],
    };
    const data: RawConversationResponse = {
      id: "conv-story-object",
      mode: "extension",
      messages: [
        {
          id: "a1",
          role: "assistant",
          content: storyDigest,
          timestamp: "2024-01-01T12:00:00Z",
          metadata: { turnMode: "extension" },
        },
      ],
    };
    const msgs = mapConversationMessages(data);
    const msg = msgs[0] as AssistantMessage;
    expect(msg.structuredOutput).toBeDefined();
    expect(msg.structuredOutput!.schema).toBe("StoryDigest");
    expect((msg.structuredOutput!.data as { book: string }).book).toBe("hansen-probability");
    expect((msg.structuredOutput!.data as { _schema?: string })._schema).toBeUndefined();
  });

  it("persisted StoryDigest (JSON string) revives to structuredOutput.schema === 'StoryDigest'", () => {
    const storyDigestStr = JSON.stringify({
      _schema: "StoryDigest",
      book: "hansen-probability",
      chapter: "ch07 · 7.4–7.5",
      takes: [],
      unfilled_subjects: ["history of LLN"],
    });
    const data: RawConversationResponse = {
      id: "conv-story-string",
      mode: "extension",
      messages: [
        {
          id: "a1",
          role: "assistant",
          content: storyDigestStr,
          timestamp: "2024-01-01T12:00:00Z",
          metadata: { turnMode: "extension" },
        },
      ],
    };
    const msgs = mapConversationMessages(data);
    const msg = msgs[0] as AssistantMessage;
    expect(msg.structuredOutput).toBeDefined();
    expect(msg.structuredOutput!.schema).toBe("StoryDigest");
    expect((msg.structuredOutput!.data as { book: string }).book).toBe("hansen-probability");
  });

  it("recognizes the extension mode from metadata.turnMode (badge on reload)", () => {
    const out = mapConversationMessages({
      mode: "extension",
      messages: [
        { role: "user", content: "extend ch7" },
        { role: "assistant", content: '{"_schema":"ExtensionDigest","book":"b","chapter":"7","points":[],"unfilled_gaps":[]}', metadata: { turnMode: "extension" } },
      ],
    } as never);
    const assistants = out.filter((m) => m.role === "assistant") as AssistantMessage[];
    expect(assistants[0].mode).toBe("extension");
  });
});

describe("mapConversationMessages — TutorAnswer formal_statements", () => {
  it("preserves formal_statements[] in structuredOutput.data for TutorAnswer", () => {
    const data: RawConversationResponse = {
      id: "conv-fs1",
      mode: "tutor",
      messages: [
        {
          id: "a1",
          role: "assistant",
          content: {
            _schema: "TutorAnswer",
            text: "## Definition\n\nSome definition.",
            citations: [],
            formal_statements: [
              { kind: "definition", label: "Definition 14.1", statement: "$$F(x_{t})=F(x_{t+h})$$", cite: 1 },
              { kind: "theorem", label: "", statement: "E[X] = μ", cite: 2 },
            ],
          },
          timestamp: "2024-01-01T12:00:00Z",
        },
      ],
    };
    const msgs = mapConversationMessages(data);
    const msg = msgs[0] as AssistantMessage;
    expect(msg.structuredOutput).toBeDefined();
    expect(msg.structuredOutput!.schema).toBe("TutorAnswer");
    const d = msg.structuredOutput!.data as { formal_statements?: { kind: string; label: string; statement: string; cite: number }[] };
    expect(d.formal_statements).toBeDefined();
    expect(d.formal_statements).toHaveLength(2);
    expect(d.formal_statements![0].kind).toBe("definition");
    expect(d.formal_statements![0].label).toBe("Definition 14.1");
    expect(d.formal_statements![1].kind).toBe("theorem");
    expect(d.formal_statements![1].label).toBe("");
  });

  it("preserves formal_statements from a JSON string content", () => {
    const content = JSON.stringify({
      _schema: "TutorAnswer",
      text: "## Formal statement\n\nA theorem.",
      citations: [],
      formal_statements: [
        { kind: "theorem", label: "Theorem 2.1", statement: "MSE = bias² + variance", cite: 3 },
      ],
    });
    const data: RawConversationResponse = {
      id: "conv-fs2",
      mode: "tutor",
      messages: [
        {
          id: "a2",
          role: "assistant",
          content: content,
          timestamp: "2024-01-01T12:00:00Z",
        },
      ],
    };
    const msgs = mapConversationMessages(data);
    const msg = msgs[0] as AssistantMessage;
    expect(msg.structuredOutput!.schema).toBe("TutorAnswer");
    const d = msg.structuredOutput!.data as { formal_statements?: { kind: string; label: string; statement: string; cite: number }[] };
    expect(d.formal_statements).toHaveLength(1);
    expect(d.formal_statements![0].kind).toBe("theorem");
    expect(d.formal_statements![0].label).toBe("Theorem 2.1");
  });
});
