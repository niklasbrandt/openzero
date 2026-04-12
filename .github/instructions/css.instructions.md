---
description: "CSS design system conventions for openZero"
applyTo: "**/*.css"
---

# CSS Conventions (openZero)

## Spacing
- Use `rem` for all spacing (margin, padding, gap, width, height).
- The only acceptable use of `em` is `letter-spacing`.

## Colors
- Use `var(--token, fallback)` for ALL colors. Never hardcode hex values.
- Color format: HSLA (`hsla(H, S%, L%, A)`).
- Full token chain for accent colors: `-h`, `-s`, `-l`, `-rgb`, plus composite.
- When updating a color, set the ENTIRE chain (H, S, L, RGB, composite, aliases).
- Reference `docs/artifacts/DESIGN.md` for the full token architecture.

## Class Naming
- Section header icons: `.h-icon`
- Status indicators: `.status-dot`
- Empty placeholders: `.empty-state`
- Never use generic `.icon` or `.empty`

## Accessibility
- `@media (prefers-reduced-motion: reduce)` to suppress animations.
- `@media (forced-colors: active)` for Windows High Contrast.
- Maintain WCAG 2.1 AA contrast ratios.
