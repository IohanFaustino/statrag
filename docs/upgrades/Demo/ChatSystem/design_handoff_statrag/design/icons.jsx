// Minimal stroke-based icon set. 16px viewBox unless noted.

const Ic = {
  book: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M3 2.5h7a2 2 0 0 1 2 2v9H5a2 2 0 0 1-2-2v-9Z"/><path d="M3 11.5a2 2 0 0 1 2-2h7"/></svg>,
  compare: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M4 2.5v11M12 2.5v11"/><path d="M4 5.5h2M12 5.5h-2M4 10.5h2M12 10.5h-2"/></svg>,
  image: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="2.5" y="3" width="11" height="10" rx="1.5"/><circle cx="6" cy="6.5" r="1"/><path d="m3 12 3-3 2.5 2.5L11 8l2 2"/></svg>,
  quiz: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="8" cy="8" r="5.5"/><path d="M6.5 6.5a1.5 1.5 0 1 1 2.4 1.2c-.6.4-.9.7-.9 1.3"/><circle cx="8" cy="11.2" r=".5" fill="currentColor"/></svg>,
  search: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="7" cy="7" r="4"/><path d="m10 10 3.5 3.5"/></svg>,
  tree: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="8" cy="3" r="1.4"/><circle cx="3.5" cy="9" r="1.4"/><circle cx="8" cy="9" r="1.4"/><circle cx="12.5" cy="9" r="1.4"/><circle cx="8" cy="13.5" r="1.2"/><path d="M8 4.4v3.2M8 4.4 3.7 7.8M8 4.4l4.3 3.4M8 10.4v1.9"/></svg>,
  pen: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m3 13 1-3 7-7 2 2-7 7-3 1Z"/><path d="m10 4 2 2"/></svg>,
  flask: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M6 2.5h4M6.5 2.5v4L3.5 12a1.5 1.5 0 0 0 1.3 2.2h6.4A1.5 1.5 0 0 0 12.5 12L9.5 6.5v-4"/><path d="M4.7 10h6.6"/></svg>,
  sigma: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M11.5 3h-7l3.5 5-3.5 5h7"/></svg>,
  cal: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="2.5" y="3.5" width="11" height="10" rx="1.5"/><path d="M2.5 6.5h11M5.5 2v3M10.5 2v3"/></svg>,
  film: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="2.5" y="3" width="11" height="10" rx="1"/><path d="M2.5 6.5h11M2.5 9.5h11M5 3v10M11 3v10"/></svg>,
  plus: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" {...p}><path d="M8 3.5v9M3.5 8h9"/></svg>,
  spark: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M8 2.5v3M8 10.5v3M2.5 8h3M10.5 8h3M4 4l2 2M10 10l2 2M12 4l-2 2M4 12l2-2"/></svg>,
  send: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M8 13V3M4 7l4-4 4 4"/></svg>,
  attach: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M11 7 6.5 11.5a2 2 0 1 1-2.8-2.8L9 3.4a3 3 0 0 1 4.2 4.2L8 13"/></svg>,
  caret: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m5 6.5 3 3 3-3"/></svg>,
  gear: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="8" cy="8" r="2"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.5 3.5 5 5M11 11l1.5 1.5M12.5 3.5 11 5M5 11l-1.5 1.5"/></svg>,
  dots: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" {...p}><circle cx="3.5" cy="8" r="1.2"/><circle cx="8" cy="8" r="1.2"/><circle cx="12.5" cy="8" r="1.2"/></svg>,
  chevR: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m6 4 4 4-4 4"/></svg>,
  chevL: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m10 4-4 4 4 4"/></svg>,
  arrowDown: (p) => <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M8 3v10M4 9l4 4 4-4"/></svg>,
};

