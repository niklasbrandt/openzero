/**
 * Shared status indicator styles for Shadow DOM components.
 *
 * Provides status dots (small colored circles) and semantic
 * color classes for health/state indicators. Uses CSS custom
 * property tokens from :root for consistent theming.
 *
 * Markup convention:
 *   <span class="status-dot online"></span>
 *   <span class="status-dot warning"></span>
 *   <span class="status-dot critical"></span>
 *
 * Usage:
 *   import { STATUS_STYLES } from '../services/statusStyles';
 *   // In template: ${STATUS_STYLES}
 */

/* ── Settings ── */
const DOT_SIZE = '8px';
const DOT_GLOW_SPREAD = '6px';

export const STATUS_STYLES = `
	.status-dot {
		width: ${DOT_SIZE};
		height: ${DOT_SIZE};
		border-radius: 50%;
		flex-shrink: 0;
	}

	/* ── Healthy / online / excellent ── */
	.status-dot.online,
	.status-dot.excellent,
	.status-dot.healthy {
		background: var(--accent-color, #14B8A6);
		box-shadow: 0 0 ${DOT_GLOW_SPREAD} rgba(var(--accent-color-rgb, 20, 184, 166), 0.4);
	}

	/* ── Good / success ── */
	.status-dot.good {
		background: var(--color-success, #22c55e);
		box-shadow: 0 0 ${DOT_GLOW_SPREAD} rgba(var(--color-success-rgb, 34, 197, 94), 0.4);
	}

	/* ── Warning / moderate / degraded ── */
	.status-dot.warning,
	.status-dot.moderate,
	.status-dot.limited {
		background: var(--color-warning, #eab308);
		box-shadow: 0 0 ${DOT_GLOW_SPREAD} rgba(var(--color-warning-rgb, 234, 179, 8), 0.4);
	}

	/* ── Critical / offline / error / slow ── */
	.status-dot.critical,
	.status-dot.offline,
	.status-dot.error,
	.status-dot.slow {
		background: var(--color-danger, #ef4444);
		box-shadow: 0 0 ${DOT_GLOW_SPREAD} rgba(var(--color-danger-rgb, 239, 68, 68), 0.4);
	}
`;
