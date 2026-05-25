import React from "react";
import {
  IconPlus,
  IconSpark,
  IconGear,
  IconChevronLeft,
} from "./Icons";

export interface ConvDigest {
  id: string;
  title: string;
  mode: string;
  active?: boolean;
}

interface RoadmapItem {
  id: string;
  title: string;
  scenes: number;
  date: string;
}

interface SidebarProps {
  collapsed: boolean;
  convs: {
    today: ConvDigest[];
    yesterday: ConvDigest[];
    thisWeek: ConvDigest[];
    earlier: ConvDigest[];
  };
  roadmaps: RoadmapItem[];
  onCollapseToggle(): void;
  onNewConv(): void;
  onSelectConv?(id: string): void;
  onDeleteConv?(id: string): void;
  activeId?: string;
  // Conversation ids whose detached run is still streaming (§13).
  streamingIds?: string[];
}

function ConvItem({
  conv,
  onSelect,
  onDelete,
  isActive,
  streaming,
}: {
  conv: ConvDigest;
  onSelect?: (id: string) => void;
  onDelete?: (id: string) => void;
  isActive: boolean;
  streaming?: boolean;
}) {
  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    const ok = window.confirm(`Delete conversation "${conv.title}"? This cannot be undone.`);
    if (ok) onDelete?.(conv.id);
  };
  return (
    <div className={"conv-item-row" + (isActive ? " is-active" : "")}>
      <button
        className={"conv-item" + (isActive ? " is-active" : "")}
        type="button"
        onClick={() => onSelect?.(conv.id)}
      >
        <span className="conv-item__title">{conv.title}</span>
        {streaming ? (
          <span
            className="conv-item__streaming"
            aria-label="still generating"
            title="Still generating in the background"
          />
        ) : (
          <span className="conv-item__mode" aria-hidden="true" />
        )}
      </button>
      {onDelete && (
        <button
          className="conv-item__delete"
          type="button"
          title="Delete conversation"
          aria-label={`Delete conversation: ${conv.title}`}
          onClick={handleDelete}
        >
          ×
        </button>
      )}
    </div>
  );
}

const CONV_GROUPS = [
  { label: "Today", key: "today" as const },
  { label: "Yesterday", key: "yesterday" as const },
  { label: "This week", key: "thisWeek" as const },
  { label: "Earlier", key: "earlier" as const },
];

export default function Sidebar({
  collapsed,
  convs,
  roadmaps,
  onCollapseToggle,
  onNewConv,
  onSelectConv,
  onDeleteConv,
  activeId,
  streamingIds,
}: SidebarProps) {
  const streamingSet = new Set(streamingIds ?? []);
  if (collapsed) {
    const totalToday = convs.today.length;
    const totalYesterday = convs.yesterday.length;
    const totalThisWeek = convs.thisWeek.length;

    return (
      <aside className="sidebar sidebar--collapsed">
        <button
          className="rail-btn rail-btn--new"
          onClick={onNewConv}
          type="button"
          title="New conversation"
          aria-label="New conversation"
        >
          <IconPlus />
        </button>
        <div className="rail-divider" />
        {totalToday > 0 && (
          <button className="rail-btn" type="button" title="Today">
            <span className="rail-badge">{totalToday}</span>
          </button>
        )}
        {totalYesterday > 0 && (
          <button className="rail-btn" type="button" title="Yesterday">
            <span className="rail-badge">{totalYesterday}</span>
          </button>
        )}
        {totalThisWeek > 0 && (
          <button className="rail-btn" type="button" title="This week">
            <span className="rail-badge">{totalThisWeek}</span>
          </button>
        )}
        <div style={{ flex: 1 }} />
        <button
          className="rail-btn"
          onClick={onCollapseToggle}
          type="button"
          title="Expand sidebar"
          aria-label="Expand sidebar"
        >
          <IconGear />
        </button>
      </aside>
    );
  }

  return (
    <aside className="sidebar">
      <button className="new-conv" onClick={onNewConv} type="button">
        <IconPlus />
        <span>New conversation</span>
        <span className="new-conv__spark" aria-hidden="true">
          <IconSpark />
        </span>
      </button>

      <div className="sidebar__scroll">
        {CONV_GROUPS.map((g) => {
          const items = convs[g.key];
          if (items.length === 0) return null;
          return (
            <div className="sb-group" key={g.label}>
              <div className="sb-group__label">{g.label}</div>
              <div className="sb-group__list">
                {items.map((c) => (
                  <ConvItem
                    key={c.id}
                    conv={c}
                    onSelect={onSelectConv}
                    onDelete={onDeleteConv}
                    isActive={activeId ? c.id === activeId : !!c.active}
                    streaming={streamingSet.has(c.id)}
                  />
                ))}
              </div>
            </div>
          );
        })}

        {roadmaps.length > 0 && (
          <>
            <div className="sb-divider" />
            <div className="sb-group">
              <div className="sb-group__label sb-group__label--ts">
                Roadmaps
              </div>
              <div className="sb-group__list">
                {roadmaps.map((r) => (
                  <button key={r.id} className="roadmap-item" type="button">
                    <span className="roadmap-item__title">{r.title}</span>
                    <span className="roadmap-item__meta">
                      <span className="roadmap-item__scenes">
                        {r.scenes} scenes
                      </span>
                      <span className="roadmap-item__date">{r.date}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      <button
        className="sb-collapse"
        onClick={onCollapseToggle}
        type="button"
        title="Collapse sidebar"
        aria-label="Collapse sidebar"
      >
        <IconChevronLeft />
      </button>
    </aside>
  );
}
