/**
 * Shared accessibility utilities for Shadow DOM components.
 *
 * Provides screen-reader-only text, reduced-motion suppression,
 * and forced-colors compatibility. Import and interpolate
 * ${ACCESSIBILITY_STYLES} in every component's <style> block.
 *
 * Standards: WCAG 2.1 AA / EN 301 549
 */
export const ACCESSIBILITY_STYLES = `
	/* ── Screen-reader-only (WCAG 1.3.1, 1.1.1) ── */
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}

	/* ── Reduced motion (WCAG 2.3.3 / EN 301 549 §9.2.3.3) ── */
	@media (prefers-reduced-motion: reduce) {
		*,
		*::before,
		*::after {
			animation-duration: 0.01ms !important;
			animation-iteration-count: 1 !important;
			transition-duration: 0.01ms !important;
		}
	}

	/* ── Forced colors (EN 301 549 §9.1.4.11) ── */
	@media (forced-colors: active) {
		:focus-visible {
			outline: 3px solid ButtonText;
		}
	}
`;
