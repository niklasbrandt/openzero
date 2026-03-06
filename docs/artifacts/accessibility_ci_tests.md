# Accessibility CI Tests -- Design, Rationale, and Exhaustive Fix Guide

## 1. Context and Standards

openZero's dashboard **must conform to WCAG 2.1 Level AA and EN 301 549** (agents.md rule 12, DESIGN.md section 9). These standards overlap almost completely: EN 301 549 clause 9 _is_ WCAG 2.1 AA, making a single test suite sufficient for both mandates.

Current Lighthouse accessibility score: **100/100** (5 consecutive runs; docs/artifacts/lighthouse_results.md Run 8).

The purpose of CI accessibility testing is therefore **regression prevention** -- ensuring no future change silently breaks the A11y 100 baseline without a CI failure surfacing it within minutes.

---

## 2. Tool Selection

### Why axe-core + Playwright (not Lighthouse CI or pa11y)

| Criterion | axe-core + Playwright | Lighthouse CI | pa11y |
|:---|:---|:---|:---|
| Shadow DOM piercing | Full (open mode natively) | Partial (outer + some rules) | None |
| WCAG 2.1 AA coverage | ~57% of WCAG SCs automatically | ~35% | ~30% |
| GitHub Actions support | Official action available | Official action available | Manual |
| False-positive control | Per-rule disable flags | Limited | Limited |
| Failure details | Node HTML + fix summary | Category score | Rule code only |
| Headless browser | Playwright (Chromium) | puppeteer | jsdom / real browser |

**The critical deciding factor**: all 16 openZero components use `attachShadow({ mode: 'open' })`. pa11y's HTMLCodeSniffer engine cannot inspect Shadow DOM at all -- it would only audit the 14 `<section>` elements in the outer shell, missing every button, form input, heading, ARIA region, and focus indicator living inside the components. Lighthouse CI audits Shadow DOM partially (it runs axe-core internally but with limited rule propagation across boundaries). Only `@axe-core/playwright` queries the DOM via a recursive tree-walk that descends into each `shadowRoot` natively.

### axe-core rule engine

axe-core 4.x is the reference engine maintained by Deque Systems (the firm that co-authored the original ARIA spec). It covers WCAG 2.0 A/AA, WCAG 2.1 AA, WCAG 2.2 AA, and EN 301 549 criteria. It is also used internally by Lighthouse, Edge DevTools, Firefox Accessibility Inspector, and the axe browser extension.

---

## 3. File Structure

```
src/dashboard/
  playwright.config.ts           # Playwright + webServer config
  tests/
    accessibility.spec.ts        # All 10 accessibility test cases
  package.json                   # @playwright/test + @axe-core/playwright added
.github/
  workflows/
    ci.yml                       # New `accessibility` job (job 4 of 4)
```

---

## 4. CI Job Specification

```yaml
accessibility:
  name: Accessibility audit (WCAG 2.1 AA)
  runs-on: ubuntu-latest
  needs: [frontend]              # Type-check must pass first
  steps:
    - checkout
    - setup Node 20 (npm cache)
    - npm ci
    - npx playwright install --with-deps chromium
    - npm run build              # Vite production bundle to dist/
    - npx playwright test tests/accessibility.spec.ts
    - upload playwright-report as artifact on failure (7-day retention)
```

**Why `needs: [frontend]` and not `needs: [frontend, backend]`?**: The accessibility audit runs against the static Vite bundle; it does not need the Docker build. Running it in parallel with `backend` and `build` keeps total CI wall time under 4 minutes.

**Why build inside the job?**: `vite preview` can only serve from `dist/`. If the build job ran first and we tried to share the artifact, we would add S3 upload/download latency and complexity. The build is fast (< 30s on ubuntu-latest) and the `npm ci` step is cached.

---

## 5. What Each Test Validates

### Test 1 -- Full WCAG 2.1 AA audit

Tags analyzed: `wcag2a`, `wcag2aa`, `wcag21aa`

This single pass covers the majority of automatically-detectable WCAG 2.1 A and AA success criteria. It exercises the complete DOM spanning the outer HTML shell and all 16 Shadow DOM components.

