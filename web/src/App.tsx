import React, { useState, useEffect, useCallback } from "react";
import type { Book, Source, ModelProvider } from "./types";
import { mapConversationMessages } from "./lib/mapConversationMessages";
import { pickOpenedMode } from "./lib/pickOpenedMode";
import { lastTurnMode } from "./lib/lastTurnMode";
import { useTweaks, THEME_ACCENT_DEFAULTS } from "./state/tweaks";
import { useChat } from "./state/chat";
import { fetchProviders, createConversation } from "./api/client";
import Topbar from "./components/Topbar";
import Sidebar from "./components/Sidebar";
import type { ConvDigest } from "./components/Sidebar";
import ContextPanel from "./components/ContextPanel";
import MessageThread from "./components/MessageThread";
import InputBar from "./components/InputBar";
import TempChat from "./components/TempChat";
import { STATRAG_MODES } from "./lib/modes";
import BookModal from "./components/modals/BookModal";
import SourceModal from "./components/modals/SourceModal";
import AboutModelModal from "./components/modals/AboutModelModal";
import QAModeModal from "./components/modals/QAModeModal";
import ChapterFacilitateModal from "./components/modals/ChapterFacilitateModal";
import ChapterResumeModal from "./components/modals/ChapterResumeModal";
import ExtensionModeModal from "./components/modals/ExtensionModeModal";
import type { StageKey } from "./data/tutorPipeline";
import type { ChatSettings } from "./state/chat";
import { usePersistentState } from "./state/persist";
import { RECOMMENDED_MODEL_ID, recommendedModelId } from "./data/recommended";
import { conversationToMarkdown, assistantMessageToMarkdown, slugify, downloadBlob } from "./lib/exportMarkdown";
import { buildZipBlob } from "./lib/exportZip";

// Default per-stage model overrides for the deep-tutor pipeline. Persisted
// under "statrag.stageModels"; user changes via the tutor (i) modal flow.
//   plan  → Query planner stage  (deepseek-v4-pro — reasoner truncated JSON)
//   draft → Draft / synthesis    (deepseek-v4-pro — best-effort JSON path)
const DEFAULT_STAGE_MODELS: Record<string, string> = {
  plan: "deepseek-v4-pro",
  draft: "deepseek-v4-pro",
};

// ─── Fallback providers (used when /api/models fails) ────────────────────────

const FALLBACK_PROVIDERS: ModelProvider[] = [
  {
    id: "openai",
    name: "OpenAI",
    short: "OAI",
    color: "#10A37F",
    models: [
      {
        id: "gpt-4o",
        name: "GPT-4o",
        tagline: "Fast multimodal",
        cost: "$$$",
        speed: "fast",
        ctx: "128k",
      },
    ],
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    short: "DS",
    color: "#4D6BFE",
    models: [
      {
        id: "deepseek-v3",
        name: "DeepSeek V3",
        tagline: "Chat & code, open",
        cost: "$",
        speed: "fast",
        ctx: "64k",
      },
    ],
  },
];

// ─── Types ────────────────────────────────────────────────────────────────────

interface ConvGroups {
  today: ConvDigest[];
  yesterday: ConvDigest[];
  thisWeek: ConvDigest[];
  earlier: ConvDigest[];
}

interface RawConv {
  id: string;
  title: string;
  mode: string;
  updatedAt?: string;
  active?: boolean;
}

// ─── Date grouping ────────────────────────────────────────────────────────────

function groupConvsByDate(convs: RawConv[]): ConvGroups {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86400000);
  const startOfWeek = new Date(startOfToday.getTime() - 6 * 86400000);

  const groups: ConvGroups = {
    today: [],
    yesterday: [],
    thisWeek: [],
    earlier: [],
  };

  for (const conv of convs) {
    const ts = conv.updatedAt ? new Date(conv.updatedAt) : null;
    const digest: ConvDigest = {
      id: conv.id,
      title: conv.title,
      mode: conv.mode,
      active: conv.active,
    };

    if (!ts || ts >= startOfToday) {
      groups.today.push(digest);
    } else if (ts >= startOfYesterday) {
      groups.yesterday.push(digest);
    } else if (ts >= startOfWeek) {
      groups.thisWeek.push(digest);
    } else {
      groups.earlier.push(digest);
    }
  }

  return groups;
}

