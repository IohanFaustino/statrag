// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import MessageThread from "./MessageThread";
import type { Message, QAStoryAnswer, FacilitateStory, ModeId } from "../types";

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