**Disabled rule**: `scrollable-region-focusable` -- this rule fires when a scrollable container has no focusable descendant. In the preview environment, list-based components (BriefingHistory, MemorySearch, ProjectTree) render with empty containers (API 404s return no data). An empty `<div class="list" tabindex="0">` will fail this rule even though it is correct in the presence of data. This is a known false positive in test environments without API data. It must be re-enabled once mock API responses exist.

### Test 2 and Test 3 -- Color contrast (dark and light theme)

**Rule**: `color-contrast` (WCAG 1.4.3 -- minimum 4.5:1 for normal text, 3:1 for large text)

Dark theme tests the default palette. Light theme explicitly sets `data-theme="light"` and waits 200ms for CSS custom properties to repaint before auditing. This exercises the entire HSL token system (tokens.css) to catch any combination of accent hue + lightness that drops below the AA threshold, particularly for the tinted surface backgrounds introduced in the recent surface-tinting commit.

### Test 4 -- ARIA correctness

Tag: `cat.aria`

Covers all axe-core ARIA rules: valid roles, required attributes, allowed attributes, prohibited attributes, parent/child role relationships, deprecated roles, valid attribute values. Pierces Shadow DOM so misconfigured ARIA inside components will fail the build.

### Test 5 -- Landmark and heading structure

Rules: `landmark-one-main`, `landmark-unique`, `landmark-no-duplicate-banner`, `landmark-no-duplicate-contentinfo`, `landmark-no-duplicate-main`, `region`, `heading-order`, `page-has-heading-one`, `bypass`

Verifies the document's navigational skeleton: exactly one `<main>`, no duplicate banners, no skipped heading levels (h1 -> h3 max per DESIGN.md section 9.1), and a bypass mechanism (skip link). Screen reader users navigate entirely via landmarks and headings -- losing any of these is a critical regression.

### Test 6 -- Keyboard navigation focus traversal

Custom test (not axe-core). Recursively collects all interactive elements across all shadow trees, then simulates Tab key presses and records which elements receive focus. Asserts:

- At least 10 distinct elements are registered as interactive.
- At least 5 distinct elements receive focus via Tab.
- No focus trap (no element receives focus twice consecutively).

**Why a custom test?**: axe-core's `focus-trap` and `keyboard` rules are passive (they detect structural traps but do not simulate user navigation). Simulated Tab traversal catches dynamic traps introduced by `z-index` overlays, `pointer-events: none` applied to focusable elements, or `overflow: hidden` on wrapping containers.

### Test 7 -- Skip link

Validates the `<a class="skip-link" href="#main-content">` element that bypass mechanism rule requires. Without a skip link, keyboard users must Tab through the entire navigation on every page view to reach the main content area. WCAG 2.4.1 (Bypass Blocks).

### Test 8 -- Language declaration

Validates `<html lang="...">` with a valid BCP 47 language tag. Screen readers use this to select the correct voice synthesiser profile. Without it, a German user with a German TTS installation may hear English text read with German phonology. WCAG 3.1.1 (Language of Page).

### Test 9 -- Image and SVG alternatives

Rules: `image-alt`, `svg-img-alt`. The dashboard has many decorative SVG icons (correctly marked `aria-hidden="true" focusable="false"` per index.html audit). Any new informative SVG, `<img>`, or CSS-background-replaced element that lacks an alternative text will fail this test. WCAG 1.1.1 (Non-text Content).

### Test 10 -- Form labels

Rules: `label`, `label-content-name-mismatch`, `select-name`, `input-button-name`, `input-image-alt`. The dashboard has input fields in MemorySearch, CreateProject, ChatPrompt, CalendarManager, EmailRules, and WelcomeOnboarding. Every `<input>`, `<textarea>`, and `<select>` must have an associated visible `<label>` or an `aria-label`/`aria-labelledby` attribute. WCAG 1.3.1 (Info and Relationships) and 4.1.2 (Name, Role, Value).

---

## 6. Exhaustive Fix Guide

This section describes every category of accessibility violation that the test suite can detect, explains why it fails, and gives the exact code pattern required to fix it.

---

### 6.1 Color Contrast Failures (WCAG 1.4.3, 1.4.6 / EN 301 549 clause 9.1.4.3)

**What fails**: Text or interactive element foreground color does not achieve 4.5:1 contrast against its background color (AA) or 7:1 (AAA). Large text (18pt/24px regular or 14pt/18.7px bold) requires only 3:1.

