/**
 * Shared badge / pill / tag styles for Shadow DOM components.
 *
 * Provides compact indicator badges with semantic color variants.
 * Uses CSS custom property tokens from :root for theming.
 *
 * Markup convention:
 *   <span class="badge">Default</span>
 *   <span class="badge badge-accent">Teal</span>
 *   <span class="badge badge-info">Blue</span>
 *   <span class="badge badge-success">Green</span>
 *   <span class="badge badge-warning">Amber</span>
 *   <span class="badge badge-danger">Red</span>
 *
 * Usage:
 *   import { BADGE_STYLES } from '../services/badgeStyles';
 *   // In template: ${BADGE_STYLES}
 */
export const BADGE_STYLES = `
	.badge {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.65rem;
		font-weight: 600;
		padding: 0.15rem 0.5rem;
		border-radius: var(--radius-pill, 9999px);
		letter-spacing: 0.05em;
		text-transform: uppercase;
		white-space: nowrap;
		background: var(--surface-card, rgba(255, 255, 255, 0.03));
		color: var(--text-muted, rgba(255, 255, 255, 0.4));
		border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
	}

	.badge-accent {
		background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.12);
		color: var(--accent-color, hsla(173, 80%, 40%, 1));
		border-color: rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
	}

	.badge-info {
		background: rgba(var(--color-info-rgb, 59, 130, 246), 0.12);
		color: var(--color-info, hsla(217, 91%, 60%, 1));
		border-color: rgba(var(--color-info-rgb, 59, 130, 246), 0.2);
	}

	.badge-success {
		background: rgba(var(--color-success-rgb, 34, 197, 94), 0.12);
		color: var(--color-success-light, hsla(142, 69%, 58%, 1));
		border-color: rgba(var(--color-success-rgb, 34, 197, 94), 0.2);
	}

	.badge-warning {
		background: rgba(var(--color-warning-rgb, 234, 179, 8), 0.12);
		color: var(--color-warning, hsla(45, 93%, 47%, 1));
		border-color: rgba(var(--color-warning-rgb, 234, 179, 8), 0.2);
	}

	.badge-danger {
		background: rgba(var(--color-danger-rgb, 239, 68, 68), 0.12);
		color: var(--color-danger-light, hsla(0, 91%, 71%, 1));
		border-color: rgba(var(--color-danger-rgb, 239, 68, 68), 0.2);
	}
`;
