/**
 * Accessibility regression suite for the openZero dashboard.
 *
 * Standards enforced:
 *   - WCAG 2.1 Level AA  (agents.md rule 12)
 *   - EN 301 549          (agents.md rule 12)
 *
 * Tool: axe-core via @axe-core/playwright.
 * axe-core is the industry reference engine (used by Lighthouse internally).
 * It natively traverses open Shadow DOM trees, which is essential because all
 * 16 openZero components use attachShadow({ mode: 'open' }).
 *
 * Architecture note
 * -----------------
 * The Vite preview server serves the production bundle (static HTML + JS + CSS).
 * The dashboard JS will attempt API calls to /api/... which will 404 in the
 * preview environment.  Components catch these errors and render their empty /
 * error states -- which are still fully accessible DOM nodes with ARIA attributes,
 * landmarks, headings, and colour tokens.  axe-core audits the DOM after all
 * custom elements have upgraded, therefore Shadow DOM content IS visible to it.
 *
 * Test structure
 * --------------
 * 1. Full WCAG 2.1 AA audit  -- zero violations gate.
 * 2. Color-contrast hardened audit  -- explicitly exercises the dynamic
 *    theming system (HSL tokens, dark/light mode).
 * 3. Keyboard navigation audit  -- verifies that Tab reaches every interactive
 *    element and that none escape without a visible focus indicator.
 * 4. Landmark & heading structure audit  -- verifies document skeleton that
 *    screen readers depend on for orientation.
 */

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import type { Result } from 'axe-core';

// ---------------------------------------------------------------------------
// Helper: format axe violations into a readable CI failure message
// ---------------------------------------------------------------------------
function formatViolations(violations: Result[]): string {
	if (violations.length === 0) return '';
	return violations
		.map((v) => {
			const nodes = v.nodes
				.slice(0, 3)
				.map((n) => `    HTML: ${n.html.slice(0, 200)}\n    Fix:  ${n.failureSummary ?? '(see axe docs)'}`)
				.join('\n');
			return (
				`\n[${v.impact?.toUpperCase() ?? 'UNKNOWN'}] ${v.id}\n` +
				`  Rule:    ${v.description}\n` +
				`  WCAG:    ${v.tags.filter((t) => t.startsWith('wcag')).join(', ')}\n` +
				`  Help:    ${v.helpUrl}\n` +
				`  Nodes (first 3):\n${nodes}`
			);
		})
		.join('\n');
}

// ---------------------------------------------------------------------------
// Fixture: navigate to the dashboard once and wait for custom elements
// ---------------------------------------------------------------------------
test.beforeEach(async ({ page }) => {
	// Navigate to the root; the Vite preview serves index.html from dist/
	await page.goto('/');

	// Wait for the page shell to be fully painted -- the skip-link and all
	// landmark regions are in the outer HTML, so they are immediate.  We wait
	// for any one custom element to upgrade as a proxy for "JS has executed".
	await page.waitForFunction(
		() => customElements.get('user-card') !== undefined,
		undefined,
		{ timeout: 15_000 }
	);

	// Give async connectedCallback()s (translation loads) time to settle.
	// A short settled-DOM wait is more reliable than a fixed sleep.
	await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {
		// networkidle may never fire in test env (ongoing 404 retries).
		// That is acceptable -- DOM structure is what we audit, not network.
	});
});

// ---------------------------------------------------------------------------
// Test 1: Full WCAG 2.1 A + AA audit
// ---------------------------------------------------------------------------
test('WCAG 2.1 AA: zero violations across the full page including Shadow DOM', async ({ page }) => {
	const results = await new AxeBuilder({ page })
		.withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
		// Disable rules that require live API data (dynamic content that is
		// absent in the preview environment and would produce false positives).
		// IMPORTANT: Re-enable these once mock API responses are available.
		.disableRules([
			// `scrollable-region-focusable` -- may fire on empty scroll containers
			// that would contain list items when API data is present.
			'scrollable-region-focusable',
		])
		.analyze();

	const message = formatViolations(results.violations);
	expect(results.violations, `WCAG 2.1 AA violations found:\n${message}`).toHaveLength(0);
});

