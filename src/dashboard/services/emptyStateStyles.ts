/**
 * Shared empty state styles for Shadow DOM components.
 *
 * Provides a centered, subtle placeholder for empty data areas.
 *
 * Markup convention:
 *   <p class="empty-state">No items to display</p>
 *
 * Usage:
 *   import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
 *   // In template: ${EMPTY_STATE_STYLES}
 */
export const EMPTY_STATE_STYLES = `
	.empty-state {
		/* Use text-secondary (0.7 opacity) rather than text-faint because empty-state
		   messages convey status/error information and must meet WCAG AA 4.5:1. */
		color: var(--text-secondary, rgba(255, 255, 255, 0.7));
		font-size: 0.85rem;
		font-style: italic;
		text-align: center;
		padding: 1.5rem;
	}
`;
