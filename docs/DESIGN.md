# openZero Design System

> Corporate identity and design language reference for the openZero dashboard.
> This document is the single source of truth for visual decisions across every
> component, page, and interaction pattern.

---

## 1. Brand Voice

openZero communicates through a neutral, technical brand identity. The visual
language is precise, understated, and confidence-driven. No decorative
flourishes, no gratuitous animation, no marketing polish. Every pixel exists
because it aids comprehension, reinforces hierarchy, or improves usability.

The system is a tool, not a product page. The dashboard is an operational
surface where information density and legibility outweigh aesthetic novelty.

---

## 2. Color Architecture

### 2.1 Accent Palette

The accent palette is user-configurable via the identity card. Default values
serve as the canonical fallbacks throughout CSS custom properties.

| Token                    | Default      | Purpose                          |
|:-------------------------|:-------------|:---------------------------------|
| `--accent-color`         | `#14B8A6`    | Primary brand accent             |
| `--accent-color-rgb`     | `20,184,166` | RGB triplet for `rgba()` usage   |
| `--accent-secondary`     | `#0066FF`    | Secondary gradient endpoint      |
| `--accent-secondary-rgb` | `0,102,255`  | RGB triplet                      |
| `--accent-tertiary`      | `#6366F1`    | Tertiary / decorative accent     |
| `--accent-glow`          | `rgba(20,184,166,0.4)` | Ambient glow effect    |

### 2.2 Semantic Status

| Token              | Default     | Use Case           |
|:-------------------|:------------|:-------------------|
| `--color-success`  | `#22c55e`   | Confirmations, OK  |
| `--color-warning`  | `#eab308`   | Caution states     |
| `--color-danger`   | `#ef4444`   | Errors, deletions  |
| `--color-info`     | `#3b82f6`   | Informational      |
| `--color-birthday` | `#f472b6`   | Birthday events    |

Each semantic color has a corresponding `-rgb` triplet and optionally a
`-light` variant for foreground text on dark translucent backgrounds.

### 2.3 Text Hierarchy

| Token              | Value                       | Role                 |
|:-------------------|:----------------------------|:---------------------|
| `--text-primary`   | `#fff`                      | Headings, key labels |
| `--text-secondary` | `rgba(255,255,255,0.7)`     | Body copy            |
| `--text-muted`     | `rgba(255,255,255,0.4)`     | Metadata, hints      |
| `--text-faint`     | `rgba(255,255,255,0.2)`     | Placeholders         |

### 2.4 Surfaces and Borders

Surfaces use translucent backgrounds that layer on top of the body gradient.
Borders remain subtle to avoid visual clutter.

| Token                    | Value                          |
|:-------------------------|:-------------------------------|
| `--surface-card`         | `rgba(255,255,255,0.03)`       |
| `--surface-card-hover`   | `rgba(255,255,255,0.05)`       |
| `--surface-input`        | `rgba(0,0,0,0.2)`             |
| `--surface-input-focus`  | `rgba(0,0,0,0.28)`            |
| `--surface-hover`        | `rgba(255,255,255,0.06)`       |
| `--border-subtle`        | `rgba(255,255,255,0.08)`       |
| `--border-medium`        | `rgba(255,255,255,0.12)`       |
| `--border-accent`        | `rgba(accent-rgb,0.25)`       |
| `--border-accent-focus`  | `rgba(accent-rgb,0.4)`        |

---

## 3. Typography

### 3.1 Font Stack

| Purpose    | Family                                                     |
|:-----------|:-----------------------------------------------------------|
| Body       | `Inter`, system-ui, -apple-system, sans-serif              |
| Monospace  | `Fira Code`, `SF Mono`, `Cascadia Code`, monospace         |
| CJK        | `Noto Sans SC/JP/KR` (planned self-hosted)                 |

### 3.2 Scale

Base font size is `105%` (~16.8px). All sizing uses `rem` relative to this
base. Letter-spacing values are the sole exception where `em` is acceptable
since spacing should scale proportionally with the element's own font size.

| Level      | Size      | Weight | Letter-Spacing |
|:-----------|:----------|:-------|:---------------|
| H1         | 2rem      | 800    | -0.02em        |
| H2         | 1.5rem    | 700    | 0.02em         |
| Subtitle   | 0.65rem   | 400    | 0.1em          |
| Body       | 0.9rem    | 400    | --             |
| Label      | 0.7rem    | 600    | 0.06em         |
| Small      | 0.65rem   | 500    | 0.03em         |

### 3.3 Rules

- Use `rem` for all spacing: margin, padding, gap, width, height.
- Use `em` only for `letter-spacing`.
- Never use `px` for sizing except pixel-perfect icon dimensions.
- Monospace text references the `--font-mono` token, never a hardcoded family.

