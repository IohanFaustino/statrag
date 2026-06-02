/**
 * Maps a raw conversation response (from GET /api/conversations/:id) to the
 * frontend Message[] type used by the chat state.
 *
 * Extracted so it can be unit-tested independently of the React component.
 *
 * Key correctness invariant: every assistant message receives the
 * conversation-level mode (e.g. "facilitate", "resume") rather than a
 * hardcoded "tutor" default.  Per-message mode is not persisted in the
 * messages table; the conversation digest carries the single mode for the
 * whole conversation.
 */
import type { ModeId, Source, Figure, RetrievalMetadata, Message } from "../types";

// ---------------------------------------------------------------------------
// Types for the raw backend payload
// ---------------------------------------------------------------------------

export interface RawMessage {
  id: string;
  role: string;
  content: unknown;
  timestamp: string;
  sources?: unknown;
  figures?: unknown;
  metadata?: unknown;
}

/** The shape returned by GET /api/conversations/:id */
export interface RawConversationResponse {
  id?: string;
  mode?: string;
  messages?: RawMessage[];
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Internal helpers (exported so tests can reach them)
// ---------------------------------------------------------------------------

/** Known conversation modes; anything else falls back to "tutor". */
const VALID_MODES: ReadonlySet<string> = new Set(["tutor", "qa", "facilitate", "resume"]);

/** Parse a raw mode string into a validated ModeId, falling back to "tutor". */
export function parseConvMode(raw: unknown): ModeId {
  return typeof raw === "string" && VALID_MODES.has(raw) ? (raw as ModeId) : "tutor";
}

/** Convert an ISO timestamp to a short HH:MM locale string. */
function toTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

const ASPECT_HEADINGS: Array<[string, string]> = [
  ["tldr", "Introduction"],
  ["definition", "Definition"],
  ["formal_statement", "Formal statement"],
  ["example_intuition", "Example & Intuition"],
  ["applications", "Applications"],
  ["further_reading", "Further reading"],
];

function assembleFromAspects(obj: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, heading] of ASPECT_HEADINGS) {
    const body = obj[key];
    if (typeof body === "string" && body.trim()) {
      parts.push(`## ${heading}\n\n${body.trim()}`);
    }
  }
  if (parts.length) return parts.join("\n\n");
  const a = (obj as { aspects?: Record<string, string> }).aspects;
  if (a && typeof a === "object") {
    for (const [key, heading] of ASPECT_HEADINGS) {
      const body = a[key];
      if (typeof body === "string" && body.trim()) {
        parts.push(`## ${heading}\n\n${body.trim()}`);
      }
    }
  }
  return parts.join("\n\n");
}

function reviveContent(raw: unknown): { text: string; structured: Record<string, unknown> | null } {
  const fromObject = (obj: Record<string, unknown>): { text: string; structured: Record<string, unknown> } => {
    let text = typeof obj.text === "string" ? (obj.text as string) : "";
    if (!text.trim()) text = assembleFromAspects(obj);
    return { text, structured: { ...obj, text } };
  };
  if (raw && typeof raw === "object") return fromObject(raw as Record<string, unknown>);
  if (typeof raw === "string") {
    const s = raw.trim();
    if (s.startsWith("{") && s.endsWith("}")) {
      try {
        const obj = JSON.parse(s);
        if (obj && typeof obj === "object" && ("text" in obj || "aspects" in obj || "tldr" in obj)) {
          return fromObject(obj as Record<string, unknown>);
        }
      } catch {
        // not JSON — fall through
      }
    }
    return { text: s, structured: null };
  }
  return { text: "", structured: null };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Convert the raw API response for a stored conversation into the Message[]
 * array expected by the chat reducer's LOAD_CONVERSATION action.
 *
 * @param data  Raw JSON body from GET /api/conversations/:id
 * @returns     Mapped Message array ready for loadConversation()
 */
export function mapConversationMessages(data: RawConversationResponse): Message[] {
  // Derive the conversation mode once; every assistant message inherits it
  // because per-message mode is not stored in the DB.
  const convMode = parseConvMode(data.mode);
  const rawMsgs: RawMessage[] = data.messages ?? [];

  return rawMsgs.map((m): Message => {
    const { text, structured } = reviveContent(m.content);

    if (m.role === "user") {
      return {
        role: "user" as const,
        id: m.id,
        time: toTime(m.timestamp),
        timestamp: m.timestamp,
        text,
      };
    }

    const schema =
      structured && typeof structured._schema === "string"
        ? (structured._schema as string)
        : "TutorAnswer";

    const base = {
      role: "assistant" as const,
      id: m.id,
      time: toTime(m.timestamp),
      timestamp: m.timestamp,
      mode: convMode,
      model: "",
      books: [],
      sourceCount: Array.isArray(m.sources) ? (m.sources as unknown[]).length : 0,
      latencyMs: 0,
      blocks: [{ type: "p" as const, text }],
      sources: (m.sources as unknown as Source[]) ?? undefined,
      figures: (m.figures as unknown as Figure[]) ?? undefined,
      retrievalMetadata: (m.metadata as unknown as RetrievalMetadata) ?? undefined,
      stopped: ((m.metadata as { stopped?: boolean } | null)?.stopped) ?? undefined,
      status: "complete" as const,
    };

    if (structured) {
      const clone: Record<string, unknown> = { ...structured };
      delete clone._schema;
      return { ...base, structuredOutput: { schema, data: clone } };
    }
    return base;
  });
}