**Why axe-core catches it**: axe-core reads computed CSS color values from the rendered CSSOM and calculates relative luminance per WCAG formula. It pierces Shadow DOM to audit tokens resolved inside components.

**Common causes in this codebase**:
- A new accent hue introduced via theme presets that reduces lightness values below the computed minimum.
- A `disabled` state styled with reduced opacity where the resulting contrast drops below threshold.
- `var(--token)` used without a sufficient fallback value.

**How to fix**:

_Step 1_: Identify the failing element from the axe violation output. The `nodes[].html` field contains the element's HTML. The `nodes[].failureSummary` shows the expected and actual ratio.

_Step 2_: In `src/dashboard/css/tokens.css`, locate the token governing the element's color. For light-theme text, check `[data-theme="light"]` block. For dark-theme, check the `:root` block.

_Step 3_: Adjust the lightness channel of the HSL value. The formula for minimum lightness on a dark surface is:
```
L_min = 1 - (1 / (ratio * (L_bg + 0.05))) + 0.05
```
For ratio=4.5 against a near-black surface (L_bg ≈ 0.05), L_min ≈ 0.52 (52%). Text must be at 52% lightness or brighter.

_Step 4_: If the token controls both a surface and text color, split it into two tokens: `--token-surface` and `--token-text` with independent lightness values.

_Step 5_: For the accent-tinted surface system (recently introduced), always test every theme preset combination. Add a `--accent-min-contrast-text` token that clamps the computed tinted foreground to a safe minimum:
```css
--surface-text: hsl(var(--accent-primary-h) 10% max(55%, var(--surface-text-l)));
```

_Step 6_: For `disabled` states, never use `opacity: 0.4` alone. Instead use a dedicated token:
```css
.btn:disabled {
    color: var(--text-disabled, hsl(0 0% 45%));
    background: var(--surface-disabled, hsl(0 0% 18%));
}
```
Verify the disabled token pair achieves 4.5:1.

_Step 7_: Re-run `npm run test:a11y` and confirm the test passes before committing.

---

### 6.2 ARIA Attribute Errors (WCAG 4.1.2 / EN 301 549 clause 9.4.1.2)

**What fails**: An element has an ARIA attribute that is invalid for its role, uses a deprecated role, is missing a required attribute, has a parent/child role mismatch, or uses a non-existent ARIA value.

**How to fix by sub-type**:

#### `aria-allowed-attr`
An attribute is not permitted on the element's role. Example: `aria-checked` on an element with `role="button"`.
```html
<!-- WRONG -->
<div role="button" aria-checked="true">Sort ascending</div>

<!-- CORRECT: use aria-pressed for toggle state on buttons -->
<div role="button" aria-pressed="true">Sort ascending</div>
```

#### `aria-required-attr`
A required attribute is missing. Example: `role="checkbox"` without `aria-checked`.
```html
<!-- WRONG -->
<span role="checkbox">Remember me</span>

<!-- CORRECT -->
<span role="checkbox" aria-checked="false" tabindex="0">Remember me</span>
```

#### `aria-required-children`
A parent role is missing required children. Example: `role="listbox"` containing `<div>` instead of `role="option"` elements.
```html
<!-- WRONG -->
<ul role="listbox">
    <li>Item 1</li>
</ul>

<!-- CORRECT -->
<ul role="listbox">
    <li role="option" aria-selected="false">Item 1</li>
</ul>
```

#### `aria-required-parent`
A child role appears outside its required container. Example: `role="option"` outside a `role="listbox"`.
Fix: always wrap child-role elements inside the correct container role.

#### `aria-roles`
An invalid (non-existent or misspelled) role value is used.
```html
<!-- WRONG -->
<div role="modal">...</div>      <!-- "modal" is not an ARIA role -->

<!-- CORRECT -->
<div role="dialog" aria-modal="true" aria-label="Settings">...</div>
```

#### `aria-deprecated-role`
A role has been removed from the ARIA spec. Example: `role="directory"`.
Remove the deprecated role attribute or replace with the modern equivalent.

#### `aria-prohibited-attr`
An attribute is explicitly prohibited on a role. Example: `aria-label` on `role="presentation"`.
```html
<!-- WRONG -->
<div role="presentation" aria-label="decorative">...</div>

<!-- CORRECT -->
<div role="presentation">...</div>
```

