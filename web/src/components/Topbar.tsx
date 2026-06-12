import React from "react";
import type { Book } from "../types";
import { IconMenu, IconLogo, IconSun, IconMoon, IconGear, IconBook, IconDownload } from "./Icons";

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
  onExportConversation?(): void;
  exportDisabled?: boolean;
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
  onExportConversation,
  exportDisabled,
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

      <div className="topbar__center" />

      <div className="topbar__right">
        <BooksButton books={books} onClick={onOpenBooks} />
        <div className="topbar__divider" />
        {onExportConversation && (
          <button
            className="icon-btn icon-btn--export"
            onClick={onExportConversation}
            disabled={exportDisabled}
            aria-label="Export conversation as Markdown"
            title="Export conversation (.md)"
            type="button"
          >
            <IconDownload />
          </button>
        )}
        <button
          className="icon-btn icon-btn--appr"
          onClick={onOpenSettings}
          aria-label="Appearance"
          title="Appearance — colors"
          type="button"
        >
          <IconGear />
        </button>
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
