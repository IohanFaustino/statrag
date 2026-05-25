# 01 — Design Tokens

Every color, font, size, shadow, and motion value used in the design. Reproduce these as CSS custom properties (or your token system's equivalent). Names match `design/styles.css` + `design/neon.css`.

---

## Theme attribute

Themes are switched by flipping `data-theme` on `<html>`:

```html
<html data-theme="dark">   <!-- or "light" -->
```

All tokens below are defined as `:root[data-theme="dark"] { ... }` and `:root[data-theme="light"] { ... }` blocks. Components consume them via `var(--token-name)` — they never reference raw hex.

---

## Color tokens

### Dark theme — "Scholar's Terminal" (neon + glass)

```css
:root[data-theme="dark"] {
  /* Surfaces — translucent for glassmorphism */
  --bg-primary:    #050912;                          /* opaque body */
  --bg-secondary:  rgba(15, 23, 38, 0.34);           /* topbar/sidebar/ctx-panel glass */
  --bg-tertiary:   rgba(22, 32, 52, 0.34);           /* cards/chips glass */
  --bg-elevated:   rgba(32, 44, 68, 0.58);           /* modals/dropdowns/user bubble */

  /* Borders */
  --border-subtle:  rgba(120, 170, 255, 0.10);
  --border-default: rgba(120, 170, 255, 0.26);

  /* Text */
  --text-primary:   #E6EEFB;
  --text-secondary: #8CA2C2;
  --text-tertiary:  #5C6E8B;
  --text-inverse:   #050912;   /* dark text on light accent buttons */

  /* Accents */
  --accent-primary:   #3FA9FF;   /* electric neon blue */
  --accent-secondary: #3DDC97;   /* sage / success / ISLP book */
  --accent-tertiary:  #FFB36B;   /* amber / Hansen book */
  --accent-danger:    #FF6B7E;
  --accent-neutral:   #B68BFF;   /* lilac / figure / temp-chat */

  /* Code & math */
  --code-surface: rgba(8, 14, 26, 0.55);
  --code-accent:  #3FA9FF;
  --syntax-amber: #FFB36B;       /* source highlight underline */

  /* Glow */
  --glow-accent:  0 0 16px rgba(63, 169, 255, 0.45), 0 0 36px rgba(63, 169, 255, 0.15);
  --glow-soft:    0 0 10px rgba(63, 169, 255, 0.30);
  --glass-edge:   inset 0 1px 0 rgba(255, 255, 255, 0.06),
                  inset 0 0 0 1px rgba(120, 170, 255, 0.06);

  /* Shadows */
  --shadow-elev:    0 14px 50px rgba(0, 0, 0, 0.55),
                    inset 0 1px 0 rgba(255, 255, 255, 0.04);
  --shadow-popover: 0 12px 40px rgba(0, 0, 0, 0.55),
                    0 0 0 1px rgba(63, 169, 255, 0.10),
                    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}
```

### Light theme — "Financial Terminal" (cream + navy)

```css
:root[data-theme="light"] {
  /* Warm paper — primary surface */
  --bg-primary:    #F2EEE5;                          /* opaque body */
  --bg-secondary:  rgba(255, 253, 248, 0.42);        /* topbar/sidebar/ctx-panel glass */
  --bg-tertiary:   rgba(255, 253, 248, 0.55);        /* cards/chips glass */
  --bg-elevated:   rgba(255, 253, 248, 0.80);

  --border-subtle:  rgba(0, 31, 63, 0.10);
  --border-default: rgba(0, 31, 63, 0.24);

  --text-primary:   #001F3F;                         /* deep navy — primary text + accent */
  --text-secondary: #3D5870;
  --text-tertiary:  #7A8FA8;
  --text-inverse:   #FAFAF7;

  --accent-primary:   #001F3F;
  --accent-secondary: #1F6A4A;   /* finance green */
  --accent-tertiary:  #B8860B;   /* gold — highlights */
  --accent-danger:    #A8322B;
  --accent-neutral:   #6B4F7A;   /* burgundy-violet — temp chat */

  --code-surface: rgba(0, 31, 63, 0.05);
  --code-accent:  #001F3F;
  --syntax-amber: #B8860B;

  --glow-accent:  0 0 14px rgba(0, 31, 63, 0.22), 0 0 30px rgba(0, 31, 63, 0.10);
  --glow-soft:    0 0 8px  rgba(0, 31, 63, 0.16);

  --shadow-elev:    0 8px 32px rgba(0, 31, 63, 0.10);
  --shadow-popover: 0 8px 28px rgba(0, 31, 63, 0.14),
                    0 0 0 1px rgba(0, 31, 63, 0.06);
}
```

### Body backdrop (both themes)

The body has a fixed cosmic/financial gradient drawn via `body::before`:

```css
/* Dark */
body::before {
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background:
    radial-gradient(60vmax 60vmax at 15% 85%, rgba(63, 169, 255, 0.22), transparent 55%),
    radial-gradient(50vmax 50vmax at 90% 12%, rgba(140, 95, 255, 0.13), transparent 60%),
    radial-gradient(35vmax 35vmax at 60% 50%, rgba(60, 120, 255, 0.07), transparent 65%);
}
body::after {
  /* film grain to break up the gradient — dark only */
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,0.025) 1px, transparent 0);
  background-size: 3px 3px; opacity: 0.45;
}

/* Light */
:root[data-theme="light"] body::before {
  background:
    radial-gradient(60vmax 60vmax at 15% 88%, rgba(0, 31, 63, 0.10), transparent 55%),
    radial-gradient(48vmax 48vmax at 88% 8%,  rgba(184, 134, 11, 0.10), transparent 60%);
}
:root[data-theme="light"] body::after { display: none; }
```

Place `.app` at `position: relative; z-index: 1;` so it sits above the backdrop.

---

## Book / provider colors

Each indexed book has a brand color used for dots, pins, and chips:

| Book                    | Hex (dark)  | Hex (light) | Usage              |
|-------------------------|-------------|-------------|--------------------|
| ISLP                    | `#7EC8A4`   | `#1F6A4A`   | dot, pin, book tag |
| Hansen                  | `#E8A87C`   | `#B8860B`   | dot, pin, book tag |
| ESL                     | `#9B8FCC`   | `#6B4F7A`   | (not yet indexed)  |
| Wooldridge              | `#4F9CF9`   | `#001F3F`   | (not yet indexed)  |

Each provider has a brand color used in the Model Picker:

| Provider  | Hex       | Short |
|-----------|-----------|-------|
| OpenAI    | `#10A37F` | OAI   |
| DeepSeek  | `#4D6BFE` | DS    |

---

## Typography

### Font families

Loaded from Google Fonts in `statrag.html`. The "Plex" pair is default; "Editorial" and "Spectral" are tweakable alternates.

| Family          | Weights      | Role                                  |
|-----------------|--------------|---------------------------------------|
| IBM Plex Serif  | 300/400/500/600 | Display, headings, mode titles, scene numbers |
| IBM Plex Sans   | 400/500/600/700 | Body, UI labels, prose answers        |
| IBM Plex Mono   | 400/500/600     | Metadata, timestamps, code, citations |
| Newsreader      | opsz, 300–600   | Alt serif (Editorial pair)            |
| Inter Tight     | 400–700      | Alt sans (Editorial pair)             |
| JetBrains Mono  | 400/500/600  | Alt mono (Editorial pair)             |
| Spectral        | 300/400/500/600 | Alt serif (Spectral pair)         |
| Manrope         | 400/500/600/700 | Alt sans (Spectral pair)         |

CSS vars:

```css
--font-serif: 'IBM Plex Serif', Georgia, serif;
--font-sans:  'IBM Plex Sans', system-ui, -apple-system, sans-serif;
--font-mono:  'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace;
```

### Type scale

```css
--text-xs:   11px / 1.4   /* metadata, timestamps, kbd, monospace labels */
--text-sm:   13px / 1.5   /* secondary UI, captions, sidebar items */
--text-base: 15px / 1.65  /* body prose, answers */
--text-md:   17px / 1.6   /* section headers, source chunk in modal */
--text-lg:   21px / 1.4   /* mode titles, empty-state titles */
--text-xl:   28px / 1.2   /* roadmap scene numbers (future) */
--text-2xl:  38px / 1.1   /* hero, empty states */
```

### Treatments

- **Monospace** for: timestamps, source chip metadata, retrieval metadata rows, model picker tagline/badges, KPI numbers, chunk IDs, breadcrumb separators.
- **Serif (Plex Serif)** for: section headers, mode titles, book card titles, modal titles (h2), assistant message **strong** emphasis, empty-state titles, scene numbers.
- **Sans (Plex Sans)** for: everything else (body prose, button labels, conv list items).
- **`text-wrap: pretty`** on all prose paragraphs (`.msg__p`, `.book-card__desc`, etc.).
- **`text-wrap: balance`** on h2/h3 titles in modals.

---

## Spacing

No strict scale, but the design uses these recurring values:

| Token         | Px    | Usage                                |
|---------------|-------|--------------------------------------|
| —             | 2px   | inline icon-to-text gap              |
| —             | 4px   | tight inline gap                     |
| —             | 6px   | dense list gap, button padding-y     |
| —             | 8px   | default gap                          |
| —             | 10–12 | card padding, button padding-x       |
| —             | 14–16 | thread gap (compact density)         |
| —             | 18–22 | thread gap (comfortable density)     |
| —             | 24    | container padding                    |
| —             | 32    | thread side padding                  |
| `--section-gap`  | 14 / 22  | density-controlled (compact / comfy) |
| `--thread-gap`   | 18 / 28  | density-controlled                   |
| `--row-pad-y`    | 6 / 10   | density-controlled                   |
| `--conv-h`       | 30 / 36  | sidebar conv item height             |

Density toggles between `compact` and `comfortable` via `data-density` attribute on `<html>`.

---

## Layout dimensions

```css
--topbar-h:             48px;
--sidebar-w:            260px;
--sidebar-w-collapsed:  52px;
--ctx-w:                320px;
--ctx-w-collapsed:      36px;
```

Thread max-width: `720px` centered.
Modal max-widths: `default 720px` · `md 760px` · `lg 1020px`.
ModelPicker panel: `360px`.
Mode picker panel: `320px`.
BookCover: 92×132 (lg) or 56×78 (compact).

---

## Border radii

| Value | Usage |
|-------|-------|
| `2px` | book spine, chip excerpt corners |
| `3px` | kbd badges, small badges |
| `4px` | figure thumb, accordion meta |
| `6px` | tool buttons, code surface, small inputs |
| `7px` | tool buttons, books-btn |
| `8px` | source/figure/book card, panels |
| `10px` | input field, mode picker panel, focus modal panel |
| `12px` | user bubble (12-12-2-12 asymmetric), modal panel |
| `14px` | focus modal panel |
| `100px` (pill) | bm-chip, book-card__toggle |

User bubble has asymmetric corners: `border-radius: 12px 12px 2px 12px` (the bottom-right is the "tail").

---

## Shadows & glow

Three categories:

**Surface depth** — for cards, modals, popovers.
```css
--shadow-elev:    0 14px 50px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.04);
--shadow-popover: 0 12px 40px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(63, 169, 255, 0.10), inset 0 1px 0 rgba(255, 255, 255, 0.06);
```

**Glass edge** — adds a subtle top-light highlight to glass surfaces.
```css
--glass-edge: inset 0 1px 0 rgba(255, 255, 255, 0.06), inset 0 0 0 1px rgba(120, 170, 255, 0.06);
```

**Neon glow** — for accent elements (logo, status dot, focus rings, active states, hover on cards).
```css
--glow-accent: 0 0 16px rgba(63, 169, 255, 0.45), 0 0 36px rgba(63, 169, 255, 0.15);
--glow-soft:   0 0 10px rgba(63, 169, 255, 0.30);
```

Applied to:
- `.logo__mark` — `text-shadow: 0 0 14px rgba(63,169,255,0.6), 0 0 28px rgba(63,169,255,0.3)`
- `.status-dot.is-online` — `box-shadow: var(--glow-accent)`
- `.input-bar__field:focus-within` — `box-shadow: 0 0 0 3px rgba(63,169,255,0.16), var(--glow-accent)`
- `.input-bar__send.is-active` — `box-shadow: var(--glow-accent)`
- `.source-card:hover`, `.figure-card:hover`, `.src-chip:hover` — `box-shadow: var(--glow-soft)` + accent border
- `.bm-chip.is-on` — `box-shadow: 0 0 14px rgba(63,169,255,0.28), inset 0 0 14px rgba(63,169,255,0.05)`
- `.bm-kpi--accent` — `box-shadow: inset 0 0 22px rgba(63,169,255,0.06)` + accent border
- `.mp-item.is-active` — `box-shadow: inset 0 0 14px rgba(63,169,255,0.08)`

In light mode, all glow uses navy `rgba(0, 31, 63, X)` instead of cyan.

---

## Glassmorphism recipe

The signature surface treatment. Apply to: topbar, sidebar, ctx-panel, modals, popovers, cards, chips, the input field, the temp-chat header.

```css
.surface {
  background: var(--bg-secondary);   /* or --bg-tertiary for smaller cards */
  backdrop-filter: blur(22px) saturate(170%);
  -webkit-backdrop-filter: blur(22px) saturate(170%);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--glass-edge);
}
```

Blur strength by surface:
- Topbar / sidebar / ctx-panel / modal panel: **22px / 170%**
- Input bar / temp chat header: **16–18px / 160%**
- Cards / chips / input field / source modal chunk: **14px**

**Critical**: the chat thread area (`.main__pane--primary`, `.thread`) is **fully transparent** — `background: transparent`. The cosmic backdrop shows through. Do not give it a background.

---

## Motion

| Element                | Animation                          | Duration | Easing             |
|------------------------|------------------------------------|----------|--------------------|
| Mode pill / chip toggle| bg + border + color cross-fade    | 120ms    | ease                |
| Mode picker open       | popover scale + fade               | 150ms    | ease-out           |
| Source card hover      | border-color + translateY(-1px) + glow | 120ms | ease            |
| Context panel collapse | width transition                   | 200ms    | ease-out           |
| Focus modal scrim      | opacity fade                       | 160ms    | ease-out           |
| Focus modal panel      | scale 0.96 → 1 + translateY 8 → 0 + fade | 180ms | cubic-bezier(0.2, 0.8, 0.2, 1) |
| Hover-fork "+" button  | opacity + translateX(-4 → 0)       | 120ms    | ease                |
| Send button press      | scale(0.95)                        | 80ms     | ease                |
| Send button hover (active) | filter brightness(1.08) + scale(1.02) | 120ms | ease         |
| Status dot pulse       | ring scale 0.8 → 1.8 + opacity 0.6 → 0 | 2s loop | ease-out      |
| Streaming dot          | translateY(0→-1px) + opacity 0.25 → 1 | 1.2s loop | ease-in-out |
| KaTeX equations        | none — render once on mount        |          |                     |
| Theme toggle           | instant attribute swap; tokens transition implicitly via CSS color transitions | — | — |
| Theme toggle icon hover | rotate(20deg)                     | 200ms    | ease                |

**Reduced motion:** all transitions/animations collapse to 0.01ms when `prefers-reduced-motion: reduce` is set. Implementation:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Z-index scale

```
0    body::before / body::after (backdrop layers)
1    .app (above backdrop)
5    .msg__fork (hover button)
10   .ctx-panel__collapse (handle on panel edge)
50   .topbar
55   .popover-scrim (under any open popover)
60   popover panels (.book-filter__panel, .mode-picker__panel, .model-picker__panel, .mode-overflow__panel)
1000 .fm (focus modal scrim + panel)
2147483646 .twk-panel (preview tweaks — N/A in production)
```

Continue to → `02_components.md`