**Pattern for all ARIA fixes in Shadow DOM components**:
All ARIA attributes in openZero components must use `this.tr('key', 'English fallback')` for localizable strings. Never hardcode English directly:
```typescript
// WRONG
this.shadowRoot.innerHTML = `<button aria-label="Close">X</button>`;

// CORRECT
this.shadowRoot.innerHTML = `<button aria-label="${this.tr('close_btn', 'Close')}">X</button>`;
```
Then add the key to both `_EN` and `_DE` in `src/backend/app/services/translations.py` under the `Accessibility / ARIA labels` section.

---

### 6.3 Form Label Failures (WCAG 1.3.1, 4.1.2 / EN 301 549 clause 9.1.3.1, 9.4.1.2)

**What fails**: An `<input>`, `<textarea>`, or `<select>` has no programmatically associated label. Screen readers announce the input's type but not its purpose.

**How to fix**:

_Option A_ (preferred for visible labels):
```html
<!-- Associate via for/id pair -->
<label for="search-input">Search memories</label>
<input id="search-input" type="text" />
```

_Option B_ (for inputs where a visible label is not desired for design reasons):
```html
<input
    type="text"
    aria-label="${this.tr('memory_search_placeholder', 'Search memories')}"
    placeholder="${this.tr('memory_search_placeholder', 'Search memories')}"
/>
```

_Option C_ (for inputs where another visible element describes the field):
```html
<h3 id="filter-heading">Filter by date</h3>
<input type="date" aria-labelledby="filter-heading" />
```

**Rule**: `placeholder` alone is NEVER sufficient as an accessible label. `placeholder` text disappears when the user starts typing, and many screen reader + browser combinations do not announce it at all. Always pair it with `aria-label` or a `<label>`.

**For icon buttons** (buttons that contain only an SVG icon):
```html
<!-- WRONG -->
<button><svg>...</svg></button>

<!-- CORRECT -->
<button aria-label="${this.tr('delete_event', 'Delete event')}">
    <svg aria-hidden="true" focusable="false">...</svg>
</button>
```

---

### 6.4 Keyboard Navigation Failures (WCAG 2.1.1, 2.1.2 / EN 301 549 clause 9.2.1.1, 9.2.1.2)

**What fails**: An interactive element cannot be reached via Tab, or focus becomes trapped inside a component and cannot escape with Escape or Tab.

**How to fix**:

#### Non-native interactive elements missing tabindex
```typescript
// WRONG: div with click handler is invisible to keyboard users
this.shadowRoot.innerHTML = `<div class="card" @click="...">Click me</div>`;

// CORRECT: use a button (preferred) or add tabindex
this.shadowRoot.innerHTML = `<button class="card">Click me</button>`;
// If a div is required for layout reasons:
this.shadowRoot.innerHTML = `<div class="card" tabindex="0" role="button" 
    aria-label="${this.tr('card_action', 'Open item')}">...</div>`;
```

#### Focus trap in modal/dialog components
When a component renders a dialog/drawer, focus must be trapped INSIDE the dialog while it is open, and returned to the trigger element when it closes.
```typescript
// Minimal focus trap implementation
private trapFocus(dialogEl: HTMLElement, triggerEl: HTMLElement) {
    const focusable = dialogEl.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key !== 'Tab') return;
        if (e.shiftKey) {
            if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
            if (document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
        if (e.key === 'Escape') { this.closeDialog(); triggerEl.focus(); }
    };

    dialogEl.addEventListener('keydown', handleKeyDown);
    // Store cleanup: this._trapCleanup = () => dialogEl.removeEventListener('keydown', handleKeyDown);
    first.focus();
}
```

#### Invisible elements receiving focus
Elements with `visibility: hidden`, `display: none`, or `opacity: 0` must also have `tabindex="-1"` or be removed from the DOM while hidden. Use `inert` attribute for entire regions:
```html
<div class="drawer" id="mobile-nav-drawer" inert>...</div>
<!-- Remove 'inert' attribute when opening the drawer -->
```

---

### 6.5 Focus Indicator Failures (WCAG 2.4.7, 2.4.11, 2.4.12 / EN 301 549 clause 9.2.4.7)

