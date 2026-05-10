import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';

export class InstanceEntry extends HTMLElement {
	private t: Record<string, string> = {};

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
		this.loadTranslations().then(() => this.checkStatus());
	}

	private async checkStatus() {
		try {
			const res = await fetch('/api/dashboard/onboarding-status');
			if (!res.ok) return;
			const data = await res.json();
			if (data.needs_onboarding) {
				this.render();
			} else {
				this.style.display = 'none';
			}
		} catch (_) {
			// silently hide on network error
		}
	}

	private render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
			<style>
				:host { display: block; grid-column: 1 / -1; margin-bottom: 2rem; }
				${ACCESSIBILITY_STYLES}
				.card {
					background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.08));
					border: 2px solid var(--border-accent, hsla(173, 80%, 40%, 0.3));
					border-radius: var(--radius-lg, 1rem);
					padding: 2rem;
					display: flex;
					flex-direction: column;
					gap: 1.5rem;
					animation: entryIn var(--duration-base, 0.25s) ease-out;
				}
				@keyframes entryIn {
					from { opacity: 0; transform: translateY(-8px); }
					to { opacity: 1; transform: translateY(0); }
				}
				h2 {
					margin: 0;
					font-size: 1.5rem;
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
				}
				.field-group {
					display: flex;
					flex-direction: column;
					gap: 0.5rem;
				}
				label {
					font-size: 0.9rem;
					font-weight: 600;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.7));
				}
				textarea,
				input[type="text"] {
					background: var(--surface-card, hsla(0, 0%, 100%, 0.05));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.15));
					border-radius: var(--radius-md, 0.75rem);
					box-sizing: border-box;
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					font-family: inherit;
					font-size: 1rem;
					min-height: 44px;
					padding: 0.75rem 1rem;
					width: 100%;
				}
				textarea {
					min-height: 5rem;
					resize: vertical;
				}
				textarea:focus-visible,
				input[type="text"]:focus-visible {
					border-color: transparent;
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}
				.cta {
					align-self: flex-start;
					background: var(--accent-primary-dark, hsla(173, 80%, 25%, 1));
					border: none;
					border-radius: var(--radius-md, 0.75rem);
					box-shadow: 0 4px 12px var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.2));
					color: hsla(0, 0%, 100%, 1);
					cursor: pointer;
					font-family: inherit;
					font-size: 0.95rem;
					font-weight: 600;
					min-height: 44px;
					padding: 0.75rem 1.5rem;
					transition: transform var(--duration-fast, 0.15s) ease, box-shadow var(--duration-fast, 0.15s) ease;
				}
				.cta:hover {
					box-shadow: 0 6px 16px var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.35));
					transform: translateY(-2px);
				}
				.cta:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 3px;
				}
				@media (prefers-reduced-motion: reduce) {
					.card { animation: none; }
					.cta { transform: none; transition: none; }
				}
				@media (forced-colors: active) {
					.card { background: Canvas; border: 2px solid ButtonText; }
					textarea,
					input[type="text"] { background: Field; border: 1px solid ButtonText; color: FieldText; }
					.cta { background: Highlight; border: 1px solid Highlight; color: HighlightText; }
				}
			</style>
			<div class="card" role="region" aria-label="${this.tr('aria_instance_entry', 'Instance setup')}">
				<h2>${this.tr('instance_entry_heading', 'Set up your instance')}</h2>
				<div class="field-group">
					<label for="ie-template-hint">${this.tr('instance_purpose_label', 'What is this instance for?')}</label>
					<textarea
						id="ie-template-hint"
						name="template_hint"
						placeholder="${this.tr('template_hint_placeholder', 'e.g. my personal life, our engineering team, my recipes...')}"
						rows="3"
					></textarea>
				</div>
				<div class="field-group">
					<label for="ie-purpose">${this.tr('instance_purpose_label', 'What is this instance for?')}</label>
					<input
						id="ie-purpose"
						type="text"
						name="purpose"
						placeholder="${this.tr('template_hint_placeholder', 'e.g. my personal life, our engineering team, my recipes...')}"
						aria-label="${this.tr('instance_purpose_label', 'What is this instance for?')}"
					/>
				</div>
				<button
					class="cta"
					id="ie-connect-btn"
					type="button"
					aria-label="${this.tr('connect_source_cta', 'Connect your first source')}"
				>
					${this.tr('connect_source_cta', 'Connect your first source')}
				</button>
			</div>
		`;
		this.shadowRoot.querySelector('#ie-connect-btn')?.addEventListener('click', () => this.handleSubmit());
	}

	private async handleSubmit() {
		const purpose = (this.shadowRoot?.querySelector<HTMLInputElement>('#ie-purpose')?.value ?? '').trim();
		const templateHint = (this.shadowRoot?.querySelector<HTMLTextAreaElement>('#ie-template-hint')?.value ?? '').trim();
		try {
			await fetch('/api/dashboard/instance-purpose', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ purpose, template_hint: templateHint }),
			});
		} catch (_) { }
		const hasSettings = !!document.querySelector('#section-settings');
		if (hasSettings) {
			window.location.hash = 'section-settings';
		}
		this.style.opacity = '0';
		this.style.pointerEvents = 'none';
		setTimeout(() => { this.style.display = 'none'; }, 300);
	}
}

customElements.define('instance-entry', InstanceEntry);
