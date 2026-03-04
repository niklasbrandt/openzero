/**
 * Shared thin scrollbar styles for Shadow DOM components.
 *
 * Provides a minimal 4px scrollbar that matches the glass UI.
 * Apply to scrollable containers by scoping the selector.
 *
 * Usage:
 *   import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';
 *   // In template: ${SCROLLBAR_STYLES}
 *   // Then scope: .my-list { overflow-y: auto; }
 *   // The :host styles apply to all scrollable areas in the shadow root.
 */
export const SCROLLBAR_STYLES = `
	::-webkit-scrollbar {
		width: 4px;
	}

	::-webkit-scrollbar-track {
		background: transparent;
	}

	::-webkit-scrollbar-thumb {
		background: rgba(255, 255, 255, 0.1);
		border-radius: 4px;
	}

	::-webkit-scrollbar-thumb:hover {
		background: rgba(255, 255, 255, 0.2);
	}
`;
