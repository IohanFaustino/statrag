// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import MessageThread from "./MessageThread";
import type { Message, QAStoryAnswer, FacilitateStory, ModeId, RetrievalMetadata } from "../types";

// Minimal assistant message in "pending" state (thinking indicator shows)
const pendingMsg: Message = {
  role: "assistant",
  id: "a1",
  time: "12:00",
  timestamp: "2026-06-04T12:00:00Z",
  mode: "tutor",
  model: "gpt-4",
  books: [],
  sourceCount: 0,
  latencyMs: 0,
  blocks: [],
  status: "pending",
};

describe("MessageThread — thinkingLabel prop", () => {
  it("renders custom thinkingLabel when provided", () => {
    render(
      <MessageThread
        thread={[pendingMsg]}
        thinkingLabel="Synthesizing across authors… (~45 s)"
        isStreaming={true}
        streamingPhase="thinking"
      />,
    );
    expect(
      screen.getByText("Synthesizing across authors… (~45 s)"),
    ).toBeInTheDocument();
  });

  it("renders default 'Thinking' label when thinkingLabel is omitted", () => {
    render(
      <MessageThread
        thread={[pendingMsg]}
        isStreaming={true}
        streamingPhase="thinking"
      />,
    );
    expect(screen.getByText("Thinking")).toBeInTheDocument();
  });
});