**What fails**: An interactive element has no visible focus ring when focused via keyboard.

**Why this codebase is protected**: `css/a11y.css` defines a global `:focus-visible` rule and `services/accessibilityStyles.ts` injects equivalent styles into every Shadow DOM component. The CI keyboard navigation test (Test 6) catches structural focus traversal issues but does NOT perform visual focus indicator validation (axe-core cannot measure CSS visibility).

**How to verify manually**: Use Tab on a freshly loaded dashboard. Every button, link, and input must show a 2px solid accent-colored ring on keyboard focus; it must disappear on mouse click (`:focus:not(:focus-visible)` suppresses it for pointer users).

**How to fix if a component overrides focus styles**:
```css
/* WRONG: removes all focus indicators */
:host *:focus { outline: none; }

/* CORRECT: only suppress for pointer users */
:host *:focus:not(:focus-visible) { outline: none; }
:host *:focus-visible {
    outline: 2px solid var(--accent-primary, #14B8A6);
    outline-offset: 3px;
    border-radius: 3px;
}
```

Never add `outline: none` or `outline: 0` to a component without pairing it with a `:focus-visible` alternative. The global `ACCESSIBILITY_STYLES` module already includes the correct pattern -- do not override it locally.

---

### 6.6 Landmark Failures (WCAG 1.3.6, 2.4.1 / EN 301 549 clause 9.1.3.6, 9.2.4.1)

**What fails**: The page lacks required landmark regions, has duplicate banners/contentinfos, or interactive content exists outside any landmark.

**How to fix**:

#### Missing main landmark
```html
<!-- WRONG: content floats outside landmarks -->
<div id="main-content">...</div>

<!-- CORRECT -->
<main id="main-content" aria-label="Dashboard">...</main>
```

#### Duplicate `<header>` or `<footer>` at page level
Sectioning elements (`<header>`, `<footer>`) are implicit landmarks only when they are top-level (not nested inside `<article>`, `<section>`, etc.). If a component includes its own `<header>`, it must be inside a sectioning element to prevent it mapping to `banner` role:
```html
<!-- Inside a Shadow DOM component -- OK: <header> inside <section> is not banner -->
<section>
    <header>
        <h2>Hardware Monitor</h2>
    </header>
</section>
```

#### All content must be inside a landmark
Every text node and interactive element must be contained within at least one of: `<main>`, `<nav>`, `<header>`, `<footer>`, `<aside>`, `<section>` (with accessible name), or `role="region"` (with `aria-label`).

---

### 6.7 Heading Order Failures (WCAG 1.3.1, 2.4.6 / EN 301 549 clause 9.1.3.1, 9.2.4.6)

**What fails**: Heading levels are skipped (e.g., `<h1>` followed directly by `<h3>`) or an `<h1>` is absent.

**The openZero heading hierarchy**:
```
h1 -- Page title (index.html header: "Z" wordmark, or the active section route)
  h2 -- Widget/section titles (e.g., "Hardware Monitor", "Memory Search")
    h3 -- Sub-sections within a widget (e.g., "CPU", "Memory", "Storage")
```

**How to fix**:

Never use `<h3>` inside a component that is the first heading in that component's shadow tree. The shadow tree's first heading visible to the heading-order audit should always be `<h2>` (the widget title, rendered via `${SECTION_HEADER_STYLES}` pattern).

If a component needs a lower heading for a subplot, use `<h3>`:
```typescript
// CORRECT heading structure inside a Shadow DOM component
`<section>
    <h2>${this.tr('section_title', 'Memory Search')}</h2>
    <div class="results">
        <h3>${this.tr('results_heading', 'Recent Results')}</h3>
    </div>
</section>`
```

Do not use headings purely for visual styling. If you need large bold text that is not a structural heading, use `<p class="section-label">` with CSS, not an `<h>` tag.

---

### 6.8 Image and SVG Alt-Text Failures (WCAG 1.1.1 / EN 301 549 clause 9.1.1.1)

**What fails**: An `<img>` element has no `alt` attribute (or an empty `alt` when the image is informative). An SVG without `aria-hidden` that contains no accessible text.

**The openZero rule** (verified in index.html): all decorative SVGs use `aria-hidden="true" focusable="false"`.

