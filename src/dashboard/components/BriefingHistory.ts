import { BUTTON_STYLES } from '../services/buttonStyles';
import { initGoo } from '../services/gooStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';

export class BriefingHistory extends HTMLElement {
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
		this.render();
		this.loadTranslations().then(() => {
			this.render();
			this.fetchBriefings();
		});
		initGoo(this);
		window.addEventListener('goo-changed', () => initGoo(this));
	}

	private currentLimit = 5;

	async fetchBriefings() {
		try {
			const response = await fetch(`/api/dashboard/briefings?limit=${this.currentLimit}`);
			if (!response.ok) throw new Error('API error');
			const data = await response.json();
			this.displayBriefings(data);
		} catch (_e) {
			const list = this.shadowRoot?.querySelector('#briefing-list');
			if (list) {
				list.removeAttribute('role');
				list.textContent = 'No briefings yet.';
			}
		}
	}

	showMore() {
		this.currentLimit += 15;
		this.fetchBriefings();
	}

	displayBriefings(briefings: any[]) {
		const list = this.shadowRoot?.querySelector('#briefing-list');
		if (!list) return;

		if (briefings.length === 0) {
			list.removeAttribute('role');
		}

		const itemsHtml = briefings.map((b) => `
				<div class="briefing-item" role="listitem">
					<button class="meta"
						onclick="this.parentElement.classList.toggle('active'); this.setAttribute('aria-expanded', this.parentElement.classList.contains('active').toString())"
						aria-expanded="false"
						aria-controls="briefing-content-${b.id || b.created_at}"
						aria-label="${b.type.toUpperCase()} -- ${new Date(b.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} -- ${this.tr('aria_toggle_briefing', 'Toggle briefing')}"
					>
						<div class="meta-left">
							<span class="type">${b.type.toUpperCase()}</span>
							<span class="date">${new Date(b.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
							${b.model ? `<span class="model-tag" aria-label="${this.tr('aria_briefing_model', 'Model used')}: ${b.model}">${b.model}</span>` : ''}
						</div>
						<div class="chevron" aria-hidden="true">
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false" class="oz-goo-blob">
								<path d="m6 9 6 6 6-6"/>
							</svg>
						</div>
					</button>
					<div class="content-wrapper"
						id="briefing-content-${b.id || b.created_at}"
						role="region"
						aria-label="${this.tr('aria_briefing_content', 'Briefing content from')} ${new Date(b.created_at).toLocaleDateString()}">
						<div class="content-inner">
							<div class="content">${b.content}</div>
						</div>
					</div>
				</div>
			`).join('');

		list.innerHTML = `
			<div class="briefing-items-list"${briefings.length > 0 ? ' role="list"' : ''}>
				${itemsHtml || this.tr('no_briefings', 'No briefings yet.')}
			</div>
			${briefings.length >= 5 ? `<button class="load-more" id="load-more-btn">${this.tr('show_more', 'Show More History')}</button>` : ''}
		`;

		const loadMoreBtn = this.shadowRoot?.querySelector('#load-more-btn');
		if (loadMoreBtn) {
			loadMoreBtn.addEventListener('click', () => this.showMore());
		}
	}

	render() {
		if (this.shadowRoot) {
			this.shadowRoot.innerHTML = `
				<style>
					${BUTTON_STYLES}
					${ACCESSIBILITY_STYLES}
					${SECTION_HEADER_STYLES}
					/* Override icon gradient */
					h2 .h-icon {
						background: linear-gradient(135deg, var(--accent-color, hsla(173, 80%, 40%, 1)) 0%, hsla(216, 100%, 50%, 1) 100%);
					}
					:host { display: block; }
					.card {
						display: flex;
						flex-direction: column;
						position: relative;
					}
					.bg-glow {
						position: absolute;
						top: -10px; right: -10px; width: 100px; height: 100px;
						background: radial-gradient(circle at center, var(--accent-glow) 0%, transparent 70%);
						opacity: 0.1;
						pointer-events: none;
						z-index: 0;
					}
					.briefing-item {
						background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
						border-radius: var(--radius-lg, 0.75rem);
						margin-bottom: 0.75rem;
						border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
						overflow: hidden;
						transition: background var(--duration-base, 0.3s) ease, border-color var(--duration-base, 0.3s) ease;
						position: relative;
						z-index: 1;
					}
					.briefing-item:hover {
						background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.05));
						border-color: var(--border-medium, hsla(0, 0%, 100%, 0.12));
					}
					.briefing-item.active {
						background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.05));
						border-color: rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
					}
					.meta { 
						display: flex; 
						justify-content: space-between; 
						align-items: center;
						padding: 1rem 1.25rem; 
						cursor: pointer;
						user-select: none;
						background: transparent;
						border: none;
						width: 100%;
						font-family: inherit;
						color: inherit;
					}
					.meta-left {
						display: flex;
						align-items: center;
						gap: 0.5rem;
						flex-wrap: wrap;
						min-width: 0;
					}
					.meta:focus-visible {
						outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1));
						outline-offset: 2px;
						border-radius: var(--radius-sm, 0.35rem);
						background: var(--surface-hover, hsla(0, 0%, 100%, 0.06));
					}
					.type { 
						background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.1); 
						color: var(--accent-color, hsla(173, 80%, 40%, 1)); 
						font-size: 0.65rem; 
						padding: 0.2rem 0.6rem; 
						border-radius: var(--radius-pill, 9999px); 
						font-weight: 700;
						letter-spacing: 0.05em;
						border: 1px solid rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
					}
					.date { 
						font-size: 0.8rem; 
						color: var(--text-muted, hsla(0, 0%, 100%, 0.4)); 
						font-weight: 500;
					}
					.model-tag {
						font-size: 0.6rem;
						color: var(--text-faint, hsla(0, 0%, 100%, 0.3));
						background: hsla(0, 0%, 100%, 0.05);
						border: 1px solid hsla(0, 0%, 100%, 0.08);
						border-radius: var(--radius-pill, 9999px);
						padding: 0.15rem 0.5rem;
						font-weight: 500;
						letter-spacing: 0.02em;
						white-space: nowrap;
						max-width: 12rem;
						overflow: hidden;
						text-overflow: ellipsis;
					}
					.chevron { 
						transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1); 
						color: var(--text-faint, hsla(0, 0%, 100%, 0.2));
						display: flex;
						align-items: center;
					}
					.briefing-item.active .chevron { 
						transform: rotate(180deg); 
						color: var(--accent-color, hsla(173, 80%, 40%, 1));
					}
					
					.content-wrapper {
						display: grid;
						grid-template-rows: 0fr;
						pointer-events: none;
						transition: grid-template-rows 0.4s cubic-bezier(0.4, 0, 0.2, 1);
					}
					.briefing-item.active .content-wrapper {
						grid-template-rows: 1fr;
						pointer-events: auto;
					}
					.content-inner {
						overflow: hidden;
						min-height: 0;
					}
					.content { 
						padding: 0 1.25rem 1.25rem 1.25rem;
						font-size: 0.95rem; 
						white-space: pre-wrap; 
						line-height: 1.6; 
						color: var(--text-secondary, hsla(0, 0%, 100%, 0.7)); 
						border-top: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
						padding-top: 1rem;
					}
					.load-more {
						width: 100%;
						background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
						border: 1px dashed var(--border-medium, hsla(0, 0%, 100%, 0.12));
						color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
						padding: 0.75rem;
						border-radius: var(--radius-lg, 0.75rem);
						font-size: 0.8rem;
						font-weight: 600;
						cursor: pointer;
						margin-top: 0.5rem;
						transition: all 0.2s;
					}
					.load-more:hover {
						background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.1);
						color: var(--accent-color, hsla(173, 80%, 40%, 1));
						border-color: rgba(var(--accent-color-rgb, 20, 184, 166), 0.4);
					}
					.load-more:focus-visible { outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1)); outline-offset: 2px; }
					@media (forced-colors: active) {
						.h-icon { background: ButtonFace; border: 1px solid ButtonText; }
						.briefing-item.active { border-color: Highlight; }
						.type-tag { border: 1px solid ButtonText; }
					}
				</style>
				<div class="card">
					<div class="bg-glow"></div>
					<h2>
			<span class="h-icon" aria-hidden="true">
						<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false" class="oz-goo-blob">
								<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
								<polyline points="14 2 14 8 20 8"></polyline>
								<line x1="16" y1="13" x2="8" y2="13"></line>
								<line x1="16" y1="17" x2="8" y2="17"></line>
							</svg>
						</span>
						${this.tr('briefing_history', 'Briefing')}
					<span class="subtitle" aria-hidden="true">${this.tr('briefing_subtitle', 'Daily Reports')}</span>
				</h2>
				<div id="briefing-list" aria-label="${this.tr('aria_briefing_list', 'Briefing history entries')}" aria-live="polite">${this.tr('loading', 'Loading...')}</div>
				</div>
			`;
		}
	}
}

customElements.define('briefing-history', BriefingHistory);
