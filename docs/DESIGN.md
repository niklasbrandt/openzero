# openZero Design System

## 1. Overview

openZero uses a token-based CSS custom property system with HSLA color decomposition. All visual decisions should reference this document before modifying component styling.

## 2. Color Architecture

### Token Structure

Every accent color is decomposed into four primitive tokens, then composed into a composite token. This enables per-component alpha overrides without redundant custom properties.

```
--accent-primary-h      (hue:        0-360)
--accent-primary-s      (saturation: 0%-100%)
--accent-primary-l      (lightness:  0%-100%)
--accent-primary-rgb    ("R, G, B" triplet for rgba() usage)
--accent-primary        (composite:  hsla(H, S%, L%, 1))
```

The same structure applies to `--accent-secondary-*` and `--accent-tertiary-*`. Legacy aliases (`--accent-color`, `--accent-glow`) are also maintained for backward compatibility.

**Rule:** Every CSS var update MUST set the full token chain — H, S, L, RGB, composite, and all aliases. Never update a partial set.

### Color Format

All colors in the frontend use HSLA strings: `hsla(H, S%, L%, A)`. Hex strings (`#RRGGBB`) are accepted by all parsers and losslessly converted. The backend may store either format; all parsers (`parseColor` in `UserCard.ts`, `main.ts`, and `index.html`) handle both.

### parseColor / hslToRgb

Two helpers are shared across `UserCard.ts`, `main.ts`, and `index.html`:

- `parseColor(color: string)` — accepts `hsla(...)`, `hsl(...)`, or `#RRGGBB`. Returns `{ h, s, l, a }`.
- `hslToRgb(h, s, l)` — returns an `"R, G, B"` triplet string for use in `rgba()`.

## 3. Dark/Light Mode vs Themes

These are **strictly separate** concerns:

| Concern | Mechanism | Where Controlled |
|---------|-----------|-----------------|
| Dark/Light mode | `[data-theme="light"]` on `<html>` | Three-way toggle in UserCard.ts (`dark` / `auto` / `light`) |
| Accent theme | CSS custom properties | Theme preset dropdown + HSLA picker |

**Themes must never set `data-theme`** or otherwise alter the dark/light mode. Mode is controlled only by the user's explicit toggle or system preference via `@media (prefers-color-scheme: light)`.

## 4. Theme Catalogue

38 curated themes in 10 categories. All values are HSLA strings.

### Default
| Key | Label |
|-----|-------|
| `fusion` | Default Fusion |

### Natural Elements
| Key | Label |
|-----|-------|
| `wind` | Wind |
| `water` | Water |
| `fire` | Fire |
| `earth` | Earth |

### Natural Environments
| Key | Label |
|-----|-------|
| `polar` | Polar |
| `mountain` | Mountain |
| `forest` | Forest |
| `desert` | Desert |
| `coast` | Coast |
| `sky` | Sky |

### Natural Phenomena
| Key | Label |
|-----|-------|
| `aurora` | Aurora |
| `storm` | Storm |
| `jungle` | Jungle |

### IDE Palettes
Proper nouns — same in all languages.

| Key | Label |
|-----|-------|
| `solarized` | Solarized |
| `monokai` | Monokai |
| `dracula` | Dracula |
| `gruvbox` | Gruvbox |
| `nord` | Nord |
| `catppuccin` | Catppuccin |
| `tokyo_night` | Tokyo Night |

### Monochromatic
| Key | Label |
|-----|-------|
| `mono_silver` | Monochrome Silver |
| `mono_teal` | Monochrome Teal |
| `mono_violet` | Monochrome Violet |

### Pure Colors
| Key | Label |
|-----|-------|
| `color_red` | Red |
| `color_blue` | Blue |
| `color_green` | Green |
| `color_purple` | Purple |
| `color_orange` | Orange |
| `color_cyan` | Cyan |
| `color_gold` | Gold |
| `color_indigo` | Indigo |

### Glassmorphism
| Key | Label |
|-----|-------|
| `glass_frost` | Glass Frost |
| `glass_ember` | Glass Ember |

### Style
| Key | Label |
|-----|-------|
| `neon` | Neon |

### High Contrast
| Key | Label |
|-----|-------|
| `hc_1` | High Contrast I |
| `hc_2` | High Contrast II |
| `hc_3` | High Contrast III |

## 5. HSLA Color Picker

Each of the three accent colors (Primary, Secondary, Tertiary) is edited via an inline HSLA picker overlay within `UserCard.ts`.

### Interaction Pattern

1. User clicks a color swatch button (shows the color dot and label)
2. Picker overlay appears above the swatches with 4 sliders: Hue, Saturation, Lightness, Opacity
3. Sliders and number inputs are two-way synced; preview circle updates in real time
4. "Apply" writes `hsla(H, S%, L%, A)` to the hidden input and calls `applyColors()`
5. "Cancel" closes the picker without changes
6. The swatch dot color is updated on apply

### Accessibility

- Picker overlay uses `role="dialog"` and `aria-modal="true"`
- All slider inputs have `aria-label` via `this.tr()` (multilingual)
- Swatch buttons have `aria-label` via `this.tr('primary_label', 'Primary Accent')`
- Keyboard: picker closes on Cancel; Apply can be triggered via Enter on the button

## 6. Design Tokens Reference

Defined in `src/dashboard/css/tokens.css`. Key surface tokens:

```css
--surface-bg             /* page background */
--surface-card           /* widget card background */
--surface-overlay        /* modal / picker overlay background */
--border-subtle          /* 10% white borders */
--text-primary           /* primary text */
--text-muted             /* muted / label text */
```

Light mode overrides are scoped to `[data-theme="light"]` in `tokens.css`.

## 7. Shared Style Modules

Reusable CSS lives in `src/dashboard/services/*Styles.ts`:

| Module | Contents |
|--------|----------|
| `BUTTON_STYLES` | `.oz-btn`, `.oz-btn-primary`, `.oz-btn-secondary` |
| `ACCESSIBILITY_STYLES` | `.sr-only`, `@media(prefers-reduced-motion)`, `@media(forced-colors:active)` |
| `SCROLLBAR_STYLES` | Custom scrollbar track/thumb |
| `SECTION_HEADER_STYLES` | `.section-header`, `.h-icon` |

Every Shadow DOM component must include `${ACCESSIBILITY_STYLES}`.

## 8. Typography

- Font family: `var(--font-sans, 'Inter', sans-serif)`
- All spacing uses `rem` (not `em`)
- `letter-spacing` may use `em`
- Heading hierarchy: H2 (component title) → H3 (section header)

## 9. Animation Easing

Standard GSAP easing:

| Use case | Easing |
|----------|--------|
| Entrance | `expo.out` |
| Transition | `expo.inOut` |
| Exit | `power2.in` |
| Micro-interaction | `power2.out` |
| Goo mode only | `elastic.out`, `bounce.out` |