**How to fix informative SVGs** (SVGs that convey meaning, e.g., charts, diagrams):
```html
<!-- Option A: title element inside SVG -->
<svg role="img" aria-labelledby="chart-title">
    <title id="chart-title">CPU usage over the past hour: 42% average</title>
    <!-- SVG paths ... -->
</svg>

<!-- Option B: aria-label on the svg element -->
<svg role="img" aria-label="${this.tr('cpu_chart_alt', 'CPU usage chart')}">
    <!-- SVG paths ... -->
</svg>
```

**How to fix `<img>` elements**:
```html
<!-- Decorative image (pure visual) -->
<img src="pattern.svg" alt="" role="presentation" />

<!-- Informative image -->
<img src="avatar.png" alt="${this.tr('user_avatar_alt', 'User profile picture')}" />
```

---

### 6.9 Skip Link Failures (WCAG 2.4.1 / EN 301 549 clause 9.2.4.1)

**What fails**: The skip link (`<a href="#main-content">`) is present in the DOM but not first in tab order, does not link to an existing `id="main-content"`, or the target element cannot receive focus.

**How to fix**:

The skip link must:
1. Be the first element in the `<body>` tab order.
2. Link to `#main-content`.
3. Target `<main id="main-content">` -- `<main>` is inherently focusable as a landmark but adding `tabindex="-1"` to the target is a safe fallback:
```html
<main id="main-content" tabindex="-1">...</main>
```
4. Be visually hidden by default but become visible on `:focus`:
```css
.skip-link {
    position: absolute;
    top: -40px;
    left: 0;
    z-index: 9999;
    transition: top 0.2s;
}
.skip-link:focus {
    top: 0;
}
```

---

### 6.10 Language Declaration Failures (WCAG 3.1.1 / EN 301 549 clause 9.3.1.1)

**What fails**: `<html>` has no `lang` attribute, or the value is not a valid BCP 47 language tag.

**How to fix**:
```html
<!-- Correct -->
<html lang="en">        <!-- English -->
<html lang="de">        <!-- German -->
<html lang="en-GB">     <!-- British English -->
```

The openZero dashboard uses `<html lang="en">` (verified in index.html). If multi-language support is expanded to serve a German user interface by default, the `lang` attribute must be updated server-side or via the theme-init script to reflect the user's configured language.

For inline content in a different language from the page language, use `lang` on the element:
```html
<span lang="de">Guten Morgen</span>
```

---

### 6.11 Live Region Failures (WCAG 4.1.3 / EN 301 549 clause 9.4.1.3)

**What fails**: Dynamic content updates (new messages added to a list, status changes, error messages) are not announced to screen reader users because they lack `aria-live` regions.

**How to fix**:

Use `aria-live="polite"` for non-urgent updates (most cases):
```html
<div aria-live="polite" role="status" aria-atomic="false">
    <!-- Content inserted here is announced after the user stops typing -->
</div>
```

Use `aria-live="assertive"` only for urgent alerts that must interrupt:
```html
<div aria-live="assertive" role="alert" aria-atomic="true">
    <!-- Content here interrupts screen reader immediately -->
</div>
```

**Rules**:
- `aria-atomic="true"` means the whole region is re-read when any part changes. Use for short, complete messages.
- `aria-atomic="false"` (default) means only the changed nodes are announced. Use for append-only lists.
- The region must exist in the DOM BEFORE the dynamic content is inserted. Do not create the live region and insert content simultaneously -- screen readers will not announce it.

```typescript
// CORRECT pattern -- live region scaffolded in initial render, populated later
render() {
    this.shadowRoot!.innerHTML = `
        <div aria-live="polite" role="status" id="status-msg"></div>
    `;
}

updateStatus(message: string) {
    const status = this.shadowRoot!.getElementById('status-msg');
    if (status) status.textContent = message;  // Triggers announcement
}
```

---

### 6.12 Touch Target Size Failures (WCAG 2.5.5, 2.5.8 / EN 301 549 clause 9.2.5.5)

**What fails**: Interactive elements have a touch/click target smaller than 44x44px (WCAG 2.5.5 AA) or 24x24px (WCAG 2.5.8 AA in WCAG 2.2).

axe-core does not automatically check target size, but the CI keyboard navigation test validates that elements are focusable (invisible 1x1px elements fail this). Visual target size is validated by Lighthouse's "target-size" audit.

