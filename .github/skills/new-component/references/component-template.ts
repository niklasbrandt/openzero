import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';

export class __COMPONENT_NAME__ extends HTMLElement {
	private t: Record<string, string> = {};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
		this.loadTranslations().then(() => this.render());
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => this.render());
		});
	}

	disconnectedCallback() {
		// Clean up timers, listeners, observers here
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

	private render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
			<style>
				${ACCESSIBILITY_STYLES}
				${SCROLLBAR_STYLES}

				:host {
					display: block;
				}

				.container {
					padding: 1rem;
				}

				/* ---- Accessibility ---- */
				@media (prefers-reduced-motion: reduce) {
					*, *::before, *::after {
						animation-duration: 0.01ms !important;
						transition-duration: 0.01ms !important;
					}
				}

				@media (forced-colors: active) {
					:host {
						border: 1px solid CanvasText;
					}
				}
			</style>
			<div class="container">
				<h2>${this.tr('__tag_name___title', '__COMPONENT_NAME__')}</h2>
			</div>
		`;
	}
}

customElements.define('__TAG_NAME__', __COMPONENT_NAME__);
