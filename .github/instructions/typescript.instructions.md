---
description: "TypeScript Web Component conventions for the openZero dashboard"
applyTo: "**/*.ts"
---

# TypeScript Conventions (openZero Dashboard)

## Shadow DOM Component Pattern
Every dashboard component follows this structure:
1. `class MyWidget extends HTMLElement` with `attachShadow({ mode: 'open' })`.
2. `connectedCallback()` calls `this.render()` then `this.loadTranslations()`.
3. `disconnectedCallback()` cleans up timers, listeners, observers.

## Translation (i18n)
- ALL user-facing strings MUST use `this.tr('key', 'English fallback')`.
- This includes `aria-label`, `placeholder`, `title`, and visible text.
- The component must include the translation boilerplate:
  ```ts
  private t: Record<string, string> = {};
  private async loadTranslations() { /* fetch from /api/dashboard/translations */ }
  private tr(key: string, fallback: string): string { return this.t[key] || fallback; }
  ```
- New keys go into `_EN` and `_DE` in `src/backend/app/services/translations.py`.

## Style Modules
- Import and interpolate shared modules in `<style>`:
  - `${ACCESSIBILITY_STYLES}` -- mandatory in every component.
  - `${BUTTON_STYLES}`, `${SECTION_HEADER_STYLES}`, `${SCROLLBAR_STYLES}` as needed.
- CSS stays inside the `.ts` file via template literals. Never extract to separate files.

## Accessibility
- Include `@media (prefers-reduced-motion: reduce)` block.
- Include `@media (forced-colors: active)` block.
- Use native HTML elements (`<button>`, `<input>`, `<a>`) where possible.
- Min 44x44px touch targets. Visible `:focus-visible` states.
- `aria-live="polite"` for dynamic content updates.

## CSS Rules
- `rem` for all spacing. `em` only for `letter-spacing`.
- `var(--token, fallback)` for all colors. No hardcoded hex.
