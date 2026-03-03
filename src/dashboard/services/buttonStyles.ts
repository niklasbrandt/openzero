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
		gap: 0.4em;
		border-radius: 0.5rem;
		border: 1px solid rgba(20, 184, 166, 0.25);
		padding: 0.38rem 0.85rem;
		font-size: 0.78rem;
		font-weight: 600;
		font-family: inherit;
		background: rgba(20, 184, 166, 0.1);
		color: #14B8A6;
		cursor: pointer;
		transition: background 0.2s, border-color 0.2s, color 0.2s, transform 0.1s;
		letter-spacing: 0.02em;
	}
	button:hover {
		background: rgba(20, 184, 166, 0.2);
		border-color: rgba(20, 184, 166, 0.6);
	}
	button:active { transform: scale(0.97); }
	button:disabled { opacity: 0.45; cursor: not-allowed; pointer-events: none; }
	button:focus-visible { outline: 2px solid #14B8A6; outline-offset: 2px; }

	/* Primary / filled — save, submit, add-confirm */
	.btn-primary, .save-btn {
		background: #14B8A6;
		color: #0a0f1e;
		border-color: #14B8A6;
		font-weight: 700;
	}
	.btn-primary:hover, .save-btn:hover {
		background: #0d9488;
		border-color: #0d9488;
		color: #0a0f1e;
	}

	/* Ghost / cancel — transparent, muted white */
	.btn-ghost, .cancel-btn {
		background: transparent;
		color: rgba(255, 255, 255, 0.6);
		border-color: rgba(255, 255, 255, 0.12);
	}
	.btn-ghost:hover, .cancel-btn:hover {
		background: rgba(255, 255, 255, 0.06);
		border-color: rgba(255, 255, 255, 0.25);
		color: rgba(255, 255, 255, 0.9);
	}

	/* Danger / destructive */
	.delete-btn, .btn-danger {
		background: rgba(239, 68, 68, 0.1);
		color: #f87171;
		border-color: rgba(239, 68, 68, 0.25);
	}
	.delete-btn:hover, .btn-danger:hover {
		background: rgba(239, 68, 68, 0.2);
		border-color: rgba(239, 68, 68, 0.5);
	}
	.delete-btn:focus-visible, .btn-danger:focus-visible { outline-color: #f87171; }

	/* Compact size modifier */
	.btn-sm {
		padding: 0.18rem 0.55rem;
		font-size: 0.72rem;
		border-radius: 0.35rem;
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
