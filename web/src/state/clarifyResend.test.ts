// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// Capture the body handed to streamChat so we can assert the bookFilter scope.
const { streamChatMock } = vi.hoisted(() => ({ streamChatMock: vi.fn() }));
vi.mock("../api/sse", () => ({
  streamChat: streamChatMock,
  streamResume: vi.fn(),
  fetchRunStatus: vi.fn(async () => ({ active: false })),
  cancelRun: vi.fn(async () => ({ cancelled: false })),
}));

import { useChat } from "./chat";

function sentBody(call: number): { bookFilter: unknown } {
  return streamChatMock.mock.calls[call][0] as { bookFilter: unknown };
}

describe("clarify re-send scoping", () => {
  beforeEach(() => {
    streamChatMock.mockReset();
    streamChatMock.mockResolvedValue(undefined);
  });

  it("a bookFilter override wins over the hook's bookFilter (clarify pick scopes the re-send)", async () => {
    const { result } = renderHook(() =>
      useChat({ mode: "tutor", model: "gpt-4o", bookFilter: "ALL" }),
    );
    await act(async () => {
      await result.current.sendMessage("hansen ch7", "conv-1", ["hansen"]);
    });
    expect(streamChatMock).toHaveBeenCalled();
    expect(sentBody(0).bookFilter).toEqual(["hansen"]);
  });

  it("without an override the hook's bookFilter is used", async () => {
    const { result } = renderHook(() =>
      useChat({ mode: "tutor", model: "gpt-4o", bookFilter: "ALL" }),
    );
    await act(async () => {
      await result.current.sendMessage("hi", "conv-2");
    });
    expect(sentBody(0).bookFilter).toEqual("ALL");
  });
});
