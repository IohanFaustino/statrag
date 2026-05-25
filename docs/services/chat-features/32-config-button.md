# 32 — Config button + popover restyle

## Purpose

The settings affordance was an unclear gear labelled "⚙ Chat settings" docked in the topbar. Renamed to a clear, card-themed "Config" button with a wrench icon, and the popover repainted to match the dark-red glass aesthetic.

## Where it lives

- `web/src/components/SettingsPicker.tsx` — trigger button + popover panel. Button class: `tool-btn tool-btn--config`. Icon: `IconWrench` (added to `Icons.tsx`).
- `web/src/styles/tutor.css` — popover surface (`.settings-popover`) restyled with `--bg-elevated` glass + red accent border + red focus ring.
- Form controls inside the popover (range slider thumb, checkboxes) overridden to use `accent-color: var(--accent-danger)` so they render red, not the browser-default blue.

## What changed

| Before | After |
|---|---|
| `⚙ Chat settings` text button | `Config` button with `IconWrench` |
| Generic toolbar styling | `tool-btn--config` card style (matches model/mode pickers) |
| Blue native slider + checkboxes | Forced red accent via `accent-color` |
| Plain dark panel | `bg-elevated` glass + red 1px border + red glow |

## User-facing behavior

- Same popover contents (preferences, density, theme, font pair, etc.) — only chrome changed.
- Slider thumbs and checkboxes are now red on every browser (Chrome/Firefox/Safari respect `accent-color`).
- Visually consistent with the rest of the topbar card row.
