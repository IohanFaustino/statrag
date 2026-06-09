import React from "react";
import type { Message, AssistantMessage as AssistantMsg, UserMessage as UserMsg, AssistantBlock, TutorAnswer, QAAnswer, ChapterDigest, ClarifyData, FacilitateDigest } from "../types";
import { MathBlock, MathInline } from "./Math";
import { normalizeMathDelimiters } from "./views/TutorView";
import TutorView from "./views/TutorView";
import QAAnswerCard from "./QAAnswerCard";
import ChapterDigestCard from "./ChapterDigestCard";
import FacilitateDigestCard from "./FacilitateDigestCard";
import ClarifyCard from "./ClarifyCard";
import ExtensionDigestCard, { ExtensionDigest } from "./ExtensionDigestCard";
import { IconBook, IconDownload } from "./Icons";

// ─── Mode icon map ────────────────────────────────────────────────────────────

type IconComponent = React.ComponentType<React.SVGProps<SVGSVGElement>>;

const MODE_ICONS: Record<string, IconComponent> = {
  tutor: IconBook,
  qa: IconBook,
};

const MODE_LABELS: Record<string, string> = {
  tutor: "Tutor",
  qa: "Q&A",
};

// ─── Inline renderer ──────────────────────────────────────────────────────────

type InlineNode =
  | { kind: "text"; content: string }
  | { kind: "math"; tex: string }
  | { kind: "bold"; content: string };

