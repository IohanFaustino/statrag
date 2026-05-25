import { useEffect, type ReactNode } from "react";

type ModalSize = "default" | "md" | "lg";

interface FocusModalProps {
  open: boolean;
  onClose(): void;
  size?: ModalSize;
  children: ReactNode;
  labelledBy?: string;
  panelClassName?: string;
}

export default function FocusModal({
  open,
  onClose,
  size = "default",
  children,
  labelledBy,
  panelClassName,
}: FocusModalProps) {
  // Esc to close + body scroll lock
  useEffect(() => {
    if (!open) return;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
    >
      <div
        className={`fm__panel fm__panel--${size}${panelClassName ? " " + panelClassName : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
