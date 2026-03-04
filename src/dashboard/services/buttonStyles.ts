/**
 * Shared button design system for Shadow DOM components.
 *
 * Import and interpolate ${BUTTON_STYLES} at the top of each
 * component's CSS <style> block. Because Shadow DOM is fully
 * encapsulated, global style.css rules never reach inside
 * components — this constant is the single source of truth
 * for every button variant used across the dashboard.
 *
 * Variants:
 *   default       — teal ghost (navigation, filters, misc)
 *   .btn-primary / .save-btn  — filled teal (save, submit, add)
 *   .btn-ghost   / .cancel-btn — transparent white (cancel, secondary)
 *   .delete-btn  / .btn-danger — soft red (destructive actions)
 *   .btn-sm                    — compact size modifier
 */
export const BUTTON_STYLES = `
	button {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		border-radius: var(--radius-md, 0.5rem);
		border: 1px solid var(--border-accent, rgba(20, 184, 166, 0.25));
		padding: 0.38rem 0.85rem;
		font-size: 0.78rem;
		font-weight: 600;
		font-family: inherit;
		background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.1);
		color: var(--accent-color, #14B8A6);
		cursor: pointer;
		transition: background var(--duration-base, 0.3s), border-color var(--duration-base, 0.3s), color var(--duration-base, 0.3s), transform var(--duration-instant, 0.1s);
		letter-spacing: 0.02em;
	}
	button:hover {
		background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
		border-color: rgba(var(--accent-color-rgb, 20, 184, 166), 0.6);
	}
	button:active { transform: scale(0.97); }
	button:disabled { opacity: 0.45; cursor: not-allowed; pointer-events: none; }
	button:focus-visible { outline: 2px solid var(--accent-color, #14B8A6); outline-offset: 2px; }

	/* Primary / filled — save, submit, add-confirm */
	.btn-primary, .save-btn {
		background: var(--accent-color, #14B8A6);
		color: var(--bg-body, #0a0f1e);
		border-color: var(--accent-color, #14B8A6);
		font-weight: 700;
	}
	.btn-primary:hover, .save-btn:hover {
		background: color-mix(in srgb, var(--accent-color, #14B8A6) 85%, #000);
		border-color: color-mix(in srgb, var(--accent-color, #14B8A6) 85%, #000);
		color: var(--bg-body, #0a0f1e);
	}

	/* Ghost / cancel — transparent, muted white */
	.btn-ghost, .cancel-btn {
		background: transparent;
		color: var(--text-secondary, rgba(255, 255, 255, 0.6));
		border-color: var(--border-medium, rgba(255, 255, 255, 0.12));
	}
	.btn-ghost:hover, .cancel-btn:hover {
		background: var(--surface-hover, rgba(255, 255, 255, 0.06));
		border-color: rgba(255, 255, 255, 0.25);
		color: rgba(255, 255, 255, 0.9);
	}

	/* Danger / destructive */
	.delete-btn, .btn-danger {
		background: rgba(var(--color-danger-rgb, 239, 68, 68), 0.1);
		color: var(--color-danger-light, #f87171);
		border-color: rgba(var(--color-danger-rgb, 239, 68, 68), 0.25);
	}
	.delete-btn:hover, .btn-danger:hover {
		background: rgba(var(--color-danger-rgb, 239, 68, 68), 0.2);
		border-color: rgba(var(--color-danger-rgb, 239, 68, 68), 0.5);
	}
	.delete-btn:focus-visible, .btn-danger:focus-visible { outline-color: var(--color-danger-light, #f87171); }

	/* Compact size modifier */
	.btn-sm {
		padding: 0.18rem 0.55rem;
		font-size: 0.72rem;
		border-radius: var(--radius-sm, 0.35rem);
	}

	@media (prefers-reduced-motion: reduce) {
		button { transition: none; }
		button:active { transform: none; }
	}
	@media (forced-colors: active) {
		button { border: 2px solid ButtonText; }
		.btn-primary, .save-btn { background: ButtonText; color: ButtonFace; }
	}
`;
