import { useCallback, useMemo, useReducer, useRef } from "react";
import type {
  Message, UserMessage, AssistantMessage, AssistantBlock,
  Source, Figure, RetrievalMetadata, ModeId, ChatEvent,
} from "../types";
import { streamChat, streamResume, fetchRunStatus, cancelRun } from "../api/sse";
import type { ChatRequestBody } from "../api/sse";

// Sentinel slice key for the "no conversation yet" draft. Mapped back to
// `null` in the value exposed to App so the lazy-create flow is unchanged.
export const DRAFT_KEY = "__draft__";

// ─── State ────────────────────────────────────────────────────────────────────

export interface UsageStats {
  durationMs: number;
  promptChars: number;
  completionChars: number;
  estTokens: number;
}

export interface FiguresMeta {
  status: "ok" | "no_candidates" | "all_rejected" | "error" | "disabled" | "no_sources";
  reason: string;
  candidateCount: number;
  approvedCount: number;
}

export interface ChatState {
  messages: Message[];
  sources: Source[];
  figures: Figure[];
  figuresMeta: FiguresMeta | undefined;
  metadata: RetrievalMetadata | undefined;
  status: "idle" | "streaming" | "error";
  conversationId: string | null;
  usage: UsageStats | null;
  streamingPhase: "idle" | "thinking" | "writing";
  // Highest SSE `seq` applied to this slice (§13); drives resume `after`.
  lastSeq: number;
}

const initialState: ChatState = {
  messages: [],
  sources: [],
  figures: [],
  figuresMeta: undefined,
  metadata: undefined,
  status: "idle",
  conversationId: null,
  usage: null,
  streamingPhase: "idle",
  lastSeq: 0,
};

// ─── Actions ──────────────────────────────────────────────────────────────────

// Slice-level actions mutate ONE conversation's ChatState.
type SliceAction =
  | { type: "USER_SENT"; text: string; userId: string; assistantId: string; time: string }
  | { type: "EVENT"; ev: ChatEvent }
  | { type: "BEGIN_RESUME"; assistantId: string; time: string }
  | { type: "LOAD_CONVERSATION"; id: string; messages: Message[] }
  | { type: "STOP" };

// Store-level actions carry a `convId` and route to the matching slice, or
// manage which slice is active (§13 multi-conversation store).
export type Action =
  | { type: "SLICE"; convId: string; action: SliceAction }
  | { type: "SET_ACTIVE"; id: string }
  | { type: "RESET_DRAFT" };

// ─── Helpers ──────────────────────────────────────────────────────────────────

function nowTime(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function nowTimestamp(): string {
  return new Date().toISOString();
}

function makeUserId(): string {
  return `u_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

function makeAssistantId(): string {
  return `a_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

function lastAssistant(messages: Message[]): AssistantMessage | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") return messages[i] as AssistantMessage;
  }
  return null;
}

function updateLastAssistant(
  messages: Message[],
  updater: (msg: AssistantMessage) => AssistantMessage,
): Message[] {
  const idx = [...messages].reverse().findIndex((m) => m.role === "assistant");
  if (idx === -1) return messages;
  const realIdx = messages.length - 1 - idx;
  const updated = messages.slice();
  updated[realIdx] = updater(updated[realIdx] as AssistantMessage);
  return updated;
}

// Append text to last open "p" block, or create one
function appendToken(blocks: AssistantBlock[], text: string): AssistantBlock[] {
  if (blocks.length > 0) {
    const last = blocks[blocks.length - 1];
    if (last.type === "p") {
      return [
        ...blocks.slice(0, -1),
        { type: "p" as const, text: last.text + text },
      ];
    }
  }
  return [...blocks, { type: "p" as const, text }];
}

// ─── Reducer ──────────────────────────────────────────────────────────────────

