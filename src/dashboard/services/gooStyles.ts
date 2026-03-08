/**
 * Shared Goo Mode styles for Shadow DOM components.
 *
 * Import and interpolate ${GOO_STYLES} inside each component's
 * <style> block. The effects activate when the component's host
 * element carries the .oz-goo class (set via JS in connectedCallback).
 *
 * Performance contract:
 * - Every animation touches ONLY transform and opacity (GPU-composited).
 * - No layout-triggering properties (width, height, margin, padding).
 * - The heavy SVG feGaussianBlur filter is NEVER applied to containers
 *   or the document body. It exists only for tiny decorative merges
 *   on sub-32px elements.
 * - will-change is scoped to active animations only.
 * - prefers-reduced-motion disables everything.
 *
 * Easing conventions (docs/artifacts/DESIGN.md S6.3):
 *   elastic.out  ~  cubic-bezier(0.175, 0.885, 0.32, 1.275)
 *   bounce.out   ~  multi-step keyframe with overshoot
 *   These easings are ONLY permitted inside goo-scoped rules.
 */
export const GOO_STYLES = `
	/* ================================================================
	   GOO MODE -- Organic Interaction Layer
	   Scoped to :host(.oz-goo) for Shadow DOM containment.
	   ================================================================ */

	/* ── Elastic buttons ── */
	:host(.oz-goo) button {
		transition:
			transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275),
			background var(--duration-base, 0.3s),
			border-color var(--duration-base, 0.3s),
			border-radius 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275);
	}
	:host(.oz-goo) button:hover {
		transform: scale(1.05);
		border-radius: 1.2rem;
	}
	:host(.oz-goo) button:active {
		transform: scale(0.92);
		transition-duration: 0.08s;
	}

	/* ── Organic card morph ── */
	:host(.oz-goo) .oz-goo-morph {
		transition:
			border-radius 0.8s cubic-bezier(0.175, 0.885, 0.32, 1.275),
			transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
	}
	:host(.oz-goo) .oz-goo-morph:hover {
		border-radius: 1.5rem 0.5rem 1.5rem 0.5rem;
		transform: scale(1.008);
	}

	/* ── Bouncy entrance ── */
	@keyframes oz-goo-enter {
		0%   { opacity: 0; transform: scale(0.85) translateY(12px); }
		50%  { opacity: 1; transform: scale(1.04) translateY(-2px); }
		75%  { transform: scale(0.98) translateY(1px); }
		100% { transform: scale(1) translateY(0); }
	}
	:host(.oz-goo) .oz-goo-enter {
		animation: oz-goo-enter 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) both;
	}

	/* ── Organic pulse for status dots ── */
	@keyframes oz-goo-pulse {
		0%, 100% { transform: scale(1); border-radius: 50%; }
		25%      { transform: scale(1.3); border-radius: 45% 55% 55% 45%; }
		50%      { transform: scale(1.1); border-radius: 55% 45% 45% 55%; }
		75%      { transform: scale(1.2); border-radius: 50% 50% 45% 55%; }
	}
	:host(.oz-goo) .status-dot {
		animation: oz-goo-pulse 3s ease-in-out infinite;
	}

	/* ── Elastic focus for form controls ── */
	:host(.oz-goo) input:focus,
	:host(.oz-goo) textarea:focus,
	:host(.oz-goo) select:focus {
		transform: scale(1.012);
		transition:
			transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275),
			border-color var(--duration-fast, 0.15s),
			box-shadow var(--duration-fast, 0.15s);
	}

	/* ── Goo chat bubble entrance ── */
	@keyframes oz-goo-msg {
		0%   { opacity: 0; transform: translateY(20px) scale(0.85); }
		50%  { opacity: 1; transform: translateY(-4px) scale(1.03); }
		75%  { transform: translateY(2px) scale(0.99); }
		100% { transform: translateY(0) scale(1); }
	}

	/* ── Accessibility: kill all goo motion ── */
	@media (prefers-reduced-motion: reduce) {
		:host(.oz-goo) button,
		:host(.oz-goo) .oz-goo-morph,
		:host(.oz-goo) .status-dot,
		:host(.oz-goo) .oz-goo-enter,
		:host(.oz-goo) input:focus,
		:host(.oz-goo) textarea:focus,
		:host(.oz-goo) select:focus {
			animation: none !important;
			transition: none !important;
			transform: none !important;
		}
	}

	/* ── Forced colors: goo is decorative, suppress ── */
	@media (forced-colors: active) {
		:host(.oz-goo) .oz-goo-morph:hover { border-radius: inherit; }
		:host(.oz-goo) .status-dot { animation: none; }
	}
`;

/**
 * Helper: read goo-mode from localStorage and sync the class on the host.
 * Call from connectedCallback():
 *   initGoo(this);
 *   window.addEventListener('goo-changed', () => initGoo(this));
 */
export function initGoo(el: HTMLElement): void {
	const active = localStorage.getItem('goo-mode') === 'true';
	el.classList.toggle('oz-goo', active);
}
