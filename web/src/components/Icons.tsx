// Minimal stroke-based icon set. 16px viewBox, stroke 1.4, currentColor.
// Ported 1:1 from icons.jsx.

import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const base: IconProps = {
  viewBox: "0 0 16 16",
  width: 16,
  height: 16,
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.4,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function IconBook(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="M3 2.5h7a2 2 0 0 1 2 2v9H5a2 2 0 0 1-2-2v-9Z" />
      <path d="M3 11.5a2 2 0 0 1 2-2h7" />
    </svg>
  );
}

export function IconMath(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="M11.5 3h-7l3.5 5-3.5 5h7" />
    </svg>
  );
}

export function IconPlus(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="M8 3.5v9M3.5 8h9" />
    </svg>
  );
}

export function IconBolt(p: IconProps) {
  return (
    <svg {...base} {...p} strokeWidth={1.3}>
      <path d="M8 2.5v3M8 10.5v3M2.5 8h3M10.5 8h3M4 4l2 2M10 10l2 2M12 4l-2 2M4 12l2-2" />
    </svg>
  );
}

export function IconSend(p: IconProps) {
  return (
    <svg {...base} {...p} strokeWidth={1.6}>
      <path d="M8 13V3M4 7l4-4 4 4" />
    </svg>
  );
}

export function IconAttach(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="M11 7 6.5 11.5a2 2 0 1 1-2.8-2.8L9 3.4a3 3 0 0 1 4.2 4.2L8 13" />
    </svg>
  );
}

export function IconChevron(p: IconProps) {
  // Default: down (caret)
  return (
    <svg {...base} {...p}>
      <path d="m5 6.5 3 3 3-3" />
    </svg>
  );
}

export function IconChevronRight(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="m6 4 4 4-4 4" />
    </svg>
  );
}

export function IconChevronLeft(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="m10 4-4 4 4 4" />
    </svg>
  );
}

export function IconArrowDown(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="M8 3v10M4 9l4 4 4-4" />
    </svg>
  );
}

export function IconClose(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  );
}

export function IconWrench(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="M10.5 2.2a3.3 3.3 0 0 0-3 5.05L2.4 12.35a1.2 1.2 0 0 0 1.7 1.7l5.1-5.1a3.3 3.3 0 0 0 4.3-4.3l-1.95 1.95-1.7-1.7L11.8 2.95A3.3 3.3 0 0 0 10.5 2.2Z" />
    </svg>
  );
}

export function IconGear(p: IconProps) {
  return (
    <svg {...base} {...p} strokeWidth={1.3}>
      <circle cx="8" cy="8" r="2" />
      <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.5 3.5 5 5M11 11l1.5 1.5M12.5 3.5 11 5M5 11l-1.5 1.5" />
    </svg>
  );
}

export function IconDots(p: IconProps) {
  return (
    <svg viewBox="0 0 16 16" width={16} height={16} fill="currentColor" {...p}>
      <circle cx="3.5" cy="8" r="1.2" />
      <circle cx="8" cy="8" r="1.2" />
      <circle cx="12.5" cy="8" r="1.2" />
    </svg>
  );
}

export function IconCheck(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="M3 8l3.5 3.5 6.5-7" />
    </svg>
  );
}

export function IconMode(p: IconProps) {
  // Generic mode icon — uses book shape
  return <IconBook {...p} />;
}

export function IconModel(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 5v3l2 2" />
    </svg>
  );
}

export function IconDownload(p: IconProps) {
  return (
    <svg {...base} {...p}>
      <path d="M8 2.5v8" />
      <path d="M4.5 7 8 10.5 11.5 7" />
      <path d="M3 13h10" />
    </svg>
  );
}

// Logo icon variant (open-book) — used in topbar BooksButton
export function IconLogo(p: IconProps) {
  return (
    <svg {...base} {...p} width={14} height={14}>
      <path d="M3 2.5h4.5a2 2 0 0 1 2 2v9" />
      <path d="M13 2.5H8.5a2 2 0 0 0-2 2v9" />
      <path d="M3 11.5h4.5a2 2 0 0 1 2 2" />
      <path d="M13 11.5H8.5a2 2 0 0 0-2 2" />
    </svg>
  );
}

// Hamburger / menu icon
export function IconMenu(p: IconProps) {
  return (
    <svg {...base} {...p} width={14} height={14}>
      <path d="M2.5 4h11M2.5 8h11M2.5 12h11" />
    </svg>
  );
}

// Sun icon (shown when theme=dark, click → light)
export function IconSun(p: IconProps) {
  return (
    <svg {...base} {...p} width={14} height={14}>
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.5v1.5M8 13v1.5M1.5 8h1.5M13 8h1.5M3.5 3.5l1 1M11.5 11.5l1 1M12.5 3.5l-1 1M4.5 11.5l-1 1" />
    </svg>
  );
}

// Moon icon (shown when theme=light, click → dark)
export function IconMoon(p: IconProps) {
  return (
    <svg {...base} {...p} width={14} height={14}>
      <path d="M13.5 9.2A5.5 5.5 0 0 1 6.8 2.5a5.5 5.5 0 1 0 6.7 6.7Z" />
    </svg>
  );
}

// Sigma — math mode
export function IconSigma(p: IconProps) {
  return <IconMath {...p} />;
}

// Spark (for new-conv button)
export function IconSpark(p: IconProps) {
  return <IconBolt {...p} />;
}
