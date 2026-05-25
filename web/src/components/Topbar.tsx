import React from "react";
import type { Book } from "../types";
import { IconMenu, IconLogo, IconSun, IconMoon, IconGear, IconBook } from "./Icons";

interface UsageStats {
  durationMs: number;
  promptChars: number;
  completionChars: number;
  estTokens: number;
}

interface TopbarProps {
  activeConvTitle: string;
  books: Book[];
  online: boolean;
  theme: "dark" | "light";
  usage?: UsageStats | null;
  streamingPhase?: "idle" | "thinking" | "writing";
  isStreaming?: boolean;
  onToggleSidebar(): void;
  onOpenBooks(): void;
  onOpenSettings(): void;
  onToggleTheme(): void;
}

function StatsPill({
  usage,
  streamingPhase,
  isStreaming,
}: {
  usage?: UsageStats | null;
  streamingPhase?: "idle" | "thinking" | "writing";
  isStreaming?: boolean;
}) {
  const [tick, setTick] = React.useState(0);
  const startRef = React.useRef<number | null>(null);
  React.useEffect(() => {
    if (isStreaming) {
      if (startRef.current == null) startRef.current = performance.now();
      const id = window.setInterval(() => setTick((t) => t + 1), 200);
      return () => window.clearInterval(id);
    }
    startRef.current = null;
    return undefined;
  }, [isStreaming]);

  let durationLabel = "—";
  let tokensLabel = "—";
  let phaseLabel = "idle";

  if (isStreaming && startRef.current != null) {
    const ms = performance.now() - startRef.current;
    durationLabel = (ms / 1000).toFixed(1) + "s";
    phaseLabel = streamingPhase === "writing" ? "writing" : "thinking";
    tokensLabel = "…";
    void tick;
  } else if (usage) {
    durationLabel = (usage.durationMs / 1000).toFixed(1) + "s";
    tokensLabel = `${usage.estTokens}`;
    phaseLabel = "done";
  }

  const live = isStreaming;
  return (
    <div className={"stats-pill" + (live ? " stats-pill--live" : "")} title="Session stats">
      <span className={"stats-pill__dot stats-pill__dot--" + phaseLabel} aria-hidden="true" />
      <span className="stats-pill__lbl">{phaseLabel}</span>
      <span className="stats-pill__sep">·</span>
      <span className="stats-pill__val">{durationLabel}</span>
      <span className="stats-pill__sep">·</span>
      <span className="stats-pill__val">{tokensLabel} tok</span>
    </div>
  );
}

function BooksButton({
  books,
  onClick,
}: {
  books: Book[];
  onClick(): void;
}) {
  const indexed = books.filter((b) => b.indexed !== false);
  const selected = books.filter((b) => b.selected && b.indexed !== false);
  const allSelected = selected.length === indexed.length && indexed.length > 0;

  return (
    <button className="books-btn" onClick={onClick} type="button">
      <span className="books-btn__icon" aria-hidden="true">
        <IconBook />
      </span>
      <span className="books-btn__lbl">Books</span>
      <span className="books-btn__divider" />
      <span className="books-btn__chips">
        {allSelected ? (
          <span className="books-btn__all">ALL</span>
        ) : selected.length === 0 ? (
          <span className="books-btn__none">none</span>
        ) : (
          selected.map((b) => (
            <span key={b.id} className="books-btn__chip">
              <span className="dot" style={{ background: b.color }} />
              {b.short}
            </span>
          ))
        )}
      </span>
      <span className="books-btn__count">
        {selected.length}/{indexed.length}
      </span>
    </button>
  );
}

export default function Topbar({
  activeConvTitle,
  books,
  online,
  theme,
  usage,
  streamingPhase,
  isStreaming,
  onToggleSidebar,
  onOpenBooks,
  onOpenSettings,
  onToggleTheme,
}: TopbarProps) {
  return (
    <header className="topbar">
      <div className="topbar__left">
        <button
          className="topbar__menu"
          onClick={onToggleSidebar}
          aria-label="Toggle sidebar"
          type="button"
        >
          <IconMenu />
        </button>
        <div className="logo">
          <span className="logo__mark" aria-hidden="true">∑</span>
          <span className="logo__word">statrag</span>
        </div>
      </div>

      <div className="topbar__center">
        <div className="topbar__breadcrumb">
          <span className="topbar__crumb-dim">Today</span>
          <span className="topbar__crumb-sep">/</span>
          <span className="topbar__crumb-title">{activeConvTitle}</span>
        </div>
        <StatsPill usage={usage} streamingPhase={streamingPhase} isStreaming={isStreaming} />
      </div>

      <div className="topbar__right">
        <BooksButton books={books} onClick={onOpenBooks} />
        <div className="topbar__divider" />
        <button
          className={"icon-btn icon-btn--theme"}
          onClick={onToggleTheme}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          title={`${theme === "dark" ? "Light" : "Dark"} mode`}
          type="button"
        >
          {theme === "dark" ? <IconSun /> : <IconMoon />}
        </button>
      </div>
    </header>
  );
}
