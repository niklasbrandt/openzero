import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';

export class DecisionCapture extends HTMLElement {
	private t: Record<string, string> = {};
	private _open = false;
	private _previousFocus: Element | null = null;

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	private async loadTranslations() {
		if (window.__z_translations) { this.t = window.__z_translations; return; }
		try {
			await window.__z_translations_ready;
			if (window.__z_translations) { this.t = window.__z_translations; return; }
			const res = await fetch('/api/dashboard/translations');
			if (res.ok) this.t = await res.json();
		} catch (_) { }
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] || fallback;
	}

	connectedCallback() {
		this.loadTranslations().then(() => this.render());
		document.addEventListener('oz-capture-decision', this._onCapture);
	}

	disconnectedCallback() {
		document.removeEventListener('oz-capture-decision', this._onCapture);
	}

	private _onCapture = () => {
		this._previousFocus = document.activeElement;
		this._open = true;
		this._show();
	};

	private _show() {
		const overlay = this.shadowRoot!.getElementById('overlay')!;
		overlay.style.display = 'flex';
		const titleInput = this.shadowRoot!.getElementById('dc-title-input') as HTMLInputElement;
		titleInput.value = '';
		(this.shadowRoot!.getElementById('dc-context') as HTMLTextAreaElement).value = '';
		(this.shadowRoot!.getElementById('dc-outcome') as HTMLInputElement).value = '';
		(this.shadowRoot!.getElementById('dc-revisit') as HTMLInputElement).value = '';
		(this.shadowRoot!.getElementById('dc-status') as HTMLElement).textContent = '';
		requestAnimationFrame(() => titleInput.focus());
	}

	private _close() {
		this._open = false;
		const overlay = this.shadowRoot!.getElementById('overlay')!;
		overlay.style.display = 'none';
		if (this._previousFocus && (this._previousFocus as HTMLElement).focus) {
			(this._previousFocus as HTMLElement).focus();
		}
		this._previousFocus = null;
	}

	private async _save() {
		const title = (this.shadowRoot!.getElementById('dc-title-input') as HTMLInputElement).value.trim();
		const context = (this.shadowRoot!.getElementById('dc-context') as HTMLTextAreaElement).value.trim();
		const outcome = (this.shadowRoot!.getElementById('dc-outcome') as HTMLInputElement).value.trim();
		const revisitWhen = (this.shadowRoot!.getElementById('dc-revisit') as HTMLInputElement).value || null;
		const statusEl = this.shadowRoot!.getElementById('dc-status') as HTMLElement;

		if (!title) {
			statusEl.textContent = this.tr('decision_title_placeholder', 'What did you decide?');
			(this.shadowRoot!.getElementById('dc-title-input') as HTMLInputElement).focus();
			return;
		}

		const body = {
			title,
			context: context || null,
			outcome: outcome || null,
			revisit_when: revisitWhen,
			options_considered: [],
			status: 'open',
		};

		try {
			const res = await fetch('/api/atlas/decisions', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (res.ok) {
				statusEl.textContent = this.tr('decision_save', 'Save decision') + ' \u2713';
				setTimeout(() => this._close(), 900);
			} else {
				const err = await res.json().catch(() => ({}));
				statusEl.textContent = err.detail || `Error ${res.status}`;
			}
		} catch (e) {
			statusEl.textContent = String(e);
		}
	}

	private _trapFocus(e: KeyboardEvent) {
		const panel = this.shadowRoot!.getElementById('dc-panel')!;
		const focusable = Array.from(panel.querySelectorAll<HTMLElement>(
			'button, input, textarea, [tabindex]:not([tabindex="-1"])'
		)).filter(el => !el.hasAttribute('disabled'));
		if (!focusable.length) return;
		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		const active = this.shadowRoot!.activeElement;
		if (e.shiftKey) {
			if (active === first) { e.preventDefault(); last.focus(); }
		} else {
			if (active === last) { e.preventDefault(); first.focus(); }
		}
	}

	private render() {
		const shadow = this.shadowRoot!;
		shadow.innerHTML = `
			<style>
				${ACCESSIBILITY_STYLES}

				#overlay {
					display: none;
					position: fixed;
					inset: 0;
					background: hsla(0, 0%, 0%, 0.6);
					align-items: center;
					justify-content: center;
					z-index: 1000;
				}

				#dc-panel {
					background: var(--panel-bg, hsla(222, 15%, 12%, 0.97));
					border-radius: 1rem;
					padding: 2rem;
					width: min(40rem, 90vw);
					max-height: 90vh;
					overflow-y: auto;
					display: flex;
					flex-direction: column;
					gap: 0.75rem;
					border: 1px solid var(--border, hsla(0, 0%, 40%, 0.3));
				}

				h2 {
					margin: 0 0 0.5rem;
					font-size: 1.15rem;
					color: var(--text, hsla(0, 0%, 95%, 1));
				}

				label {
					font-size: 0.8rem;
					color: var(--text-muted, hsla(0, 0%, 60%, 1));
					margin-bottom: 0.15rem;
					display: block;
				}

				input[type="text"],
				input[type="date"],
				textarea {
					width: 100%;
					padding: 0.5rem 0.75rem;
					border-radius: 0.5rem;
					border: 1px solid var(--border, hsla(0, 0%, 40%, 0.3));
					background: var(--input-bg, hsla(0, 0%, 100%, 0.05));
					color: var(--text, hsla(0, 0%, 95%, 1));
					font-size: 0.95rem;
					font-family: inherit;
					box-sizing: border-box;
					min-height: 2.75rem;
				}

				input[type="text"]:focus,
				input[type="date"]:focus,
				textarea:focus {
					outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
					border-color: var(--accent-color, hsla(173, 80%, 40%, 1));
				}

				textarea {
					resize: vertical;
					min-height: 4.5rem;
				}

				#dc-actions {
					display: flex;
					gap: 0.75rem;
					margin-top: 0.5rem;
				}

				#dc-save {
					background: var(--accent-color, hsla(173, 80%, 40%, 1));
					color: hsla(0, 0%, 0%, 1);
					border: none;
					border-radius: 0.5rem;
					padding: 0.6rem 1.25rem;
					font-size: 0.9rem;
					font-weight: 600;
					cursor: pointer;
					min-height: 2.75rem;
					min-width: 44px;
				}

				#dc-save:hover {
					filter: brightness(1.1);
				}

				#dc-save:focus-visible {
					outline: 2px solid var(--text, hsla(0, 0%, 95%, 1));
					outline-offset: 2px;
				}

				#dc-cancel {
					background: transparent;
					color: var(--text-muted, hsla(0, 0%, 60%, 1));
					border: 1px solid var(--border, hsla(0, 0%, 40%, 0.3));
					border-radius: 0.5rem;
					padding: 0.6rem 1rem;
					font-size: 0.9rem;
					cursor: pointer;
					min-height: 2.75rem;
					min-width: 44px;
				}

				#dc-cancel:hover {
					color: var(--text, hsla(0, 0%, 95%, 1));
					border-color: var(--border, hsla(0, 0%, 60%, 0.5));
				}

				#dc-cancel:focus-visible {
					outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				#dc-status {
					font-size: 0.85rem;
					color: var(--text-muted, hsla(0, 0%, 60%, 1));
					min-height: 1.2rem;
				}

				@media (prefers-reduced-motion: reduce) {
					#overlay,
					#dc-panel {
						transition: none !important;
						animation: none !important;
					}
				}

				@media (forced-colors: active) {
					#dc-panel {
						border: 2px solid ButtonText;
					}
					input[type="text"],
					input[type="date"],
					textarea {
						border: 1px solid ButtonText;
					}
					#dc-save {
						forced-color-adjust: none;
					}
				}
			</style>
			<div
				id="overlay"
				role="dialog"
				aria-modal="true"
				aria-labelledby="dc-heading"
				aria-label="${this.tr('aria_decision_capture_modal', 'Decision capture dialog')}"
			>
				<div id="dc-panel">
					<h2 id="dc-heading">${this.tr('decision_capture_title', 'Capture a Decision')}</h2>

					<label for="dc-title-input">${this.tr('decision_title', 'Decision')}</label>
					<input
						id="dc-title-input"
						type="text"
						placeholder="${this.tr('decision_title_placeholder', 'What did you decide?')}"
						aria-required="true"
					/>

					<label for="dc-context">${this.tr('decision_context', 'Context')}</label>
					<textarea
						id="dc-context"
						rows="3"
						placeholder="${this.tr('decision_context_placeholder', 'Why was this decided?')}"
					></textarea>

					<label for="dc-outcome">${this.tr('decision_outcome', 'Outcome')}</label>
					<input
						id="dc-outcome"
						type="text"
						placeholder="${this.tr('decision_outcome_placeholder', 'Expected result')}"
					/>

					<label for="dc-revisit">${this.tr('decision_revisit', 'Revisit when')}</label>
					<input id="dc-revisit" type="date" />

					<div id="dc-actions">
						<button id="dc-save">${this.tr('decision_save', 'Save decision')}</button>
						<button id="dc-cancel">${this.tr('decision_cancel', 'Cancel')}</button>
					</div>

					<div id="dc-status" role="status" aria-live="polite"></div>
				</div>
			</div>
		`;

		// Wire up event handlers
		shadow.getElementById('dc-save')!.addEventListener('click', () => this._save());
		shadow.getElementById('dc-cancel')!.addEventListener('click', () => this._close());

		shadow.getElementById('overlay')!.addEventListener('keydown', (e: KeyboardEvent) => {
			if (!this._open) return;
			if (e.key === 'Escape') { e.preventDefault(); this._close(); return; }
			if (e.key === 'Tab') this._trapFocus(e);
		});
	}
}

customElements.define('decision-capture', DecisionCapture);
