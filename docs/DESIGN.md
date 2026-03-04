# openZero Design System

> The visual language of openZero. This document is the single source of truth
> for every color, shape, motion, and spacing decision across the dashboard.

---

## 1. Brand Voice

openZero feels like mission control at 2 AM -- calm, focused, and quietly
powerful. The interface rewards sustained attention. Every surface is
translucent, every accent is earned, every animation serves orientation.

The design philosophy: **clarity through restraint, personality through
precision.** Information density is high because the operator trusts this
system to surface what matters. Visual hierarchy does the talking so the
interface itself can stay quiet.

This is a living environment, not a static page. It breathes through subtle
glassmorphism, responds to user identity through configurable accent
palettes, and treats accessibility as a first-class design constraint rather
than an afterthought.

---

## 2. Color Architecture

Colors are authored in HSLA for intuitive hue/saturation reasoning. Every
token is user-configurable through the identity card, making the palette
a personal signature rather than a fixed brand.

### 2.1 Accent Palette

| Token                    | Default                        | Purpose                          |
|:-------------------------|:-------------------------------|:---------------------------------|
| `--accent-color`         | `hsla(173, 80%, 40%, 1)`      | Primary accent -- teal energy    |
| `--accent-color-rgb`     | `20, 184, 166`                | RGB triplet for compositing      |
| `--accent-secondary`     | `hsla(216, 100%, 50%, 1)`     | Secondary gradient endpoint      |
| `--accent-secondary-rgb` | `0, 102, 255`                 | RGB triplet                      |
| `--accent-tertiary`      | `hsla(239, 84%, 67%, 1)`      | Tertiary / decorative accent     |
| `--accent-glow`          | `hsla(173, 80%, 40%, 0.4)`    | Ambient glow halo                |

### 2.2 Semantic Status

| Token              | Default                     | Use Case           |
|:-------------------|:----------------------------|:-------------------|
| `--color-success`  | `hsla(142, 71%, 45%, 1)`    | Confirmations, OK  |
| `--color-warning`  | `hsla(45, 93%, 47%, 1)`     | Caution states     |
| `--color-danger`   | `hsla(0, 84%, 60%, 1)`      | Errors, deletions  |
| `--color-info`     | `hsla(217, 91%, 60%, 1)`    | Informational      |
| `--color-birthday` | `hsla(329, 86%, 70%, 1)`    | Birthday events    |

Each semantic color carries a `-rgb` triplet for alpha compositing and
optionally a `-light` variant for foreground text on dark translucent
backgrounds.

### 2.3 Text Hierarchy

Text fades from full white to near-invisible in four deliberate steps.
Each step has a clear semantic role so components stay consistent without
guessing opacity values.

| Token              | Value                       | Role                 |
|:-------------------|:----------------------------|:---------------------|
| `--text-primary`   | `hsla(0, 0%, 100%, 1)`      | Headings, key labels |
| `--text-secondary` | `hsla(0, 0%, 100%, 0.7)`    | Body copy            |
| `--text-muted`     | `hsla(0, 0%, 100%, 0.4)`    | Metadata, hints      |
| `--text-faint`     | `hsla(0, 0%, 100%, 0.2)`    | Placeholders         |

### 2.4 Surfaces and Borders

Surfaces are translucent layers that let the body gradient breathe through.
Borders stay whisper-quiet so content remains the focal point.

| Token                    | Value                              |
|:-------------------------|:-----------------------------------|
| `--surface-card`         | `hsla(0, 0%, 100%, 0.03)`         |
| `--surface-card-hover`   | `hsla(0, 0%, 100%, 0.05)`         |
| `--surface-input`        | `hsla(0, 0%, 0%, 0.2)`            |
| `--surface-input-focus`  | `hsla(0, 0%, 0%, 0.28)`           |
| `--surface-hover`        | `hsla(0, 0%, 100%, 0.06)`         |
| `--border-subtle`        | `hsla(0, 0%, 100%, 0.08)`         |
| `--border-medium`        | `hsla(0, 0%, 100%, 0.12)`         |
| `--border-accent`        | `hsla(173, 80%, 40%, 0.25)`       |
| `--border-accent-focus`  | `hsla(173, 80%, 40%, 0.4)`        |

---

## 3. Typography

### 3.1 Font Stack

All typefaces are self-hosted from the VPS -- no external CDN dependencies.