function chatReducer(state: ChatState, action: SliceAction): ChatState {
  switch (action.type) {
    case "BEGIN_RESUME": {
      // Reconnecting to a detached run after the local stream was lost (e.g.
      // page refresh): the persisted history holds the user message but not
      // the in-flight assistant turn, so append a placeholder for replay.
      const assistantPlaceholder: AssistantMessage = {
        role: "assistant",
        id: action.assistantId,
        time: action.time,
        timestamp: nowTimestamp(),
        mode: "tutor",
        model: "",
        books: [],
        sourceCount: 0,
        latencyMs: 0,
        blocks: [],
        status: "pending",
      };
      return {
        ...state,
        messages: [...state.messages, assistantPlaceholder],
        status: "streaming",
        streamingPhase: "thinking",
      };
    }

    case "USER_SENT": {
      const time = action.time;
      const ts = nowTimestamp();
      const userMsg: UserMessage = {
        role: "user",
        id: action.userId,
        time,
        timestamp: ts,
        text: action.text,
      };
      const assistantPlaceholder: AssistantMessage = {
        role: "assistant",
        id: action.assistantId,
        time,
        timestamp: ts,
        mode: "tutor",
        model: "",
        books: [],
        sourceCount: 0,
        latencyMs: 0,
        blocks: [],
        status: "pending",
      };
      return {
        ...state,
        messages: [...state.messages, userMsg, assistantPlaceholder],
        status: "streaming",
        streamingPhase: "thinking",
      };
    }

    case "EVENT": {
      const ev = action.ev;

      switch (ev.type) {
        case "meta":
          return {
            ...state,
            messages: updateLastAssistant(state.messages, (msg) => ({
              ...msg,
              mode: ev.mode as ModeId,
              model: ev.model,
              books: ev.books,
              sourceCount: ev.sourceCount,
              latencyMs: ev.latencyMs,
              status: "streaming",
            })),
          };

        case "token":
          return {
            ...state,
            streamingPhase: "writing",
            messages: updateLastAssistant(state.messages, (msg) => ({
              ...msg,
              status: "streaming",
              blocks: appendToken(msg.blocks, ev.text),
            })),
          };

        case "paragraph_break":
          return {
            ...state,
            messages: updateLastAssistant(state.messages, (msg) => {
              const last = msg.blocks[msg.blocks.length - 1];
              if (last && last.type === "p" && last.text.trim() === "") {
                // Skip empty paragraph
                return msg;
              }
              return {
                ...msg,
                // Close current p by adding a new empty p (next token will open it)
                blocks: [...msg.blocks, { type: "p" as const, text: "" }],
              };
            }),
          };

        case "math_block":
          return {
            ...state,
            messages: updateLastAssistant(state.messages, (msg) => ({
              ...msg,
              blocks: [...msg.blocks, { type: "math" as const, tex: ev.tex }],
            })),
          };

        case "figure":
          return {
            ...state,
            messages: updateLastAssistant(state.messages, (msg) => ({
              ...msg,
              blocks: [
                ...msg.blocks,
                {
                  type: "figure" as const,
                  ref: ev.ref,
                  book: ev.book,
                  chapter: ev.chapter,
                  caption: ev.caption,
                  chart: ev.chart,
                },
              ],
            })),
          };

        case "source_chip": {
          // Append to last sources block, or create a new one
          return {
            ...state,
            messages: updateLastAssistant(state.messages, (msg) => {
              const blocks = msg.blocks;
              const lastBlock = blocks[blocks.length - 1];
              const chip = { book: ev.book, section: ev.section };
              if (lastBlock && lastBlock.type === "sources") {
                return {
                  ...msg,
                  blocks: [
                    ...blocks.slice(0, -1),
                    { type: "sources" as const, chips: [...lastBlock.chips, chip] },
                  ],
                };
              }
              return {
                ...msg,
                blocks: [...blocks, { type: "sources" as const, chips: [chip] }],
              };
            }),
          };
        }

        case "sources_full":
          return {
            ...state,
            sources: ev.sources,
            messages: updateLastAssistant(state.messages, (msg) => ({
              ...msg,
              sources: ev.sources,
            })),
          };

        case "figures_full":
          return {
            ...state,
            figures: ev.figures,
            messages: updateLastAssistant(state.messages, (msg) => ({
              ...msg,
              figures: ev.figures,
            })),
          };

        case "figures_meta":
          if (ev.status !== "ok" && ev.status !== "disabled") {
            // eslint-disable-next-line no-console
            console.warn(
              `[figures_meta] ${ev.status}: ${ev.reason} ` +
                `(candidates=${ev.candidateCount}, approved=${ev.approvedCount})`,
            );
          }
          return {
            ...state,
            figuresMeta: {
              status: ev.status,
              reason: ev.reason,
              candidateCount: ev.candidateCount,
              approvedCount: ev.approvedCount,
            },
          };

        case "retrieval_meta":
          return {
            ...state,
            metadata: ev.meta,
            messages: updateLastAssistant(state.messages, (msg) => ({
              ...msg,
              retrievalMetadata: ev.meta,
            })),
          };

        case "usage":
          return {
            ...state,
            usage: {
              durationMs: ev.durationMs,
              promptChars: ev.promptChars,
              completionChars: ev.completionChars,
              estTokens: ev.estTokens,
            },
          };

        case "done":
          return {
            ...state,
            status: "idle",
            streamingPhase: "idle",
            messages: updateLastAssistant(state.messages, (msg) => {
              // Remove trailing empty p blocks
              const blocks = msg.blocks.filter(
                (b) => !(b.type === "p" && b.text.trim() === ""),
              );
              // The backend emits `error` followed by `done`; keep the error
              // status so the error block stays visible.
              const status = msg.status === "error" ? "error" : "complete";
              return { ...msg, status, blocks };
            }),
          };

        case "clarify":
          return {
            ...state,
            status: "idle",
            streamingPhase: "idle",
            messages: updateLastAssistant(state.messages, (msg) => ({
              ...msg,
              status: "complete",
              structuredOutput: {
                schema: "Clarify",
                data: {
                  reason: ev.reason, message: ev.message,
                  candidates: ev.candidates, chapter_guess: ev.chapter_guess,
                  sections_guess: ev.sections_guess,
                },
              },
            })),
          };

        case "stage": {
          const label = ev.label;
          if ((ev.stage === "point" || ev.stage === "story") && label) {
            return {
              ...state,
              messages: updateLastAssistant(state.messages, (msg) => ({
                ...msg,
                pendingExtensionPoints: [
                  ...(msg.pendingExtensionPoints ?? []),
                  label,
                ],
              })),
            };
          }
          return state;
        }

        case "structured_output":
          return {
            ...state,
            messages: updateLastAssistant(state.messages, (msg) => ({
              ...msg,
              structuredOutput: { schema: ev.schema, data: ev.data },
            })),
          };

        case "error":
          return {
            ...state,
            status: "error",
            messages: updateLastAssistant(state.messages, (msg) => ({
              ...msg,
              status: "error",
              error: { code: ev.code, message: ev.message },
            })),
          };

        default:
          return state;
      }
    }

    case "LOAD_CONVERSATION": {
      // Hydrate the right-hand ContextPanel from the most recent assistant
      // message that carries sources/figures/retrieval metadata.  Without
      // this, opening an old conversation leaves the transparency panel
      // empty even though the data was persisted.
      let hydratedSources: Source[] = [];
      let hydratedFigures: Figure[] = [];
      let hydratedMeta: RetrievalMetadata | undefined = undefined;
      for (let i = action.messages.length - 1; i >= 0; i--) {
        const m = action.messages[i];
        if (m.role !== "assistant") continue;
        if (m.sources && m.sources.length) hydratedSources = m.sources;
        if (m.figures && m.figures.length) hydratedFigures = m.figures;
        // retrievalMetadata is set on assistant messages; fall back via meta
        const meta = (m as AssistantMessage & {
          retrievalMetadata?: RetrievalMetadata;
        }).retrievalMetadata;
        if (meta) hydratedMeta = meta;
        if (hydratedSources.length || hydratedFigures.length || hydratedMeta) break;
      }
      return {
        ...initialState,
        conversationId: action.id,
        messages: action.messages,
        sources: hydratedSources,
        figures: hydratedFigures,
        metadata: hydratedMeta,
      };
    }

    case "STOP":
      return {
        ...state,
        status: "idle",
        streamingPhase: "idle",
        messages: updateLastAssistant(state.messages, (msg) => {
          const blocks = msg.blocks.filter(
            (b) => !(b.type === "p" && b.text.trim() === ""),
          );
          return { ...msg, status: "complete", stopped: true, blocks };
        }),
      };

    default:
      return state;
  }
}

