/**
 * Shared section header styles for Shadow DOM components.
 *
 * Provides h2 heading with inline icon badge and subtitle.
 * The icon gradient colors are component-specific — pass them
 * via CSS custom properties or override .h-icon background
 * after interpolating this module.
 *
 * Usage:
 *   import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
 *   // In template: ${SECTION_HEADER_STYLES}
 *   // Override icon gradient per component:
 *   //   .h-icon { background: linear-gradient(135deg, var(--accent-color), var(--accent-secondary)); }
 *
 * Markup convention:
 *   <h2>
 *     <span class="h-icon" aria-hidden="true">EMOJI_OR_SVG</span>
 *     Title Text
 *     <span class="subtitle">Subtitle</span>
 *   </h2>
 */
export const SECTION_HEADER_STYLES = `
	h2 {
		font-size: 1.5rem;
		font-weight: bold;
		margin: 0 0 1.5rem 0;
		color: var(--text-primary, #fff);
		letter-spacing: 0.02em;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		overflow-wrap: break-word;
		word-break: break-word;
		min-width: 0;
	}

	.h-icon {
		display: inline-flex;
		width: 28px;
		height: 28px;
		background: linear-gradient(135deg, var(--accent-color, #14B8A6) 0%, var(--accent-secondary, #0066FF) 100%);
		border-radius: 0.4rem;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.subtitle {
		font-size: 0.65rem;
		font-weight: 400;
		color: var(--text-faint, rgba(255, 255, 255, 0.3));
		margin-left: 0.5rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
	}
`;