// ─── App ─────────────────────────────────────────────────────────────────────

const TWEAK_DEFAULTS = {
  theme: "dark" as const,
  accent: "#E5484D",
  density: "comfortable" as const,
  userStyle: "bubble" as const,
  fontPair: "plex" as const,
  sidebarOpen: true,
  contextOpen: true,
};

export default function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(!tweaks.sidebarOpen);
  const [contextCollapsed, setContextCollapsed] = useState(!tweaks.contextOpen);

  const [books, setBooks] = useState<Book[]>([]);
  const [providers, setProviders] = useState<ModelProvider[]>(FALLBACK_PROVIDERS);
  const [convGroups, setConvGroups] = useState<ConvGroups>({
    today: [],
    yesterday: [],
    thisWeek: [],
    earlier: [],
  });
  const [roadmaps, setRoadmaps] = useState<
    { id: string; title: string; scenes: number; date: string }[]
  >([]);

  // UI state
  const [booksModalOpen, setBooksModalOpen] = useState(false);
  const [openSource, setOpenSource] = useState<Source | null>(null);
  const [tempChatOpen, setTempChatOpen] = useState(false);
  const [tempSeed, setTempSeed] = useState<number | null>(null);

  // Tracks the last conversation whose picker mode we synced. Re-opening the
  // SAME conversation (popstate / re-select / re-render) is a no-op, so a mode
  // the user changed mid-conversation is preserved. Switching to a DIFFERENT
  // conversation and back DOES re-sync to that conversation's last-turn mode
  // (intended: the picker reflects where you left that conversation).
  const lastSyncedConvRef = React.useRef<string | null>(null);

  // Active mode / model — persisted across sessions so tutor configuration
  // survives a backend restart or a browser reload.
  const [activeMode, setActiveMode] = usePersistentState<string>("statrag.activeMode", "tutor");
  const [activeModel, setActiveModel] = usePersistentState<string>("statrag.activeModel", RECOMMENDED_MODEL_ID);

  // About-model modal (ephemeral) + per-stage model overrides (persisted).
  const [aboutModelId, setAboutModelId] = useState<string | null>(null);
  // Q&A mode info modal (ephemeral).
  const [qaModalOpen, setQaModalOpen] = useState(false);
  const [facilitateModalOpen, setFacilitateModalOpen] = useState(false);
  const [resumeModalOpen, setResumeModalOpen] = useState(false);
  const [extensionModalOpen, setExtensionModalOpen] = useState(false);
  const [stageModels, setStageModels] = usePersistentState<Record<string, string>>(
    "statrag.stageModels",
    DEFAULT_STAGE_MODELS,
  );

  // Author diversity: 0 = off, N>=2 = target distinct authors. Default 3.
  const [diversityAuthors, setDiversityAuthors] = usePersistentState<number | "auto">(
    "statrag.diversityAuthors",
    "auto",
  );

  // Derive recommended model id from the live registry (used by modals in Task 4).
  const recommendedModel = recommendedModelId(providers);

  // Derive bookFilter from selected books
  const selectedBooks = books.filter((b) => b.selected && b.indexed !== false);
  const bookFilter: string[] | "ALL" =
    selectedBooks.length === books.filter((b) => b.indexed !== false).length
      ? "ALL"
      : selectedBooks.map((b) => b.id);

  // T21: chat-UI knobs (temperature / top_k / rerank). `null` per-field
  // defers to the mode default. Rendered as a SettingsPicker popover inside
  // the InputBar toolbar.
  const [settings, setSettings] = usePersistentState<ChatSettings>("statrag.settings", {
    temperature: null,
    top_k: null,
    rerank: null,
  });

  // Chat state
  const {
    messages,
    sources,
    figures,
    figuresMeta,
    metadata,
    isStreaming,
    sendMessage,
    resetThread,
    conversationId,
    setConversationId,
    loadConversation,
    streamingPhase,
    stageLabel,
    usage,
    streamingIds,
    stopStream,
  } = useChat({
    mode: activeMode,
    model: activeModel,
    bookFilter,
    settings,
    stageModels,
    diversityAuthors,
  });

  const thinkingLabel = stageLabel;

  // Backend health (status dot)
  const [online, setOnline] = useState(false);
  useEffect(() => {
    let cancel = false;
    const ping = () => {
      fetch("/api/health")
        .then((r) => r.ok)
        .then((ok) => {
          if (!cancel) setOnline(ok);
        })
        .catch(() => {
          if (!cancel) setOnline(false);
        });
    };
    ping();
    const id = window.setInterval(ping, 10_000);
    return () => {
      cancel = true;
      window.clearInterval(id);
    };
  }, []);

  // Wrapped send: lazily create conversation on first message
  const handleSend = useCallback(
    async (text: string, bookFilterOverride?: string[] | "ALL") => {
      let activeConvId = conversationId;
      if (!activeConvId) {
        try {
          const title = text.length > 60 ? text.slice(0, 57) + "..." : text;
          const conv = await createConversation({
            title,
            mode: activeMode,
            model_id: activeModel,
            book_filter: bookFilter,
          });
          if (conv?.id) {
            activeConvId = conv.id;
            setConversationId(conv.id);
            setConvGroups((prev) => ({
              ...prev,
              today: [
                { id: conv.id, title: conv.title, mode: conv.mode, active: false },
                ...prev.today.filter((c) => c.id !== conv.id),
              ],
            }));
          }
        } catch {
          // proceed without persistence
        }
      }
      sendMessage(text, activeConvId, bookFilterOverride);
    },
    [conversationId, activeMode, activeModel, bookFilter, sendMessage, setConversationId],
  );

  // Sync collapse state when tweaks change externally
  useEffect(() => {
    setSidebarCollapsed(!tweaks.sidebarOpen);
  }, [tweaks.sidebarOpen]);

  useEffect(() => {
    setContextCollapsed(!tweaks.contextOpen);
  }, [tweaks.contextOpen]);

  // Load books from API (preserve selected state across re-loads)
  useEffect(() => {
    fetch("/api/books")
      .then((r) => r.json())
      .then((data: Book[]) => {
        setBooks((prev) => {
          if (prev.length === 0) return data;
          // Preserve user-toggled selected state
          const selMap = new Map(prev.map((b) => [b.id, b.selected]));
          return data.map((b) => ({
            ...b,
            selected: selMap.has(b.id) ? (selMap.get(b.id) as boolean) : b.selected,
          }));
        });
      })
      .catch(() => setBooks([]));
  }, []);

  // Load providers from API, fall back to hardcoded list
  useEffect(() => {
    fetchProviders()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setProviders(data);
          // Set default model to first model of first provider if current is unknown
          const allIds = data.flatMap((p) => p.models.map((m) => m.id));
          if (!allIds.includes(activeModel) && allIds.length > 0) {
            const rec = recommendedModelId(data);
            setActiveModel(allIds.includes(rec) ? rec : allIds[0]);
          }
        }
      })
      .catch(() => {
        // Keep fallback providers
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load conversations from API
  useEffect(() => {
    fetch("/api/conversations")
      .then((r) => r.json())
      .then((data: { conversations: RawConv[]; roadmaps?: typeof roadmaps }) => {
        const convList: RawConv[] = Array.isArray(data.conversations)
          ? data.conversations
          : Array.isArray(data)
          ? (data as unknown as RawConv[])
          : [];
        setConvGroups(groupConvsByDate(convList));
        if (data.roadmaps) setRoadmaps(data.roadmaps);
      })
      .catch(() => {
        setConvGroups({ today: [], yesterday: [], thisWeek: [], earlier: [] });
      });
  }, []);

  // Keyboard shortcut: Cmd/Ctrl+B → toggle books modal
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setBooksModalOpen((o) => !o);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Toggle a book's selected state
  const handleBookToggle = useCallback((id: string) => {
    setBooks((prev) =>
      prev.map((b) => (b.id === id ? { ...b, selected: !b.selected } : b)),
    );
  }, []);

  // Handle clarify card pick: select only the chosen book and re-send the
  // original user question (not a mode-id stub) so QA and other modes preserve
  // the actual question text. chapter/_sections are accepted but unused here —
  // book selection alone drives scoping on the re-send (confidence 1.0).
  const handleClarifyPick = useCallback(
    (slug: string, _chapter: string, _sections: string[]) => {
      setBooks((prev) => prev.map((b) => ({ ...b, selected: b.id === slug })));
      const lastUser = [...messages].reverse().find((m) => m.role === "user");
      // Pass the picked book explicitly: setBooks is async, so the re-send
      // would otherwise carry the stale (pre-pick) bookFilter and the backend
      // would re-clarify instead of advancing.
      if (lastUser?.text) handleSend(lastUser.text, [slug]);
    },
    [setBooks, messages, handleSend],
  );

  // Fork to temp chat
  const handleFork = useCallback((idx: number) => {
    setTempSeed(idx);
    setTempChatOpen(true);
  }, []);

  // Load an existing conversation when clicked in sidebar
  const handleSelectConv = useCallback(async (id: string) => {
    try {
      const r = await fetch(`/api/conversations/${id}`);
      if (!r.ok) return;
      const data = await r.json();
      // mapConversationMessages reads data.mode (the conversation-level mode,
      // e.g. "facilitate", "resume") and stamps it on every assistant message.
      // Previously this hardcoded "tutor", causing the wrong badge on reload.
      const msgs = mapConversationMessages(data);
      // Sync the picker once per conversation switch to its last-turn mode.
      // Re-selecting the same conversation (popstate / sidebar click) is a
      // no-op so a mid-conversation mode change by the user is never clobbered.
      if (lastSyncedConvRef.current !== id) {
        lastSyncedConvRef.current = id;
        const desiredMode = lastTurnMode(msgs, data.mode);
        setActiveMode((cur) => pickOpenedMode(desiredMode, STATRAG_MODES, cur));
      }
      loadConversation(id, msgs);
      // Update the URL so the conversation can be re-opened or shared
      // with a permalink like ``http://localhost:5175/c/<id>``.
      try {
        const desired = `/c/${id}`;
        if (window.location.pathname !== desired) {
          window.history.pushState({ convId: id }, "", desired);
        }
      } catch {
        // ignore — history API not available in some environments
      }
    } catch {
      // ignore
    }
  }, [loadConversation, setActiveMode]);

  // Delete a conversation: hit the API, prune local state, reset thread if
  // the deleted conv was active, and clear the deep-link URL when needed.
  const handleDeleteConv = useCallback(async (id: string) => {
    try {
      const r = await fetch(`/api/conversations/${id}`, { method: "DELETE" });
      if (!r.ok && r.status !== 204) return;
      setConvGroups((prev) => ({
        today: prev.today.filter((c) => c.id !== id),
        yesterday: prev.yesterday.filter((c) => c.id !== id),
        thisWeek: prev.thisWeek.filter((c) => c.id !== id),
        earlier: prev.earlier.filter((c) => c.id !== id),
      }));
      if (conversationId === id) {
        resetThread();
        try {
          if (window.location.pathname.startsWith(`/c/${id}`)) {
            window.history.pushState({}, "", "/");
          }
        } catch {
          // ignore
        }
      }
    } catch {
      // ignore network errors silently for now
    }
  }, [conversationId, resetThread]);

  // Deep-link: on first mount AND on browser back/forward, parse the URL and
  // auto-open the matching conversation. Supports both:
  //   /c/<id>            (canonical path form)
  //   /#/c/<id>          (hash form, useful when no server fallback exists)
  useEffect(() => {
    const parseConvId = (): string | null => {
      try {
        const path = window.location.pathname || "";
        const m1 = path.match(/^\/c\/([A-Za-z0-9_-]{8,64})\/?$/);
        if (m1) return m1[1];
        const hash = window.location.hash || "";
        const m2 = hash.match(/^#\/?c\/([A-Za-z0-9_-]{8,64})\/?$/);
        if (m2) return m2[1];
        return null;
      } catch {
        return null;
      }
    };

    const openFromUrl = () => {
      const id = parseConvId();
      if (id) handleSelectConv(id);
    };

    openFromUrl();
    const onPop = () => openFromUrl();
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [handleSelectConv]);

  const findConvTitle = (id: string | null | undefined): string | undefined => {
    if (!id) return undefined;
    for (const g of [convGroups.today, convGroups.yesterday, convGroups.thisWeek, convGroups.earlier]) {
      const hit = g.find((c) => c.id === id);
      if (hit) return hit.title;
    }
    return undefined;
  };
  const activeConvTitle =
    findConvTitle(conversationId) ??
    convGroups.today.find((c) => c.active)?.title ??
    convGroups.yesterday.find((c) => c.active)?.title ??
    "New conversation";

  const bookSnapshots = books.map((b) => ({ id: b.id, short: b.short }));

  const handleExportConversation = useCallback(async () => {
    if (messages.length === 0) return;
    const title = activeConvTitle.replace(/\s+/g, " ").trim();
    const slug = slugify(title);
    try {
      const md = conversationToMarkdown(messages, { title });
      const { blob } = await buildZipBlob(md, { docName: slug });
      downloadBlob(`statrag-${slug}.zip`, blob);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("[export] conversation zip failed", err);
    }
  }, [messages, activeConvTitle]);

  const handleExportMessage = useCallback(async (idx: number) => {
    const msg = messages[idx];
    if (!msg || msg.role !== "assistant") return;
    const title = activeConvTitle.replace(/\s+/g, " ").trim();
    const slug = slugify(title);
    // 1-based ordinal of this answer among assistant messages.
    let n = 0;
    for (let i = 0; i <= idx; i++) if (messages[i].role === "assistant") n++;
    const nn = String(n).padStart(2, "0");
    try {
      const md = assistantMessageToMarkdown(msg);
      const { blob } = await buildZipBlob(md, { docName: `${slug}-a${nn}` });
      downloadBlob(`statrag-${slug}-a${nn}.zip`, blob);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn("[export] answer zip failed", err);
    }
  }, [messages, activeConvTitle]);

  return (
    <div className="app">
      <Topbar
        activeConvTitle={activeConvTitle}
        books={books}
        online={online}
        theme={tweaks.theme}
        usage={usage}
        streamingPhase={streamingPhase}
        isStreaming={isStreaming}
        onToggleSidebar={() => setSidebarCollapsed((c) => !c)}
        onOpenBooks={() => setBooksModalOpen(true)}
        onOpenSettings={() => {
          /* settings modal — future */
        }}
        onToggleTheme={() => {
          const nextTheme = tweaks.theme === "dark" ? "light" : "dark";
          setTweak({ theme: nextTheme, accent: THEME_ACCENT_DEFAULTS[nextTheme] });
        }}
        onExportConversation={handleExportConversation}
        exportDisabled={messages.length === 0}
      />

      <div className="app__body">
        <Sidebar
          collapsed={sidebarCollapsed}
          convs={convGroups}
          roadmaps={roadmaps}
          onCollapseToggle={() => setSidebarCollapsed((c) => !c)}
          onNewConv={resetThread}
          onSelectConv={handleSelectConv}
          onDeleteConv={handleDeleteConv}
          activeId={conversationId ?? undefined}
          streamingIds={streamingIds}
        />

        <main className={`main${tempChatOpen ? " main--split" : ""}`}>
          <div className="main__pane main__pane--primary">
            <MessageThread
              thread={messages}
              conversationLoaded={!!conversationId}
              bubble={tweaks.userStyle === "bubble"}
              onClarifyPick={handleClarifyPick}
              onSourceClick={(chip) => {
                // Chip section is "chapter §section" concatenated (per orchestrator);
                // Source has chapter + section separate. Match by trying both.
                const src = sources.find((s) => {
                  if (s.book !== chip.book) return false;
                  const joined = `${s.chapter} ${s.section}`.trim();
                  return (
                    chip.section === joined ||
                    chip.section === s.section ||
                    chip.section.endsWith(s.section)
                  );
                });
                if (src) setOpenSource(src);
              }}
              onFork={handleFork}
              onExportMessage={handleExportMessage}
              forkDisabled={tempChatOpen}
              isStreaming={isStreaming}
              streamingPhase={streamingPhase}
              thinkingLabel={thinkingLabel}
            />
            <InputBar
              activeMode={activeMode}
              modes={STATRAG_MODES}
              onModeChange={(id) => setActiveMode(id)}
              onModeAbout={() => setAboutModelId(activeModel)}
              onModeAboutQA={() => setQaModalOpen(true)}
              onModeAboutFacilitate={() => setFacilitateModalOpen(true)}
              onModeAboutResume={() => setResumeModalOpen(true)}
              onModeAboutExtension={() => setExtensionModalOpen(true)}
              onSend={handleSend}
              isStreaming={isStreaming}
              onStop={() => stopStream()}
            />
          </div>

          {tempChatOpen && (
            <div className="main__pane main__pane--temp">
              <TempChat
                onClose={() => {
                  setTempChatOpen(false);
                  setTempSeed(null);
                }}
                seedFromMsg={tempSeed}
              />
            </div>
          )}
        </main>

        <ContextPanel
          sources={sources}
          figures={figures}
          figuresMeta={figuresMeta}
          metadata={metadata}
          collapsed={contextCollapsed}
          onToggle={() => setContextCollapsed((c) => !c)}
          onSourceClick={(s: Source) => setOpenSource(s)}
        />
      </div>

      <BookModal
        open={booksModalOpen}
        onClose={() => setBooksModalOpen(false)}
        books={books}
        onToggle={handleBookToggle}
      />

      <SourceModal
        open={openSource !== null}
        onClose={() => setOpenSource(null)}
        source={openSource}
        books={bookSnapshots}
      />

      <AboutModelModal
        open={aboutModelId !== null}
        modelId={aboutModelId}
        providers={providers}
        pickerModel={activeModel}
        recommendedModel={recommendedModel}
        stageModels={stageModels as Partial<Record<StageKey, string>>}
        diversityAuthors={diversityAuthors}
        onApply={(cfg) => {
          setStageModels(cfg.stageModels);
          setDiversityAuthors(cfg.diversityAuthors);
        }}
        onClose={() => setAboutModelId(null)}
      />

      <QAModeModal
        open={qaModalOpen}
        providers={providers}
        stageModels={stageModels}
        recommendedModel={recommendedModel}
        onApply={(cfg) => setStageModels((prev) => ({ ...prev, ...cfg.stageModels }))}
        onClose={() => setQaModalOpen(false)}
      />

      <ChapterFacilitateModal
        open={facilitateModalOpen}
        providers={providers}
        stageModels={stageModels}
        recommendedModel={recommendedModel}
        onApply={(cfg) => setStageModels((prev) => ({ ...prev, ...cfg.stageModels }))}
        onClose={() => setFacilitateModalOpen(false)}
      />

      <ChapterResumeModal
        open={resumeModalOpen}
        providers={providers}
        stageModels={stageModels}
        recommendedModel={recommendedModel}
        onApply={(cfg) => setStageModels((prev) => ({ ...prev, ...cfg.stageModels }))}
        onClose={() => setResumeModalOpen(false)}
      />

      <ExtensionModeModal
        open={extensionModalOpen}
        onClose={() => setExtensionModalOpen(false)}
      />

      {/* T21: settings moved into InputBar toolbar via SettingsPicker. */}
    </div>
  );
}