function MicroChart({ kind, accent = "#4F9CF9", warn = "#E8A87C", danger = "#E86C6C" }) {
  if (kind === "biasvar") {
    // U-shaped MSE, monotonic variance & bias²
    return (
      <svg viewBox="0 0 200 150" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
        <defs>
          <pattern id="grid-bv" width="20" height="15" patternUnits="userSpaceOnUse">
            <path d="M20 0H0V15" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="1"/>
          </pattern>
        </defs>
        <rect x="20" y="10" width="170" height="120" fill="url(#grid-bv)"/>
        <line x1="20" y1="130" x2="190" y2="130" stroke="rgba(255,255,255,0.25)" strokeWidth="1"/>
        <line x1="20" y1="10"  x2="20"  y2="130" stroke="rgba(255,255,255,0.25)" strokeWidth="1"/>
        {/* Variance: monotonic decrease */}
        <path d="M22 22 Q 60 28 90 60 T 188 120" fill="none" stroke="#7EC8A4" strokeWidth="1.6"/>
        {/* Bias²: monotonic increase */}
        <path d="M22 128 Q 70 126 100 110 T 188 30" fill="none" stroke={warn} strokeWidth="1.6"/>
        {/* Test MSE: U-shape (sum) */}
        <path d="M22 30 Q 60 70 95 75 T 188 35" fill="none" stroke="#9B8FCC" strokeWidth="1.8"/>
        {/* Min marker */}
        <circle cx="95" cy="75" r="2.5" fill="#9B8FCC"/>
        <line x1="95" y1="75" x2="95" y2="130" stroke="#9B8FCC" strokeWidth="0.8" strokeDasharray="2 2"/>
        {/* Axis labels */}
        <text x="105" y="146" fill="rgba(255,255,255,0.45)" fontSize="9" fontFamily="IBM Plex Mono, monospace" textAnchor="middle">log λ →</text>
        <text x="10" y="70" fill="rgba(255,255,255,0.45)" fontSize="9" fontFamily="IBM Plex Mono, monospace" transform="rotate(-90 10 70)" textAnchor="middle">error</text>
        {/* Legend */}
        <g fontFamily="IBM Plex Mono, monospace" fontSize="8">
          <rect x="120" y="14" width="68" height="38" fill="rgba(13,15,18,0.7)" stroke="rgba(255,255,255,0.08)"/>
          <line x1="125" y1="22" x2="135" y2="22" stroke="#9B8FCC" strokeWidth="1.8"/><text x="138" y="25" fill="rgba(255,255,255,0.7)">test MSE</text>
          <line x1="125" y1="32" x2="135" y2="32" stroke={warn} strokeWidth="1.6"/><text x="138" y="35" fill="rgba(255,255,255,0.7)">bias²</text>
          <line x1="125" y1="42" x2="135" y2="42" stroke="#7EC8A4" strokeWidth="1.6"/><text x="138" y="45" fill="rgba(255,255,255,0.7)">variance</text>
        </g>
      </svg>
    );
  }
  if (kind === "paths") {
    // Coefficient paths shrinking toward 0 as λ grows
    return (
      <svg viewBox="0 0 200 150" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
        <line x1="20" y1="75" x2="190" y2="75" stroke="rgba(255,255,255,0.18)" strokeWidth="1" strokeDasharray="3 3"/>
        <line x1="20" y1="10" x2="20" y2="140" stroke="rgba(255,255,255,0.25)" strokeWidth="1"/>
        <line x1="20" y1="140" x2="190" y2="140" stroke="rgba(255,255,255,0.25)" strokeWidth="1"/>
        {[
          { d: "M22 22 C 60 26 110 60 188 74", c: "#4F9CF9" },
          { d: "M22 38 C 70 44 120 70 188 75", c: "#7EC8A4" },
          { d: "M22 110 C 80 100 130 84 188 76", c: "#E8A87C" },
          { d: "M22 130 C 80 122 130 90 188 76", c: "#E86C6C" },
          { d: "M22 60 C 70 64 120 72 188 75", c: "#9B8FCC" },
        ].map((p, i) => <path key={i} d={p.d} fill="none" stroke={p.c} strokeWidth="1.4" opacity="0.9"/>)}
        <text x="105" y="148" fill="rgba(255,255,255,0.45)" fontSize="9" fontFamily="IBM Plex Mono, monospace" textAnchor="middle">log λ →</text>
        <text x="10" y="75" fill="rgba(255,255,255,0.45)" fontSize="9" fontFamily="IBM Plex Mono, monospace" transform="rotate(-90 10 75)" textAnchor="middle">β̂ⱼ</text>
      </svg>
    );
  }
  return null;
}

Object.assign(window, { Ic, MicroChart });