// ─── Store reducer (multi-conversation, §13) ───────────────────────────────────

export interface StoreState {
  byConv: Record<string, ChatState>;
  active: string; // convId, or DRAFT_KEY
}

function freshSlice(): ChatState {
  return { ...initialState };
}

export const initialStore: StoreState = {
  byConv: { [DRAFT_KEY]: freshSlice() },
  active: DRAFT_KEY,
};

export function storeReducer(state: StoreState, action: Action): StoreState {
  switch (action.type) {
    case "SET_ACTIVE": {
      const byConv = state.byConv[action.id]
        ? state.byConv
        : { ...state.byConv, [action.id]: freshSlice() };
      return { byConv, active: action.id };
    }

    case "RESET_DRAFT":
      // Clear ONLY the draft slice and focus it — other (possibly streaming)
      // conversations are left untouched so their runs keep going.
      return {
        byConv: { ...state.byConv, [DRAFT_KEY]: freshSlice() },
        active: DRAFT_KEY,
      };

    case "SLICE": {
      const prev = state.byConv[action.convId] ?? freshSlice();
      let next = chatReducer(prev, action.action);
      // Track the highest applied SSE seq for resume `after` (§13).
      if (action.action.type === "EVENT" && action.action.ev.seq != null) {
        next = { ...next, lastSeq: Math.max(next.lastSeq, action.action.ev.seq) };
      }
      if (next === prev) return state;
      return { ...state, byConv: { ...state.byConv, [action.convId]: next } };
    }

    default:
      return state;
  }
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export interface ChatSettings {
  temperature?: number | null;
  top_k?: number | null;
  rerank?: boolean | null;
}

export interface UseChatOptions {
  mode: string;
  model: string;
  bookFilter: string[] | "ALL";
  settings?: ChatSettings;
  stageModels?: Record<string, string> | null;
  diversityAuthors?: number | "auto";
}

export function useChat({ mode, model, bookFilter, settings, stageModels, diversityAuthors }: UseChatOptions) {
  const [store, dispatch] = useReducer(storeReducer, initialStore);
  // One AbortController per conversation key — switching conversations no
  // longer aborts; we only abort a conv's own stream on resend (§13).
  const abortMap = useRef<Map<string, AbortController>>(new Map());
  // Conversations we have already attached a resume stream to this session,
  // so reopening does not spawn a duplicate subscriber.
  const resumingRef = useRef<Set<string>>(new Set());

  const active = store.active;
  const slice = store.byConv[active] ?? initialState;

  // Latest store snapshot for stable callbacks — lets `loadConversation` read
  // current slice state WITHOUT depending on `store.byConv` (which changes on
  // every token and would otherwise re-fire the deep-link effect in App,
  // spamming /status and re-wiping the slice mid-stream).
  const storeRef = useRef(store);
  storeRef.current = store;

  // Stream a detached run's events into the slice keyed by `convKey`.
  const pump = useCallback(
    async (
      convKey: string,
      run: (onEvent: (ev: ChatEvent) => void, signal: AbortSignal) => Promise<void>,
    ) => {
      abortMap.current.get(convKey)?.abort();
      const ac = new AbortController();
      abortMap.current.set(convKey, ac);
      try {
        await run(
          (ev) => dispatch({ type: "SLICE", convId: convKey, action: { type: "EVENT", ev } }),
          ac.signal,
        );
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        dispatch({
          type: "SLICE",
          convId: convKey,
          action: {
            type: "EVENT",
            ev: { type: "error", code: "CLIENT_ERROR", message: (err as Error).message || "Unknown error" },
          },
        });
      } finally {
        if (abortMap.current.get(convKey) === ac) abortMap.current.delete(convKey);
      }
    },
    [],
  );

  const sendMessage = useCallback(
    async (
      text: string,
      convIdOverride?: string | null,
      bookFilterOverride?: string[] | "ALL",
    ) => {
      const convId = convIdOverride ?? (active === DRAFT_KEY ? null : active);
      const convKey = convId ?? DRAFT_KEY;

      const userId = makeUserId();
      const assistantId = makeAssistantId();
      const time = nowTime();

      dispatch({ type: "SET_ACTIVE", id: convKey });
      dispatch({ type: "SLICE", convId: convKey, action: { type: "USER_SENT", text, userId, assistantId, time } });

      const body: ChatRequestBody = {
        conversationId: convId,
        message: text,
        mode,
        model,
        bookFilter: bookFilterOverride ?? bookFilter,
        temperature: settings?.temperature ?? null,
        top_k: settings?.top_k ?? null,
        rerank: settings?.rerank ?? null,
        stageModels: stageModels && Object.keys(stageModels).length ? stageModels : null,
        ...(diversityAuthors != null ? { diversityAuthors } : {}),
      };

      await pump(convKey, (onEvent, signal) => streamChat(body, onEvent, signal));
    },
    [active, mode, model, bookFilter, settings?.temperature, settings?.top_k, settings?.rerank, stageModels, diversityAuthors, pump],
  );

  const stopStream = useCallback(
    (convIdOverride?: string | null) => {
      const convId = convIdOverride ?? (active === DRAFT_KEY ? null : active);
      const convKey = convId ?? DRAFT_KEY;
      abortMap.current.get(convKey)?.abort();
      if (convId) void cancelRun(convId);
      dispatch({ type: "SLICE", convId: convKey, action: { type: "STOP" } });
    },
    [active],
  );

  const resetThread = useCallback(() => {
    // Focus a fresh draft; leave other conversations' runs alive (§13).
    dispatch({ type: "RESET_DRAFT" });
  }, []);

  const setConversationId = useCallback((id: string) => {
    dispatch({ type: "SET_ACTIVE", id });
  }, []);

  // Open a conversation. If its slice is already streaming locally we keep it
  // (do NOT clobber the live partial). Otherwise hydrate from the persisted
  // transcript, then ask the backend whether a detached run is still active
  // and, if so, attach a resume stream that replays the missed events (§13).
  const loadConversation = useCallback(
    (id: string, messages: Message[]) => {
      const existing = storeRef.current.byConv[id];
      if (existing && existing.status === "streaming") {
        dispatch({ type: "SET_ACTIVE", id });
        return;
      }
      dispatch({ type: "SLICE", convId: id, action: { type: "LOAD_CONVERSATION", id, messages } });
      dispatch({ type: "SET_ACTIVE", id });

      if (abortMap.current.has(id) || resumingRef.current.has(id)) return;
      resumingRef.current.add(id);
      void (async () => {
        try {
          const st = await fetchRunStatus(id);
          if (!st.active) return;
          // We just reset the slice to the persisted transcript (no in-flight
          // assistant turn), so replay the full buffer from seq 0 into a fresh
          // placeholder.
          dispatch({
            type: "SLICE",
            convId: id,
            action: { type: "BEGIN_RESUME", assistantId: makeAssistantId(), time: nowTime() },
          });
          await pump(id, (onEvent, signal) => streamResume(id, 0, onEvent, signal));
        } finally {
          resumingRef.current.delete(id);
        }
      })();
    },
    [pump],
  );

  const lastMsg = lastAssistant(slice.messages);

  // Conversation keys whose run is still streaming — drives the sidebar dot.
  const streamingIds = useMemo(
    () =>
      Object.entries(store.byConv)
        .filter(([k, s]) => k !== DRAFT_KEY && s.status === "streaming")
        .map(([k]) => k),
    [store.byConv],
  );

  return {
    messages: slice.messages,
    sources: slice.sources,
    figures: slice.figures,
    figuresMeta: slice.figuresMeta,
    metadata: slice.metadata,
    status: slice.status,
    isStreaming: slice.status === "streaming",
    streamingPhase: slice.streamingPhase,
    usage: slice.usage,
    lastAssistant: lastMsg,
    conversationId: active === DRAFT_KEY ? null : active,
    streamingIds,
    sendMessage,
    stopStream,
    resetThread,
    setConversationId,
    loadConversation,
  };
}
