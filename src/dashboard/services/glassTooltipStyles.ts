/**
 * Shared glass tooltip styles for Shadow DOM components.
 *
 * Provides a real-DOM tooltip with backdrop-filter glassmorphism.
 * Uses CSS custom property tokens from :root for theming.
 *
 * Markup convention:
 *   <span class="has-tip" tabindex="0">
 *     Trigger text
 *     <span class="glass-tooltip">Tooltip content</span>
 *   </span>
 *
 * Usage:
 *   import { GLASS_TOOLTIP_STYLES } from '../services/glassTooltipStyles';
 *   // In template: ${GLASS_TOOLTIP_STYLES}
 */
export const GLASS_TOOLTIP_STYLES = `
	.has-tip {
		position: relative;
	}

	.glass-tooltip {
		position: absolute;
		bottom: calc(100% + 10px);
		left: 0;
		background: var(--tooltip-bg, rgba(255, 255, 255, 0.06));
		backdrop-filter: blur(var(--tooltip-blur, 32px)) saturate(var(--tooltip-saturate, 1.6)) brightness(1.1);
		-webkit-backdrop-filter: blur(var(--tooltip-blur, 32px)) saturate(var(--tooltip-saturate, 1.6)) brightness(1.1);
		color: var(--tooltip-text, rgba(255, 255, 255, 0.92));
		font-size: 0.72rem;
		line-height: 1.5;
		padding: 0.6rem 0.85rem;
		border-radius: 0.6rem;
		border: 1px solid var(--tooltip-border, rgba(255, 255, 255, 0.18));
		white-space: normal;
		width: max-content;
		max-width: 280px;
		pointer-events: none;
		opacity: 0;
		transition: all 0.24s var(--ease-snap, cubic-bezier(0.23, 1, 0.32, 1));
		z-index: 1000;
		box-shadow: var(--tooltip-shadow, 0 8px 32px rgba(0, 0, 0, 0.35));
	}

	.has-tip:hover > .glass-tooltip,
	.has-tip:focus-visible > .glass-tooltip {
		opacity: 1;
		transform: translateY(-4px);
	}

	/* Suppress parent tooltip when a nested child is hovered */
	.has-tip:has(.has-tip:hover) > .glass-tooltip,
	.has-tip:has(.has-tip:focus-visible) > .glass-tooltip {
		opacity: 0 !important;
	}
`;
