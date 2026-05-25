import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

// Discrete choice value: a number, the "auto" sentinel, or any string token.
export type ChoiceValue = number | "auto" | string;

export interface ChoiceOption {
  label: string;
  value: ChoiceValue;
}

interface NodeChoiceDropdownProps {
  value: ChoiceValue;
  options: ChoiceOption[];
  onSelect(value: ChoiceValue): void;
  ariaLabel?: string;
}

// A choice control styled identically to NodeModelDropdown (same .node-dd*
// classes, same portal + flip-up + max-height positioning logic) but for a
// flat list of discrete values rather than grouped model lists.
export default function NodeChoiceDropdown({
  value,
  options,
  onSelect,
  ariaLabel = "Select option",
}: NodeChoiceDropdownProps) {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<{
    left: number;
    top: number | undefined;
    bottom: number | undefined;
    width: number;
    maxHeight: number;
  } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const curOption = options.find((o) => o.value === value) ?? options[0];

  // Anchor the floating panel under (or above) the button — identical flip/
  // clamp logic as NodeModelDropdown so behavior is predictably consistent.
  useEffect(() => {
    if (!open) return;

    const PANEL_CAP = 280;
    const MARGIN = 8;

    const reposition = () => {
      if (!btnRef.current) return;
      requestAnimationFrame(() => {
        if (!btnRef.current) return;
        const r = btnRef.current.getBoundingClientRect();
        const vh = window.innerHeight;

        const spaceBelow = vh - r.bottom - MARGIN;
        const spaceAbove = r.top - MARGIN;

        if (spaceBelow >= 100 || spaceBelow >= spaceAbove) {
          const maxHeight = Math.min(PANEL_CAP, Math.max(spaceBelow, 60));
          setRect({ left: r.left, top: r.bottom + 4, bottom: undefined, width: r.width, maxHeight });
        } else {
          const maxHeight = Math.min(PANEL_CAP, Math.max(spaceAbove, 60));
          setRect({ left: r.left, top: undefined, bottom: vh - r.top + 4, width: r.width, maxHeight });
        }
      });
    };

    reposition();
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [open]);

  // Close on outside-click + Esc.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const t = e.target as Node;
      if (
        btnRef.current && !btnRef.current.contains(t) &&
        panelRef.current && !panelRef.current.contains(t)
      ) setOpen(false);
    }
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setOpen(false); }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="node-dd__toggle"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${ariaLabel}: ${curOption?.label ?? value}. Click to change.`}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="node-dd__name">{curOption?.label ?? String(value)}</span>
        <svg
          className="node-dd__chev"
          viewBox="0 0 16 16"
          width="11"
          height="11"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          aria-hidden="true"
        >
          <path d="m4 6 4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && rect && createPortal(
        <div
          ref={panelRef}
          className="node-dd__panel"
          role="listbox"
          aria-label={ariaLabel}
          style={{
            position: "fixed",
            left: rect.left,
            ...(rect.top !== undefined ? { top: rect.top } : {}),
            ...(rect.bottom !== undefined ? { bottom: rect.bottom } : {}),
            minWidth: Math.max(rect.width, 160),
            maxHeight: rect.maxHeight,
            overflowY: "auto",
          }}
        >
          {options.map((opt) => {
            const active = opt.value === value;
            return (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={active}
                className={"node-dd__row" + (active ? " is-active" : "")}
                onClick={() => { onSelect(opt.value); setOpen(false); }}
              >
                <span className="node-dd__row-name">{opt.label}</span>
                {active && (
                  <svg
                    viewBox="0 0 16 16"
                    width="11"
                    height="11"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="m3 8 4 4 6-8" />
                  </svg>
                )}
              </button>
            );
          })}
        </div>,
        document.body,
      )}
    </>
  );
}