**How to fix**:
```css
/* Ensure minimum touch target via padding */
.icon-button {
    min-width: 2.75rem;    /* 44px at 16px base */
    min-height: 2.75rem;
    padding: 0.625rem;     /* Creates target area around smaller visual icon */
    display: inline-flex;
    align-items: center;
    justify-content: center;
}
```

For very small UI elements that cannot be enlarged (e.g., calendar date cells), use `touch-action: manipulation` to prevent double-tap zoom delay, and add spacing between targets:
```css
.calendar-day { margin: 0.125rem; }     /* Ensures 44px total including margin */
```

---

### 6.13 Reduced Motion Failures (WCAG 2.3.3 / EN 301 549 clause 9.2.3.3)

**What fails**: Animations or transitions play even when the user has set `prefers-reduced-motion: reduce` in their OS accessibility settings.

**How the codebase is protected**: `css/a11y.css` and `ACCESSIBILITY_STYLES` both include a global `@media (prefers-reduced-motion: reduce)` block that sets all `transition` and `animation` to `none` / `0.01ms`.

**How to fix if a new component adds motion**:

Step 1: Add the animation or transition as normal.
Step 2: Add a targeted override in the component's style block AFTER `${ACCESSIBILITY_STYLES}`:
```css
@media (prefers-reduced-motion: reduce) {
    .my-animated-element {
        animation: none;
        transition: none;
    }
}
```

Never suppress the global reduced-motion block from `ACCESSIBILITY_STYLES`. Never include long `transition-duration` values that are not caught by the global override (e.g., GSAP JS animations must check the media query in JS):
```typescript
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (!prefersReducedMotion) {
    gsap.from(el, { duration: 0.6, y: 20, ease: 'expo.out' });
}
```

---

### 6.14 Forced Colors (High Contrast) Failures (EN 301 549 clause 9.1.4.3, 11.7)

**What fails**: In Windows High Contrast mode (Forced Colors), custom CSS colors are overridden by system palette colors, which can make text invisible if color and background both resolve to the same system color.

**How the codebase is protected**: Both `css/a11y.css` and `ACCESSIBILITY_STYLES` include a `@media (forced-colors: active)` block adjusting focus rings to use `ButtonText` system color.

**How to fix new components**:

Every Shadow DOM component must include this block (already in `ACCESSIBILITY_STYLES` -- do not remove):
```css
@media (forced-colors: active) {
    :host { forced-color-adjust: auto; }
    :focus-visible { outline: 3px solid ButtonText; }
    /* Custom-colored buttons use system ButtonFace/ButtonText */
    .btn-primary { background: ButtonFace; color: ButtonText; border: 1px solid ButtonText; }
}
```

For elements using `background-image` or `background-color` to convey state (e.g., a colored dot for status), always pair with a text or icon alternative so the information persists when colors are overridden.

---

## 7. Regression Prevention Strategy

### Automated gate
The `accessibility` CI job runs on every push and pull request to `main`. A single axe-core violation at critical or serious impact level fails the build. Violations at moderate or minor impact are reported but do not fail (via the `disableRules` configuration).

### Monthly Lighthouse a11y re-run
The existing Lighthouse perf audit workflow (manual) should be extended to add `--only-categories=accessibility` at least once per month to track the score timeseries in [docs/artifacts/lighthouse_results.md](docs/artifacts/lighthouse_results.md). The current streak of 100/100 is the baseline.

### Pre-commit checklist for new components
Before merging a PR that adds or modifies a component:

1. Does the component import `${ACCESSIBILITY_STYLES}`?
2. Does every `<button>`, `<a>`, `<input>`, `<select>`, `<textarea>` have an accessible name (via `aria-label` using `this.tr()` or an associated `<label>`)?
3. Do all dynamic content regions have `aria-live` set up BEFORE any content is inserted?
4. Is every Icon-only button / SVG paired with an off-screen label or `aria-label`?
5. Are heading levels sequential (h2 -> h3, never h1 inside a component)?
6. Are all ARIA attribute values correct for the element's role?
7. Does `npm run test:a11y` pass locally with zero violations?

### Failure investigation workflow
When the `accessibility` CI job fails:

