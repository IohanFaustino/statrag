import type { ChatEvent } from "../types";

export interface ChatRequestBody {
  conversationId?: string | null;
  message: string;
  mode: string;
  model: string;
  bookFilter: string[] | "ALL";
  // T13-F: optional user-controllable knobs forwarded to the backend
  // ChatRequest. `null` / `undefined` defer to the mode default.
  temperature?: number | null;
  top_k?: number | null;
  rerank?: boolean | null;
  // Per-stage model overrides (About-model feature). Maps pipeline stage id
  // ("expansion"|"draft"|"critique"|"image_judge") -> model id.
  stageModels?: Record<string, string> | null;
  // Author diversity step: 0 = off, N>=2 = target distinct authors.
  diversityAuthors?: number | "auto" | null;
  // Drafting workflow: "single" (default) or "orchestrator" (per-author workers).
  tutorWorkflow?: string;
}

// Read an SSE response body, parsing frames and invoking `onEvent` per event.
// Shared by the POST-start stream and the GET resume stream (§13).
async function pumpSse(res: Response, onEvent: (e: ChatEvent) => void): Promise<void> {
  if (!res.ok || !res.body) throw new Error(`chat http ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // SSE frames separated by \n\n OR \r\n\r\n (sse-starlette uses \r\n);
    // each frame has lines like "event: X" and "data: Y".
    while (true) {
      const crlf = buf.indexOf("\r\n\r\n");
      const lf = buf.indexOf("\n\n");
      let idx = -1;
      let sep = 0;
      if (crlf !== -1 && (lf === -1 || crlf <= lf)) {
        idx = crlf;
        sep = 4;
      } else if (lf !== -1) {
        idx = lf;
        sep = 2;
      } else {
        break;
      }
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + sep);
      const dataLine = frame
        .split(/\r?\n/)
        .find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      const json = dataLine.slice(5).trim();
      if (!json) continue;
      try {
        onEvent(JSON.parse(json) as ChatEvent);
      } catch {
        // ignore malformed frames
      }
    }
  }
}

// Start a chat turn (POST). With a conversationId the backend runs it as a
// detached, resumable run (§13); this fetch is just the first subscriber.
export async function streamChat(
  body: ChatRequestBody,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  await pumpSse(res, onEvent);
}

export interface RunStatus {
  exists: boolean;
  active: boolean;
  done: boolean;
  seq: number;
}

// Resume handshake: is a detached run still producing events for this conv?
export async function fetchRunStatus(convId: string): Promise<RunStatus> {
  const res = await fetch(`/api/chat/${convId}/status`);
  if (!res.ok) return { exists: false, active: false, done: false, seq: 0 };
  return (await res.json()) as RunStatus;
}

// Stop an in-flight detached run (§13). Best-effort; resolves cancelled=false
// on any non-OK response so the caller can still abort the client stream.
export async function cancelRun(convId: string): Promise<{ cancelled: boolean }> {
  try {
    const res = await fetch(`/api/chat/${convId}/cancel`, { method: "POST" });
    if (!res.ok) return { cancelled: false };
    return (await res.json()) as { cancelled: boolean };
  } catch {
    return { cancelled: false };
  }
}

// Resume / replay an in-flight (or just-finished) run, skipping events at or
// before `after` (§13). Used after a page refresh or when reopening a conv
// whose local stream was lost.
export async function streamResume(
  convId: string,
  after: number,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api/chat/${convId}/stream?after=${after}`, {
    headers: { accept: "text/event-stream" },
    signal,
  });
  await pumpSse(res, onEvent);
}