---

## 4. Spacing and Radii

### 4.1 Spacing

No formal spacing scale is enforced beyond the general rem guideline.
Component-internal spacing uses practical values (0.25rem, 0.5rem, 0.75rem,
1rem, 1.5rem, 2rem).

### 4.2 Border Radii

| Token          | Value     | Typical Use                   |
|:---------------|:----------|:------------------------------|
| `--radius-xs`  | `0.25rem` | Small badges, tags            |
| `--radius-sm`  | `0.35rem` | Buttons, inline inputs        |
| `--radius-md`  | `0.5rem`  | Cards, form elements          |
| `--radius-lg`  | `0.75rem` | Panels, modals                |
| `--radius-xl`  | `1rem`    | Large containers              |
| `--radius-2xl` | `1.5rem`  | Hero cards, chat bubbles      |
| `--radius-pill`| `9999px`  | Pill-shaped badges            |

---

## 5. Glassmorphism

The dashboard relies on layered translucent surfaces with backdrop filters.
These tokens govern the glass aesthetic globally:

| Token              | Default  | Notes                         |
|:-------------------|:---------|:------------------------------|
| `--glass-blur`     | `blur(24px)` | Standard blur                |
| `--glass-opacity`  | `0.6`   | Panel opacity baseline         |
| `--glass-saturate` | `180%`  | Color saturation boost         |
| `--glass-brightness`| `100%` | Brightness adjustment          |

Tooltip surfaces use their own sub-tokens (`--tooltip-bg`, `--tooltip-blur`,
`--tooltip-saturate`, `--tooltip-border`, `--tooltip-shadow`).

---

## 6. Animation and Timing

### 6.1 Duration Tokens

| Token               | Value   | Use Case                        |
|:---------------------|:--------|:--------------------------------|
| `--duration-instant` | `0.1s`  | Micro-interactions (focus ring) |
| `--duration-fast`    | `0.15s` | Hover states, toggles           |
| `--duration-base`    | `0.3s`  | Standard transitions            |
| `--duration-slow`    | `0.5s`  | Panel reveals, modals           |
| `--duration-hero`    | `0.8s`  | Page-level entrances            |

### 6.2 Easing

| Token            | Value                              | Role              |
|:-----------------|:-----------------------------------|:-------------------|
| `--ease-default` | `cubic-bezier(0.4, 0, 0.2, 1)`    | General motion     |
| `--ease-snap`    | `cubic-bezier(0.23, 1, 0.32, 1)` | Snappy entrances   |

### 6.3 GSAP Easing Rules (Phase 1+)

Standard production animations use these GSAP easing functions:

| Context       | Easing         |
|:--------------|:---------------|
| Entrance      | `expo.out`     |
| Transition    | `expo.inOut`   |
| Exit          | `power2.in`    |
| Micro-motion  | `power2.out`   |

`elastic.out` and `bounce.out` are permitted **only** inside goo mode
(scoped to `oz-goo-*` animation classes). This is a hard rule.

### 6.4 Reduced Motion

Every component includes `@media (prefers-reduced-motion: reduce)` blocks
that suppress transitions and animations. The shared `ACCESSIBILITY_STYLES`
module handles the baseline; components add overrides for their specific
keyframe animations.

---

## 7. Shared Style Modules

Reusable CSS fragments live in `src/dashboard/services/` as exported
template string constants. Components import and interpolate them inside
their Shadow DOM `<style>` blocks via `${MODULE_NAME}`.

| Module                    | Export Name            | Purpose                             |
|:--------------------------|:-----------------------|:------------------------------------|
| `accessibilityStyles.ts`  | `ACCESSIBILITY_STYLES` | `.sr-only`, reduced-motion, forced-colors |
| `sectionHeaderStyles.ts`  | `SECTION_HEADER_STYLES`| `h2`, `.h-icon`, `.subtitle`       |
| `buttonStyles.ts`         | `BUTTON_STYLES`        | `.btn-primary`, `.btn-ghost`       |
| `formInputStyles.ts`      | `FORM_INPUT_STYLES`    | `input`, `textarea`, `select`      |
| `glassTooltipStyles.ts`   | `GLASS_TOOLTIP_STYLES` | `.has-tip`, `.glass-tooltip`       |
| `scrollbarStyles.ts`      | `SCROLLBAR_STYLES`     | Thin 4px webkit scrollbar          |
| `statusStyles.ts`         | `STATUS_STYLES`        | `.status-dot` with semantic colors |
| `badgeStyles.ts`          | `BADGE_STYLES`         | `.badge` with variant classes      |
| `listItemStyles.ts`       | `LIST_ITEM_STYLES`     | `.list-item` card-row pattern      |
| `emptyStateStyles.ts`     | `EMPTY_STATE_STYLES`   | `.empty-state` placeholder         |
| `feedbackStyles.ts`       | `FEEDBACK_STYLES`      | `.feedback` toast with variants    |