1. Download the `playwright-a11y-report` artifact from the failed GitHub Actions run.
2. Open `playwright-report/index.html` in a browser.
3. Navigate to the failing test. The test output includes the full violation detail from axe-core: impact, WCAG tags, help URL, element HTML, and fix summary.
4. Cross-reference the violation ID with section 6.x of this document for the exhaustive fix pattern.
5. Fix the violation, run `npm run test:a11y` locally, and push. The CI job must green before merge.

---

## 8. Running Tests Locally

```bash
# From the repository root
cd src/dashboard

# First run: install Playwright browser binaries
npx playwright install chromium

# Build production bundle and run all accessibility tests
npm run build && npm run test:a11y

# Run a single test file with verbose output
npx playwright test tests/accessibility.spec.ts --reporter=list

# Run a specific test by name
npx playwright test tests/accessibility.spec.ts --grep "WCAG 2.1 AA"

# Open Playwright UI (interactive, with re-run on save)
npx playwright test tests/accessibility.spec.ts --ui
```

Expected output on a clean 100/100 codebase:

```
Running 10 tests using 1 worker

  + WCAG 2.1 AA: zero violations across the full page (1.2s)
  + Color contrast: all text passes WCAG AA 4.5:1 in dark theme (0.8s)
  + Color contrast: all text passes WCAG AA 4.5:1 in light theme (0.9s)
  + ARIA: all roles, attributes, and required relationships are valid (0.7s)
  + Landmarks and headings: correct document skeleton for screen readers (0.7s)
  + Keyboard navigation: every interactive element receives focus via Tab (2.1s)
  + Skip link: present in DOM and targets #main-content landmark (0.5s)
  + Language: <html> element declares a lang attribute (0.4s)
  + Images: all non-decorative images and icons have text alternatives (0.6s)
  + Forms: every input has an associated label or aria-label (0.7s)

  10 passed (8.1s)
```

---

## 9. Coverage Assessment Against WCAG 2.1 AA

| WCAG SC | Description | Covered by | Note |
|:---|:---|:---|:---|
| 1.1.1 | Non-text Content | Test 9 | img-alt, svg-img-alt |
| 1.3.1 | Info and Relationships | Tests 1, 10 | label, semantic structure |
| 1.3.2 | Meaningful Sequence | Test 5 | DOM order |
| 1.3.3 | Sensory Characteristics | Test 1 (wcag2a) | Not color-only |
| 1.3.4 | Orientation | Test 1 (wcag21aa) | |
| 1.3.5 | Identify Input Purpose | Test 10 | autocomplete |
| 1.4.1 | Use of Color | Test 1 | |
| 1.4.3 | Contrast (Minimum) | Tests 2, 3 | Dark + light themes |
| 1.4.4 | Resize Text | Manual only | Not automatable |
| 1.4.5 | Images of Text | Test 9 | |
| 1.4.10 | Reflow | Manual only | Not automatable |
| 1.4.11 | Non-text Contrast | Tests 2, 3 | UI components |
| 1.4.12 | Text Spacing | Manual only | |
| 1.4.13 | Content on Hover or Focus | Manual only | |
| 2.1.1 | Keyboard | Tests 1, 6 | |
| 2.1.2 | No Keyboard Trap | Test 6 | Focus trap detection |
| 2.4.1 | Bypass Blocks | Tests 5, 7 | Skip link + landmarks |
| 2.4.2 | Page Titled | Test 1 | document-title |
| 2.4.3 | Focus Order | Test 6 | Tab order simulation |
| 2.4.4 | Link Purpose | Test 1 | link-name |
| 2.4.6 | Headings and Labels | Tests 1, 5 | |
| 2.4.7 | Focus Visible | Test 6 (structural) | Visual requires manual check |
| 3.1.1 | Language of Page | Test 8 | html-has-lang |
| 3.1.2 | Language of Parts | Test 1 (wcag2aa) | valid-lang |
| 3.3.1 | Error Identification | Test 10 | form error patterns |
| 3.3.2 | Labels or Instructions | Test 10 | |
| 4.1.1 | Parsing | Test 1 | duplicate-id |
| 4.1.2 | Name, Role, Value | Tests 1, 4, 10 | |
| 4.1.3 | Status Messages | Test 1 | aria-live regions |