function parseInline(rawText: string): InlineNode[] {
  // Repair malformed delimiters emitted by the LLM before parsing.
  const text = normalizeMathDelimiters(rawText);
  const nodes: InlineNode[] = [];
  let i = 0;

  // Return the index of the next "special" char among $, \, or end-of-string.
  function nextSpecial(from: number): number {
    for (let k = from; k < text.length; k++) {
      if (text[k] === "$" || text[k] === "\\") return k;
    }
    return text.length;
  }

  function flushTextChunk(chunk: string): void {
    // Expand **bold** within a plain text chunk.
    const boldRe = /\*\*([^*]+)\*\*/g;
    let last = 0;
    let m: RegExpExecArray | null;
    while ((m = boldRe.exec(chunk)) !== null) {
      if (m.index > last) nodes.push({ kind: "text", content: chunk.slice(last, m.index) });
      nodes.push({ kind: "bold", content: m[1] });
      last = m.index + m[0].length;
    }
    if (last < chunk.length) nodes.push({ kind: "text", content: chunk.slice(last) });
  }

  while (i < text.length) {
    // ── $…$ inline math
    if (text[i] === "$") {
      const end = text.indexOf("$", i + 1);
      if (end === -1) {
        nodes.push({ kind: "text", content: text.slice(i) });
        break;
      }
      nodes.push({ kind: "math", tex: text.slice(i + 1, end) });
      i = end + 1;
      continue;
    }
    // ── \(…\) inline math
    if (text[i] === "\\" && text[i + 1] === "(") {
      const end = text.indexOf("\\)", i + 2);
      if (end !== -1) {
        nodes.push({ kind: "math", tex: text.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    // ── \[…\] single-line display math (treated as inline here)
    if (text[i] === "\\" && text[i + 1] === "[") {
      const end = text.indexOf("\\]", i + 2);
      if (end !== -1) {
        nodes.push({ kind: "math", tex: text.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    // ── Plain text run up to the next special char
    const special = nextSpecial(i + 1);
    flushTextChunk(text.slice(i, special));
    i = special;
  }
  return nodes;
}

function renderInline(text: string): React.ReactNode[] {
  return parseInline(text).map((node, idx) => {
    if (node.kind === "math") return <MathInline key={idx} tex={node.tex} />;
    if (node.kind === "bold") return <strong key={idx} className="msg__strong">{node.content}</strong>;
    return <React.Fragment key={idx}>{node.content}</React.Fragment>;
  });
}

// ─── Source chip ──────────────────────────────────────────────────────────────

interface ChipData { book: string; section: string }

function SourceChip({
  chip,
  onOpen,
}: {
  chip: ChipData;
  onOpen?: (chip: ChipData) => void;
}) {
  const bookKey = chip.book.toLowerCase();
  const label = chip.book === "HANSEN" ? "Hansen" : chip.book;
  return (
    <button
      className="src-chip"
      type="button"
      onClick={() => onOpen?.(chip)}
      aria-label={`${label} ${chip.section} — open source`}
    >
      <span className={`dot dot--${bookKey}`} />
      <span className="src-chip__book">{label}</span>
      <span className="src-chip__sec">{chip.section}</span>
    </button>
  );
}

// ─── Inline figure ────────────────────────────────────────────────────────────

function InlineFigure({ block }: { block: Extract<AssistantBlock, { type: "figure" }> }) {
  return (
    <figure className="inline-fig">
      <div className="inline-fig__frame">
        {block.chart && (block.chart.startsWith("/") || block.chart.startsWith("http")) ? (
          <img
            src={block.chart}
            alt={block.caption}
            loading="lazy"
            style={{ maxWidth: "100%", maxHeight: "240px", objectFit: "contain" }}
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
          />
        ) : (
          <svg viewBox="0 0 160 90" width="160" height="90" aria-label={block.caption}>
            <rect x="1" y="1" width="158" height="88" fill="none" stroke="rgba(229,72,77,0.2)" strokeWidth="1" />
            <text x="80" y="50" textAnchor="middle" fill="rgba(229,72,77,0.45)" fontSize="10" fontFamily="IBM Plex Mono, monospace">
              {block.chart || "no preview"}
            </text>
          </svg>
        )}
      </div>
      <figcaption className="inline-fig__cap">
        <span className="inline-fig__tag">
          <span className="dot dot--figure" />
          {block.book} · {block.chapter} · {block.ref}
        </span>
        <span className="inline-fig__text">{block.caption}</span>
      </figcaption>
    </figure>
  );
}

// ─── Streaming placeholder ────────────────────────────────────────────────────

function StreamingDots() {
  return (
    <div className="thread__streaming">
      <span className="thread__streaming-dot" />
      <span className="thread__streaming-dot" />
      <span className="thread__streaming-dot" />
      <span className="thread__streaming-hint">Continue the conversation below</span>
    </div>
  );
}

// ─── User message ─────────────────────────────────────────────────────────────

function UserMessageView({ msg, bubble }: { msg: UserMsg; bubble: boolean }) {
  if (bubble) {
    return (
      <div className="msg msg--user-bubble">
        <div className="user-bubble">
          <p>{msg.text}</p>
        </div>
        <div className="user-meta">[you] · {msg.time}</div>
      </div>
    );
  }
  return (
    <div className="msg msg--user-doc">
      <div className="user-doc">
        <div className="user-doc__rail" />
        <div className="user-doc__body">
          <div className="user-doc__meta">YOU · {msg.time}</div>
          <p>{msg.text}</p>
        </div>
      </div>
    </div>
  );
}

// ─── Assistant message ────────────────────────────────────────────────────────

interface AssistantMessageViewProps {
  msg: AssistantMsg;
  idx: number;
  onSourceClick?: (chip: ChipData) => void;
  onFork?: (idx: number) => void;
  forkDisabled?: boolean;
  onExport?: (idx: number) => void;
  streamingPhase?: "idle" | "thinking" | "writing";
  isLast?: boolean;
  onClarifyPick?: (slug: string, chapter: string, sections: string[]) => void;
  thinkingLabel?: string;
}

const STRUCTURED_MODES = new Set(["tutor", "qa", "facilitate", "resume"]);

function AssistantMessageView({
  msg,
  idx,
  onSourceClick,
  onFork,
  forkDisabled,
  onExport,
  streamingPhase,
  isLast,
  onClarifyPick,
  thinkingLabel = "Thinking",
}: AssistantMessageViewProps) {
  const ModeIcon = MODE_ICONS[msg.mode];
  const modeLabel = MODE_LABELS[msg.mode] ?? msg.mode;

  const isPending = msg.status === "pending";
  const isStreaming = msg.status === "streaming";
  const isError = msg.status === "error";
  // While a structured-output mode is still streaming raw JSON tokens,
  // hide raw paragraphs so the user does not see prose-JSON before the
  // structured view replaces them.
  const hideRawWhileFormatting =
    isLast &&
    isStreaming &&
    !msg.structuredOutput &&
    STRUCTURED_MODES.has(msg.mode);

  const booksDisplay = msg.books
    .map((b) => (b === "HANSEN" ? "Hansen" : b))
    .join(" + ");

  return (
    <article className="msg msg--assistant">
      <div className="msg__badge">
        {ModeIcon && (
          <span className="msg__badge-icon" aria-hidden="true">
            <ModeIcon width={12} height={12} />
          </span>
        )}
        <span className="msg__badge-mode" aria-live="polite">
          {modeLabel.toUpperCase()} MODE
        </span>
        {msg.books.length > 0 && (
          <>
            <span className="msg__badge-sep">·</span>
            <span className="msg__badge-books">{booksDisplay}</span>
          </>
        )}
        {msg.sourceCount > 0 && (
          <>
            <span className="msg__badge-sep">·</span>
            <span className="msg__badge-count">{msg.sourceCount} sources</span>
          </>
        )}
        {msg.latencyMs > 0 && (
          <>
            <span className="msg__badge-sep">·</span>
            <span className="msg__badge-lat">{(msg.latencyMs / 1000).toFixed(1)}s</span>
          </>
        )}
      </div>

      <div className="msg__body">
        {(isPending || (isLast && isStreaming && streamingPhase === "thinking")) && (
          <div className="msg__thinking" aria-live="polite">
            <span className="msg__thinking-lbl">{thinkingLabel}</span>
            <span className="msg__thinking-ell" aria-hidden="true">
              <span>.</span><span>.</span><span>.</span>
            </span>
          </div>
        )}

        {hideRawWhileFormatting && (
          <div className="msg__formatting">
            <span className="msg__formatting-bar" />
            <span className="msg__formatting-lbl">Formatting response…</span>
          </div>
        )}

        {isError && msg.error && (
          <div className="msg__error">
            <span className="msg__error-code">{msg.error.code}</span>
            <span className="msg__error-msg">{msg.error.message}</span>
          </div>
        )}

        {/* T22 (E2/E3): when a structured TutorAnswer is present the raw
            token stream is itself JSON — hide it and let TutorView render
            instead. Same applies to every other structured mode that has
            its own view component below. */}
        {!msg.structuredOutput && !hideRawWhileFormatting && msg.blocks.map((block: AssistantBlock, i: number) => {
          if (block.type === "p") {
            if (!block.text) return null;
            const isLastBlock = i === msg.blocks.length - 1;
            const showCaret = isLast && isStreaming && isLastBlock && streamingPhase === "writing";
            return (
              <p key={i} className="msg__p">
                {renderInline(block.text)}
                {showCaret && <span className="msg__caret" aria-hidden="true" />}
              </p>
            );
          }
          if (block.type === "math") {
            return <MathBlock key={i} tex={block.tex} />;
          }
          if (block.type === "figure") {
            return <InlineFigure key={i} block={block} />;
          }
          if (block.type === "sources") {
            return (
              <div key={i} className="msg__src-row">
                {block.chips.map((chip, j) => (
                  <SourceChip key={j} chip={chip} onOpen={onSourceClick} />
                ))}
              </div>
            );
          }
          return null;
        })}

        {msg.structuredOutput && (
          <div className="msg__structured">
            {msg.structuredOutput.schema === "TutorAnswer" && (
              <TutorView data={msg.structuredOutput.data as TutorAnswer} />
            )}
            {msg.structuredOutput.schema === "QAAnswer" && (
              <QAAnswerCard answer={msg.structuredOutput.data as QAAnswer} />
            )}
            {msg.structuredOutput.schema === "ChapterDigest" && (
              <ChapterDigestCard digest={msg.structuredOutput.data as ChapterDigest} />
            )}
            {msg.structuredOutput.schema === "FacilitateDigest" && (
              <FacilitateDigestCard digest={msg.structuredOutput.data as FacilitateDigest} />
            )}
            {msg.structuredOutput.schema === "ExtensionDigest" && (
              <ExtensionDigestCard
                digest={msg.structuredOutput.data as ExtensionDigest}
                pendingPoints={msg.pendingExtensionPoints}
              />
            )}
            {msg.structuredOutput.schema === "Clarify" && (
              <ClarifyCard
                data={msg.structuredOutput.data as ClarifyData}
                onPick={onClarifyPick ?? (() => {})}
              />
            )}
          </div>
        )}

        {!msg.structuredOutput && (msg.pendingExtensionPoints?.length ?? 0) > 0 && (
          <div className="extension-card extension-card--streaming">
            {msg.pendingExtensionPoints!.map((title, i) => (
              <section key={i} className="extension-point extension-point--skeleton">
                <h3 className="extension-point__title">{title}</h3>
                <div className="extension-point__body extension-point__body--loading" />
              </section>
            ))}
          </div>
        )}

        {msg.stopped && <div className="msg__stopped" role="status">Stopped</div>}
      </div>

      {onExport && msg.status === "complete" && (
        <button
          className="msg__export"
          type="button"
          onClick={() => onExport(idx)}
          title="Export this answer (.md)"
          aria-label="Export this answer as Markdown"
        >
          <IconDownload width={14} height={14} />
        </button>
      )}
      {!forkDisabled && (
        <button
          className="msg__fork"
          type="button"
          onClick={() => onFork?.(idx)}
          title="Open in temporary chat"
          aria-label="Open in temporary chat"
        >
          <svg
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          >
            <path d="M8 3.5v9M3.5 8h9" />
          </svg>
        </button>
      )}
    </article>
  );
}

// ─── Message thread ───────────────────────────────────────────────────────────

export interface MessageThreadProps {
  thread: Message[];
  bubble?: boolean;
  onSourceClick?: (chip: ChipData) => void;
  onFork?: (idx: number) => void;
  forkDisabled?: boolean;
  onExportMessage?: (idx: number) => void;
  isStreaming?: boolean;
  streamingPhase?: "idle" | "thinking" | "writing";
  thinkingLabel?: string;
  conversationLoaded?: boolean;
  onClarifyPick?: (slug: string, chapter: string, sections: string[]) => void;
}

function getDayLabel(): string {
  const now = new Date();
  return now.toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MessageThread({
  thread,
  bubble = true,
  onSourceClick,
  onFork,
  forkDisabled = false,
  onExportMessage,
  isStreaming = false,
  streamingPhase = "idle",
  thinkingLabel = "Thinking",
  conversationLoaded = false,
  onClarifyPick,
}: MessageThreadProps) {
  const dayLabel = getDayLabel();

  // Empty state
  if (thread.length === 0) {
    return (
      <div className="thread thread--empty">
        <div className="thread__inner">
          <div className="thread__empty-state">
            <div className="thread__empty-glyph" aria-hidden="true">∑</div>
            <h2 className="thread__empty-title">statrag</h2>
            {conversationLoaded ? (
              <>
                <p className="thread__empty-sub">No messages in this conversation yet.</p>
                <div className="thread__empty-hint">Send a message below to continue.</div>
              </>
            ) : (
              <>
                <p className="thread__empty-sub">What do you want to understand?</p>
                <div className="thread__empty-hint">
                  Press <kbd>⌘K</kbd> to switch modes
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="thread">
      <div className="thread__inner">
        <div className="thread__day" role="separator" aria-label={`Conversation started ${dayLabel}`}>
          <span className="thread__day-line" aria-hidden="true" />
          <span className="thread__day-label">Today · {dayLabel}</span>
          <span className="thread__day-line" aria-hidden="true" />
        </div>

        {thread.map((msg, i) =>
          msg.role === "user" ? (
            <UserMessageView key={msg.id} msg={msg} bubble={bubble} />
          ) : (
            <AssistantMessageView
              key={msg.id}
              msg={msg}
              idx={i}
              onSourceClick={onSourceClick}
              onFork={onFork}
              onExport={onExportMessage}
              forkDisabled={forkDisabled}
              streamingPhase={streamingPhase}
              thinkingLabel={thinkingLabel}
              isLast={i === thread.length - 1}
              onClarifyPick={onClarifyPick}
            />
          ),
        )}

        {!isStreaming && <StreamingDots />}
      </div>
    </div>
  );
}