### 7.1 Class Name Conventions

| Pattern        | Standard Class   | Notes                                  |
|:---------------|:-----------------|:---------------------------------------|
| Section icon   | `.h-icon`        | 28x28 gradient badge next to `h2`      |
| Status dot     | `.status-dot`    | 8px semantic indicator                 |
| Empty fallback | `.empty-state`   | Centered italic "no data" text         |
| Feedback toast | `.feedback`      | With `.success`, `.error`, `.info`     |

---

## 8. Component Architecture

### 8.1 Shadow DOM

All dashboard components are native Web Components using
`attachShadow({ mode: 'open' })`. Styles are defined as template literal
`<style>` blocks within each component's `.ts` file. This single-file
encapsulation pattern is intentional and must not be extracted into separate
CSS files.

### 8.2 Token Penetration

CSS custom properties defined on `:root` in `style.css` naturally cross
Shadow DOM boundaries. Components reference these tokens via `var()` with
hardcoded fallback values ensuring standalone functionality.

### 8.3 Component-Specific Overrides

When a shared module provides a default (e.g., section header gradient), a
component may override by adding a more specific rule after the module
interpolation:

```css
${SECTION_HEADER_STYLES}
h2 .h-icon {
	background: linear-gradient(135deg, #8b5cf6 0%, var(--accent-color, #14B8A6) 100%);
}
```

---

## 9. Accessibility

The dashboard conforms to **WCAG 2.1 Level AA** and **EN 301 549**.

### 9.1 Non-Negotiable Requirements

- All interactive elements must be keyboard-navigable with visible
  `:focus-visible` rings (minimum 2px solid, using accent color).
- Minimum touch target: 44x44px.
- Color is never the sole conveyor of meaning.
- Every dynamic content region uses `aria-live` with appropriate politeness.
- Heading hierarchy (`h1` through `h3`) is maintained without skipping.

### 9.2 Screen-Reader Text

All user-facing ARIA strings use `this.tr('key', 'English fallback')` for
localization support. English strings must never be hardcoded directly in
`aria-label` or `aria-describedby` attributes.

### 9.3 Media Queries

Every Shadow DOM component includes:
- `@media (prefers-reduced-motion: reduce)` -- transitions and animations
  reduced to near-zero.
- `@media (forced-colors: active)` -- high-contrast mode fallbacks using
  system keywords (`Highlight`, `LinkText`, `CanvasText`).

---

## 10. Dark / Light / Auto Theming (Planned)

Current implementation is dark-mode only. Phase 2+ will introduce:

- A `prefers-color-scheme` media query for auto detection.
- Light-mode token overrides within `:root` using `[data-theme="light"]`.
- A persistent toggle stored per-user in the identity record.
- All current `rgba(255,255,255,...)` values will be swapped to semantic
  tokens that resolve differently per scheme.

---

## 11. Cursor Parallax (Planned)

Phase 3+ introduces a mouse-tracking parallax layer:

- Glassmorphism panels shift subtly based on pointer coordinates.
- Movement is throttled to `requestAnimationFrame` cadence.
- Disabled entirely when `prefers-reduced-motion: reduce` is active.

---

## 12. Goo Mode (Planned)

An opt-in easter egg animation layer scoped to `oz-goo-*` CSS classes:

- Organic, fluid morphing of UI element borders and backgrounds.
- Uses `elastic.out` and `bounce.out` GSAP easing (the only permitted use
  of these easing functions in the entire codebase).
- Activated through the glass settings panel; never on by default.

---

## 13. Self-Hosted Fonts (Planned)

All typefaces will be served from the VPS to eliminate Google Fonts dependency:

| Family              | Weights        | Subsets                 |
|:--------------------|:---------------|:------------------------|
| Inter               | 400, 500, 600, 700, 800 | Latin, Latin Extended |
| Fira Code           | 400, 700       | Latin                   |
| Noto Sans SC        | 400, 700       | CJK Simplified Chinese  |
| Noto Sans JP        | 400, 700       | CJK Japanese            |
| Noto Sans KR        | 400, 700       | CJK Korean              |
| Noto Sans Devanagari| 400, 700       | Hindi                   |
| Noto Sans Bengali   | 400, 700       | Bengali                 |
| Noto Sans Arabic    | 400, 700       | Arabic                  |

Font files will be stored under `src/dashboard/fonts/` and loaded via
`@font-face` declarations in `style.css`. CJK fonts use `unicode-range`
subsetting to avoid loading unnecessary glyphs.