describe("MessageThread — QAStoryAnswer structured output routing", () => {
  const storyAnswer: QAStoryAnswer = {
    intro: "Bias and variance are foundational concepts.",
    deepening: "The tradeoff arises because reducing complexity increases bias.",
    conclusion: "Understanding this tradeoff guides model selection.",
    citations: [
      { kind: "corpus", label: "Hansen Ch3" },
      { kind: "wikipedia", label: "Bias-variance tradeoff", url: "https://en.wikipedia.org/wiki/Bias-variance_tradeoff" },
    ],
    math_blocks: [],
    grounding: { ok: true, confidence: 0.9 },
  };

  const msgWithStory: Message = {
    role: "assistant",
    id: "a2",
    time: "12:01",
    timestamp: "2026-06-04T12:01:00Z",
    mode: "qa",
    model: "gpt-5.4-nano-2026-03-17",
    books: ["hansen"],
    sourceCount: 2,
    latencyMs: 1000,
    blocks: [],
    status: "complete",
    structuredOutput: { schema: "QAStoryAnswer", data: storyAnswer },
  };

  it("routes QAStoryAnswer schema to QAAnswerCard and renders intro text", () => {
    render(<MessageThread thread={[msgWithStory]} isStreaming={false} streamingPhase="idle" />);
    expect(screen.getByText(/foundational concepts/)).toBeInTheDocument();
  });

  it("routes QAStoryAnswer schema and renders wiki chip link", () => {
    render(<MessageThread thread={[msgWithStory]} isStreaming={false} streamingPhase="idle" />);
    // wiki chip renders as a link
    const link = screen.getByRole("link", { name: /bias-variance tradeoff/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "https://en.wikipedia.org/wiki/Bias-variance_tradeoff");
  });
});

describe("MessageThread — common-ground is facilitate-only", () => {
  const story: FacilitateStory = {
    mode: "facilitate_story",
    scope: { book_slug: "hansen", chapter_id: "ch07", section_id: "7.4", requested_subtopics: [], resolution: [] },
    hook: "Why averages stabilise.",
    movements: [{ prose: "The [[c1]] is the engine here.", formal: null }],
    takeaway: "Done.",
    concepts: [{ id: "c1", term: "law of large numbers", kind: "theorem", explanation: "x",
      provenance: { book_slug: "hansen", book_name: "Probability", authors_short: "Hansen",
        section: "7.4", page_from: 1, page_to: 2, chunk_id: "x", same_author: true, fallback: false } }],
    citations: [], math_blocks: [], grounding: { ok: true, unsupported: [], confidence: 1 },
  };
  // A facilitate-produced message stays on screen even after the user switches
  // the active mode; the gate is the ACTIVE mode (dropdown), not msg.mode.
  const facStoryMsg: Message = {
    role: "assistant", id: "f1", time: "12:02", timestamp: "2026-06-04T12:02:00Z",
    mode: "facilitate" as ModeId, model: "nano", books: ["hansen"], sourceCount: 1, latencyMs: 1,
    blocks: [], status: "complete", structuredOutput: { schema: "FacilitateStory", data: story },
  };

  it("renders an interactive concept anchor when the active mode is facilitate", () => {
    render(<MessageThread thread={[facStoryMsg]} activeMode="facilitate"
      onOpenConcept={() => {}} isStreaming={false} streamingPhase="idle" />);
    expect(screen.getByRole("button", { name: /law of large numbers/i })).toBeInTheDocument();
  });

  it("does NOT expose an interactive concept anchor when the active mode is qa", () => {
    render(<MessageThread thread={[facStoryMsg]} activeMode="qa"
      onOpenConcept={() => {}} isStreaming={false} streamingPhase="idle" />);
    expect(screen.queryByRole("button", { name: /law of large numbers/i })).toBeNull();
  });
});

describe("MessageThread — finalize badge", () => {
  const baseMeta: RetrievalMetadata = {
    rewrittenQuery: "stationarity",
    embedding: "text-embedding-3-large",
    retrievalMs: 1200,
    collections: ["stats_textbooks"],
    filter: "",
    topK: 20,
    scoreThreshold: 0.3,
    mode: "tutor",
  };

  it("shows Finalized badge when finalizeApplied is true with model and route", () => {
    const meta: RetrievalMetadata = {
      ...baseMeta,
      finalizeModel: "gpt-5.4",
      finalizeRoute: "structured",
      finalizeApplied: true,
    };
    const msg: Message = {
      role: "assistant", id: "f1", time: "12:03", timestamp: "2026-06-04T12:03:00Z",
      mode: "tutor", model: "gpt-5.4", books: ["hansen"], sourceCount: 5, latencyMs: 3000,
      blocks: [], status: "complete", retrievalMetadata: meta,
    };
    render(<MessageThread thread={[msg]} isStreaming={false} streamingPhase="idle" />);
    expect(screen.getByText(/Finalized/)).toBeInTheDocument();
    expect(screen.getByText(/gpt-5.4/)).toBeInTheDocument();
    expect(screen.getByText(/structured/)).toBeInTheDocument();
  });

  it("hides Finalized badge when finalizeApplied is false", () => {
    const meta: RetrievalMetadata = {
      ...baseMeta,
      finalizeModel: "deepseek-v4-pro",
      finalizeRoute: "tolerant",
      finalizeApplied: false,
    };
    const msg: Message = {
      role: "assistant", id: "f2", time: "12:04", timestamp: "2026-06-04T12:04:00Z",
      mode: "tutor", model: "deepseek-v4-pro", books: ["hansen"], sourceCount: 3, latencyMs: 2000,
      blocks: [], status: "complete", retrievalMetadata: meta,
    };
    render(<MessageThread thread={[msg]} isStreaming={false} streamingPhase="idle" />);
    expect(screen.queryByText(/Finalized/)).toBeNull();
  });

  it("hides Finalized badge when finalizeModel is null", () => {
    const meta: RetrievalMetadata = {
      ...baseMeta,
      finalizeModel: null,
      finalizeRoute: null,
      finalizeApplied: false,
    };
    const msg: Message = {
      role: "assistant", id: "f3", time: "12:05", timestamp: "2026-06-04T12:05:00Z",
      mode: "tutor", model: "gpt-5.4", books: ["hansen"], sourceCount: 2, latencyMs: 1500,
      blocks: [], status: "complete", retrievalMetadata: meta,
    };
    render(<MessageThread thread={[msg]} isStreaming={false} streamingPhase="idle" />);
    expect(screen.queryByText(/Finalized/)).toBeNull();
  });
});
