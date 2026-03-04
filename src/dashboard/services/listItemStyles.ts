/**
 * Shared list item / card-row styles for Shadow DOM components.
 *
 * Provides a consistent row pattern for lists of items with
 * subtle glass-like backgrounds and hover states.
 *
 * Markup convention:
 *   <div class="list-item">
 *     <span class="list-item-title">Name</span>
 *     <span class="list-item-meta">Secondary info</span>
 *   </div>
 *
 * Usage:
 *   import { LIST_ITEM_STYLES } from '../services/listItemStyles';
 *   // In template: ${LIST_ITEM_STYLES}
 */
export const LIST_ITEM_STYLES = `
	.list-item {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.75rem 1rem;
		background: var(--surface-card, rgba(255, 255, 255, 0.03));
		border-radius: var(--radius-lg, 0.75rem);
		border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
		transition: background var(--duration-base, 0.3s), border-color var(--duration-base, 0.3s);
	}

	.list-item:hover {
		background: var(--surface-card-hover, rgba(255, 255, 255, 0.05));
		border-color: var(--border-medium, rgba(255, 255, 255, 0.12));
	}

	.list-item-title {
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--text-primary, #fff);
	}

	.list-item-meta {
		font-size: 0.72rem;
		color: var(--text-muted, rgba(255, 255, 255, 0.4));
	}

	@media (prefers-reduced-motion: reduce) {
		.list-item { transition: none; }
	}
`;