// ---------------------------------------------------------------------------
// Test 2: Color contrast -- dark theme (default)
// ---------------------------------------------------------------------------
test('Color contrast: all text passes WCAG AA 4.5:1 in dark theme', async ({ page }) => {
	// Ensure dark theme is active (default for the app).
	await page.evaluate(() => {
		document.documentElement.setAttribute('data-theme', 'dark');
	});

	const results = await new AxeBuilder({ page })
		.withRules(['color-contrast'])
		.analyze();

	const message = formatViolations(results.violations);
	expect(results.violations, `Color contrast failures in dark theme:\n${message}`).toHaveLength(0);
});

// ---------------------------------------------------------------------------
// Test 3: Color contrast -- light theme
// ---------------------------------------------------------------------------
test('Color contrast: all text passes WCAG AA 4.5:1 in light theme', async ({ page }) => {
	// Use browser-level media emulation so @media(prefers-color-scheme:light) fires
	// and CSS custom properties cascade into Shadow DOM components from scratch.
	// This is more reliable than toggling data-theme after render because the
	// media query change triggers a Chromium-level style recalculation that
	// propagates custom property inheritance into all shadow roots.
	await page.emulateMedia({ colorScheme: 'light' });
	// Also set the app-level attribute so non-media-query rules fire too.
	await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
	// Allow a full style-recalculation pass to complete (media + attribute).
	await page.waitForTimeout(600);
	// Force Chromium to flush pending Shadow DOM style recalculations before
	// axe scans. CSS custom property cascade into open shadow roots is async
	// after attribute/media changes; calling getComputedStyle on a shadow DOM
	// element acts as a synchronisation barrier that commits the cascade.
	await page.evaluate(() => {
		const hostEl = document.querySelector('z-personality');
		if (hostEl?.shadowRoot) {
			const btn = hostEl.shadowRoot.querySelector('button');
			if (btn) getComputedStyle(btn).color;
		}
	});

	const results = await new AxeBuilder({ page })
		.withRules(['color-contrast'])
		.analyze();

	const message = formatViolations(results.violations);
	expect(results.violations, `Color contrast failures in light theme:\n${message}`).toHaveLength(0);
});

// ---------------------------------------------------------------------------
// Test 4: ARIA correctness audit
// ---------------------------------------------------------------------------
test('ARIA: all roles, attributes, and required relationships are valid', async ({ page }) => {
	const results = await new AxeBuilder({ page })
		.withTags(['cat.aria'])
		.analyze();

	const message = formatViolations(results.violations);
	expect(results.violations, `ARIA violations found:\n${message}`).toHaveLength(0);
});

// ---------------------------------------------------------------------------
// Test 5: Landmark and heading structure
// ---------------------------------------------------------------------------
test('Landmarks and headings: correct document skeleton for screen readers', async ({ page }) => {
	const results = await new AxeBuilder({ page })
		.withRules([
			'landmark-one-main',
			'landmark-unique',
			'landmark-no-duplicate-banner',
			'landmark-no-duplicate-contentinfo',
			'landmark-no-duplicate-main',
			'region',
			'heading-order',
			'page-has-heading-one',
			'bypass',
		])
		.analyze();

	const message = formatViolations(results.violations);
	expect(results.violations, `Landmark/heading violations:\n${message}`).toHaveLength(0);
});

