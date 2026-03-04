/**
 * Shared form input styles for Shadow DOM components.
 *
 * Provides consistent styling for input, textarea, select, and label
 * elements. Uses CSS custom property tokens from :root for theming.
 *
 * Usage:
 *   import { FORM_INPUT_STYLES } from '../services/formInputStyles';
 *   // In template: ${FORM_INPUT_STYLES}
 */
export const FORM_INPUT_STYLES = `
	input, textarea, select {
		background: var(--surface-input, rgba(0, 0, 0, 0.2));
		border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
		border-radius: var(--radius-lg, 0.75rem);
		padding: 0.6rem 1rem;
		color: var(--text-primary, #fff);
		font-family: inherit;
		font-size: 0.9rem;
		outline: none;
		width: 100%;
		box-sizing: border-box;
		transition: border-color var(--duration-base, 0.3s), background var(--duration-base, 0.3s), box-shadow var(--duration-base, 0.3s);
	}

	input:focus, textarea:focus, select:focus {
		border-color: var(--border-accent-focus, rgba(20, 184, 166, 0.4));
		background: var(--surface-input-focus, rgba(0, 0, 0, 0.28));
		box-shadow: 0 0 20px rgba(var(--accent-color-rgb, 20, 184, 166), 0.08);
	}

	input::placeholder, textarea::placeholder {
		color: var(--text-faint, rgba(255, 255, 255, 0.2));
	}

	input.field-error, textarea.field-error {
		border-color: rgba(var(--color-danger-rgb, 239, 68, 68), 0.5);
		background: rgba(var(--color-danger-rgb, 239, 68, 68), 0.05);
	}

	textarea {
		resize: vertical;
		min-height: 72px;
		line-height: 1.5;
	}

	select {
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='rgba(255,255,255,0.4)' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 0.75rem center;
		padding-right: 2rem;
	}

	select option {
		background: hsla(240, 28%, 14%, 1);
		color: var(--text-primary, #fff);
	}

	label {
		font-size: 0.72rem;
		font-weight: 600;
		color: var(--text-muted, rgba(255, 255, 255, 0.4));
		text-transform: uppercase;
		letter-spacing: 0.06em;
		display: block;
		margin-bottom: 0.35rem;
	}
`;