| Purpose    | Family                                                     |
|:-----------|:-----------------------------------------------------------|
| Body       | `Inter`, system-ui, -apple-system, sans-serif              |
| Monospace  | `Fira Code`, `SF Mono`, `Cascadia Code`, monospace         |
| CJK        | `Noto Sans SC/JP/KR` (planned self-hosted)                 |

### 3.2 Scale

Base font size is `105%` (~16.8px). All sizing uses `rem` relative to this
base. Letter-spacing is the sole exception where `em` is acceptable since it
should scale proportionally with the element's own font size.

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

Components breathe through a practical spacing vocabulary: 0.25rem, 0.5rem,
0.75rem, 1rem, 1.5rem, 2rem. Generous whitespace is intentional -- it
creates visual calm inside information-dense panels.

### 4.2 Border Radii

Corners soften progressively from tight badges to expansive containers.

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

The dashboard's signature texture: layered translucent surfaces with
backdrop blur that let color gradients bleed through. The effect creates
depth without shadow hierarchies and makes the interface feel like it
exists in a physical space.

| Token              | Default      | Notes                         |
|:-------------------|:-------------|:------------------------------|
| `--glass-blur`     | `blur(24px)` | Standard blur                 |
| `--glass-opacity`  | `0.6`        | Panel opacity baseline        |
| `--glass-saturate` | `180%`       | Color saturation boost        |
| `--glass-brightness`| `100%`      | Brightness adjustment         |

Tooltip surfaces use their own sub-tokens (`--tooltip-bg`, `--tooltip-blur`,
`--tooltip-saturate`, `--tooltip-border`, `--tooltip-shadow`) so they can
float above card surfaces with a heavier glass treatment.

---

## 6. Animation and Timing

Motion in openZero is purposeful: it guides attention, confirms actions,
and creates spatial continuity. Speed is calibrated so interactions feel
instant while larger transitions feel deliberate.

### 6.1 Duration Tokens

| Token                | Value   | Use Case                        |
|:---------------------|:--------|:--------------------------------|
| `--duration-instant` | `0.1s`  | Micro-interactions (focus ring) |
| `--duration-fast`    | `0.15s` | Hover states, toggles           |
| `--duration-base`    | `0.3s`  | Standard transitions            |
| `--duration-slow`    | `0.5s`  | Panel reveals, modals           |
| `--duration-hero`    | `0.8s`  | Page-level entrances            |

### 6.2 Easing

| Token            | Value                             | Role              |
|:-----------------|:----------------------------------|:-------------------|
| `--ease-default` | `cubic-bezier(0.4, 0, 0.2, 1)`   | General motion     |
| `--ease-snap`    | `cubic-bezier(0.23, 1, 0.32, 1)` | Snappy entrances   |

### 6.3 GSAP Easing Rules (Phase 1+)

| Context       | Easing         |
|:--------------|:---------------|
| Entrance      | `expo.out`     |
| Transition    | `expo.inOut`   |
| Exit          | `power2.in`    |
| Micro-motion  | `power2.out`   |

`elastic.out` and `bounce.out` are permitted **only** inside goo mode
(scoped to `oz-goo-*` animation classes). This is a hard rule.

### 6.4 Reduced Motion

Every component includes `@media (prefers-reduced-motion: reduce)` blocks.
The shared `ACCESSIBILITY_STYLES` module provides the baseline; components
add overrides for their specific keyframe animations so the experience
remains fully usable without any motion at all.

---

## 7. Shared Style Modules

Reusable CSS fragments live in `src/dashboard/services/` as exported
template string constants. Components import and interpolate them inside
their Shadow DOM `<style>` blocks via `${MODULE_NAME}`. This keeps every
component self-contained while sharing a single source of truth for
recurring patterns.

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
| Section icon   | `.h-icon`        | 32x32 gradient badge next to `h2`      |
| Status dot     | `.status-dot`    | 8px semantic indicator                 |
| Empty fallback | `.empty-state`   | Centered italic "no data" text         |
| Feedback toast | `.feedback`      | With `.success`, `.error`, `.info`     |

---

## 8. Component Architecture

### 8.1 Shadow DOM

All dashboard components are native Web Components using
`attachShadow({ mode: 'open' })`. Styles live as template literal `<style>`
blocks within each component's `.ts` file -- a single-file encapsulation
pattern that keeps markup, logic, and styling collocated. This is
intentional and must not be extracted into separate CSS files.