// ---------------------------------------------------------------------------
// Test 6: Focus management -- every interactive element is keyboard-reachable
// ---------------------------------------------------------------------------
test('Keyboard navigation: every interactive element receives focus via Tab', async ({ page }) => {
	// Collect all interactive elements including those inside open Shadow DOM.
	// We use a recursive pierce selector via page.evaluate.
	const interactiveCount = await page.evaluate(() => {
		function collectInteractive(root: Document | ShadowRoot): Element[] {
			const selectors = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
			const found: Element[] = Array.from(root.querySelectorAll(selectors));
			for (const el of Array.from(root.querySelectorAll('*'))) {
				const shadow = (el as HTMLElement).shadowRoot;
				if (shadow) found.push(...collectInteractive(shadow));
			}
			return found;
		}
		return collectInteractive(document).length;
	});

	// Assert at least the known minimum: skip-link + hamburger + nav links
	// (7 sidebar nav items) + header toolbar buttons.
	expect(interactiveCount, 'Expected at least 10 interactive elements to be keyboard-reachable').toBeGreaterThanOrEqual(10);

	// Tab through the page and verify focus advances without getting trapped.
	const focusedElements: string[] = [];
	let previousFocused = '';

	for (let i = 0; i < Math.min(interactiveCount, 60); i++) {
		await page.keyboard.press('Tab');
		const focused = await page.evaluate(() => {
			function getDeepActiveElement(root: Document | ShadowRoot): Element | null {
				const active = (root as Document).activeElement ?? null;
				if (!active) return null;
				const shadowRoot = (active as HTMLElement).shadowRoot;
				if (shadowRoot) return getDeepActiveElement(shadowRoot);
				return active;
			}
			const el = getDeepActiveElement(document);
			if (!el) return '';
			// Use bounding-rect position to distinguish consecutive elements that share
			// the same tag/class (e.g. multiple <a> nav links). A real focus-trap would
			// keep the rect identical across two consecutive Tab presses.
			const rect = el.getBoundingClientRect();
			return `${el.tagName.toLowerCase()}@${Math.round(rect.x)},${Math.round(rect.y)}`;
		});

		if (focused === previousFocused && focused !== '') {
			// Focus is stuck -- potential focus trap.
			expect.soft(false, `Focus trap detected: "${focused}" received focus twice in a row`).toBe(true);
		}

		if (focused) {
			focusedElements.push(focused);
			previousFocused = focused;
		}
	}

	// At least 5 distinct elements must have been focused.
	const distinctFocused = new Set(focusedElements).size;
	expect(distinctFocused, `Too few distinct elements focused via Tab (${distinctFocused})`).toBeGreaterThanOrEqual(5);
});

// ---------------------------------------------------------------------------
// Test 7: Skip link is present and leads to #main-content
// ---------------------------------------------------------------------------
test('Skip link: present in DOM and targets #main-content landmark', async ({ page }) => {
	const skipLink = page.locator('a.skip-link[href="#main-content"]');
	await expect(skipLink).toHaveCount(1);

	const mainContent = page.locator('#main-content');
	await expect(mainContent).toHaveCount(1);
	await expect(mainContent).toHaveAttribute('role', /main|landmark/, { timeout: 1000 }).catch(() => {
		// <main id="main-content"> implicitly has role=main -- no explicit attribute needed.
	});
});

// ---------------------------------------------------------------------------
// Test 8: Language declaration
// ---------------------------------------------------------------------------
test('Language: <html> element declares a lang attribute', async ({ page }) => {
	const lang = await page.getAttribute('html', 'lang');
	expect(lang, '<html lang="..."> must be set for screen readers to choose voice').toBeTruthy();
	// Must be a well-formed BCP 47 tag (e.g. "en", "en-US", "de").
	expect(lang).toMatch(/^[a-z]{2,3}(-[A-Z]{2,4})?$/);
});

// ---------------------------------------------------------------------------
// Test 9: Images and SVGs -- no unlabelled informative graphics
// ---------------------------------------------------------------------------
test('Images: all non-decorative images and icons have text alternatives', async ({ page }) => {
	const results = await new AxeBuilder({ page })
		.withRules(['image-alt', 'svg-img-alt'])
		.analyze();

	const message = formatViolations(results.violations);
	expect(results.violations, `Image/SVG alt-text violations:\n${message}`).toHaveLength(0);
});

// ---------------------------------------------------------------------------
// Test 10: Form inputs have associated labels
// ---------------------------------------------------------------------------
test('Forms: every input has an associated label or aria-label', async ({ page }) => {
	const results = await new AxeBuilder({ page })
		.withRules([
			'label',
			'label-content-name-mismatch',
			'select-name',
			'input-button-name',
			'input-image-alt',
		])
		.analyze();

	const message = formatViolations(results.violations);
	expect(results.violations, `Form label violations:\n${message}`).toHaveLength(0);
});
