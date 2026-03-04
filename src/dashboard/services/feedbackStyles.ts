/**
 * Shared feedback toast styles for Shadow DOM components.
 *
 * Provides success/error/info feedback messages with subtle
 * color-coded backgrounds. Visibility is toggled via the
 * .visible class.
 *
 * Markup convention:
 *   <div class="feedback success" role="status" aria-live="polite">
 *     Saved successfully
 *   </div>
 *   <div class="feedback error" role="alert">
 *     Something went wrong
 *   </div>
 *
 * Usage:
 *   import { FEEDBACK_STYLES } from '../services/feedbackStyles';
 *   // In template: ${FEEDBACK_STYLES}
 */
export const FEEDBACK_STYLES = `
	.feedback {
		font-size: 0.78rem;
		padding: 0.5rem 0.75rem;
		border-radius: var(--radius-md, 0.5rem);
		margin-top: 0.5rem;
		opacity: 0;
		transform: translateY(4px);
		transition: opacity var(--duration-base, 0.3s), transform var(--duration-base, 0.3s);
		pointer-events: none;
	}

	.feedback.visible {
		opacity: 1;
		transform: translateY(0);
		pointer-events: auto;
	}

	.feedback.success {
		background: rgba(var(--color-success-rgb, 34, 197, 94), 0.1);
		border: 1px solid rgba(var(--color-success-rgb, 34, 197, 94), 0.2);
		color: var(--color-success-light, hsla(142, 69%, 58%, 1));
	}

	.feedback.error {
		background: rgba(var(--color-danger-rgb, 239, 68, 68), 0.1);
		border: 1px solid rgba(var(--color-danger-rgb, 239, 68, 68), 0.2);
		color: var(--color-danger-light, hsla(0, 91%, 71%, 1));
	}

	.feedback.info {
		background: rgba(var(--color-info-rgb, 59, 130, 246), 0.1);
		border: 1px solid rgba(var(--color-info-rgb, 59, 130, 246), 0.2);
		color: var(--color-info, hsla(217, 91%, 60%, 1));
	}

	@media (prefers-reduced-motion: reduce) {
		.feedback { transition: none; transform: none; }
	}
`;