### 8.2 Token Penetration

CSS custom properties defined on `:root` in `style.css` naturally cross
Shadow DOM boundaries. Components reference these tokens via `var()` with
hardcoded HSLA fallback values ensuring standalone functionality even if
the global stylesheet is absent.

### 8.3 Component-Specific Overrides

When a shared module provides a default (e.g., section header gradient), a
component may override by adding a more specific rule after the module
interpolation:

```css
${SECTION_HEADER_STYLES}
h2 .h-icon {
	background: linear-gradient(135deg, hsla(263, 90%, 65%, 1) 0%, var(--accent-color) 100%);
}
```

### 8.4 Icon Style

Section header icons are **line-only** (stroke, never filled) at 20x20px
rendered in a 24x24 viewBox. They sit inside a 32x32 gradient badge
(`.h-icon`). Every icon SVG must carry `fill="none"`, `stroke="white"`,
`stroke-width="2"`, `aria-hidden="true"`, and `focusable="false"`.

---

## 9. Accessibility

Accessibility is a design material, not a compliance checkbox. The dashboard
conforms to **WCAG 2.1 Level AA** and **EN 301 549** because good
accessibility produces good design: clear focus states, logical reading
order, and meaningful feedback benefit every user.

### 9.1 Core Requirements

- All interactive elements are keyboard-navigable with visible
  `:focus-visible` rings (minimum 2px solid, accent color).
- Minimum touch target: 44x44px.
- Color is never the sole conveyor of meaning -- text or icons always
  accompany color indicators.
- Dynamic content regions use `aria-live` with appropriate politeness.
- Heading hierarchy (`h1` through `h3`) is maintained without skipping.

### 9.2 Screen-Reader Text

All user-facing ARIA strings use `this.tr('key', 'English fallback')` for
localization support. English strings are never hardcoded directly in
`aria-label` or `aria-describedby` attributes.

### 9.3 Media Queries

Every Shadow DOM component includes:
- `@media (prefers-reduced-motion: reduce)` -- transitions and animations
  reduced to near-zero.
- `@media (forced-colors: active)` -- high-contrast mode fallbacks using
  system keywords (`Highlight`, `LinkText`, `CanvasText`).

---

## 10. Dark / Light / Auto Theming (Planned)

The current implementation is dark-mode only -- optimized for the 2 AM
mission control aesthetic. Phase 2+ will introduce:

- A `prefers-color-scheme` media query for auto detection.
- Light-mode token overrides within `:root` using `[data-theme="light"]`.
- A persistent toggle stored per-user in the identity record.
- All current `hsla(0, 0%, 100%, ...)` values will resolve through semantic
  tokens that flip per scheme.

---

## 11. Cursor Parallax (Planned)

Phase 3+ introduces a mouse-tracking parallax layer that gives the
glassmorphism panels a subtle spatial quality:

- Panels shift based on pointer coordinates, creating a sense of depth.
- Movement is throttled to `requestAnimationFrame` cadence.
- Disabled entirely when `prefers-reduced-motion: reduce` is active.

---

## 12. Goo Mode (Planned)

An opt-in easter egg -- organic, fluid morphing of UI borders and
backgrounds scoped to `oz-goo-*` CSS classes:

- Uses `elastic.out` and `bounce.out` GSAP easing (the only permitted use
  of these easing functions in the entire codebase).
- Activated through the settings panel. Never on by default.
- A playful counterpoint to the otherwise measured visual language.

---

## 13. Self-Hosted Fonts

All typefaces are served from the VPS to eliminate external dependencies.
Font files live under `src/dashboard/fonts/` and load via `@font-face`
declarations in `style.css`.

| Family              | Weights                  | Status    |
|:--------------------|:-------------------------|:----------|
| Inter               | 400, 500, 600, 700, 800 | Shipped   |
| Fira Code           | 400, 700                 | Shipped   |
| Noto Sans SC        | 400, 700                 | Planned   |
| Noto Sans JP        | 400, 700                 | Planned   |
| Noto Sans KR        | 400, 700                 | Planned   |
| Noto Sans Devanagari| 400, 700                 | Planned   |
| Noto Sans Bengali   | 400, 700                 | Planned   |
| Noto Sans Arabic    | 400, 700                 | Planned   |

CJK fonts will use `unicode-range` subsetting to avoid loading unnecessary
glyphs.
