import { BUTTON_STYLES } from '../services/buttonStyles';

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
	}

	private currentLimit = 5;

	async fetchBriefings() {
		try {
			const response = await fetch(`/api/dashboard/briefings?limit=${this.currentLimit}`);
			if (!response.ok) throw new Error('API error');
			const data = await response.json();
			this.displayBriefings(data);
		} catch (e) {
			const list = this.shadowRoot?.querySelector('#briefing-list');
			if (list) list.textContent = 'No briefings yet.';
		}
	}

	showMore() {
		this.currentLimit += 15;
		this.fetchBriefings();
	}

	displayBriefings(briefings: any[]) {
		const list = this.shadowRoot?.querySelector('#briefing-list');
		if (!list) return;

		const itemsHtml = briefings.map((b) => `
				<div class="briefing-item" role="listitem">
					<button class="meta"
						onclick="this.parentElement.classList.toggle('active'); this.setAttribute('aria-expanded', this.parentElement.classList.contains('active').toString())"
						aria-expanded="false"
						aria-controls="briefing-content-${b.id || b.created_at}"
						aria-label="${this.tr('aria_toggle_briefing', 'Toggle briefing from')} ${new Date(b.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}"
					>
						<div class="meta-left">
							<span class="type">${b.type.toUpperCase()}</span>
							<span class="date">${new Date(b.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
						</div>
						<div class="chevron" aria-hidden="true">
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
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
			${itemsHtml || this.tr('no_briefings', 'No briefings yet.')}
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
					h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1.5rem 0; color: #fff; letter-spacing: 0.02em; display: flex; align-items: center; gap: 0.5rem; }
					.icon { display: inline-flex; width: 28px; height: 28px; background: linear-gradient(135deg, #14B8A6 0%, #0066FF 100%); border-radius: 0.4rem; align-items: center; justify-content: center; flex-shrink: 0; }
					.subtitle { font-size: 0.65rem; font-weight: 400; color: rgba(255, 255, 255, 0.3); margin-left: 0.5rem; text-transform: uppercase; letter-spacing: 0.1em; }
					:host { display: block; }
					.card {
						display: flex;
						flex-direction: column;
					}
					.briefing-item {
						background: rgba(255, 255, 255, 0.02);
						border-radius: 12px;
						margin-bottom: 0.75rem;
						border: 1px solid rgba(255, 255, 255, 0.05);
						overflow: hidden;
						transition: background 0.3s ease, border-color 0.3s ease;
					}
					.briefing-item:hover {
						background: rgba(255, 255, 255, 0.04);
						border-color: rgba(255, 255, 255, 0.1);
					}
					.briefing-item.active {
						background: rgba(255, 255, 255, 0.04);
						border-color: rgba(20, 184, 166, 0.2);
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
					.meta:focus-visible {
						outline: 2px solid #14B8A6;
						outline-offset: 2px;
						border-radius: 4px;
						background: rgba(255, 255, 255, 0.05);
					}
					.type { 
						background: rgba(20, 184, 166, 0.1); 
						color: #14B8A6; 
						font-size: 0.65rem; 
						padding: 0.2rem 0.6rem; 
						border-radius: 20px; 
						font-weight: 700;
						letter-spacing: 0.05em;
						border: 1px solid rgba(20, 184, 166, 0.2);
					}
					.date { 
						font-size: 0.8rem; 
						color: rgba(255, 255, 255, 0.4); 
						font-weight: 500;
					}
					.chevron { 
						transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1); 
						color: rgba(255, 255, 255, 0.2);
						display: flex;
						align-items: center;
					}
					.briefing-item.active .chevron { 
						transform: rotate(180deg); 
						color: #14B8A6;
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
						color: rgba(255, 255, 255, 0.8); 
						border-top: 1px solid rgba(255, 255, 255, 0.03);
						padding-top: 1rem;
					}
					.load-more {
						width: 100%;
						background: rgba(255, 255, 255, 0.02);
						border: 1px dashed rgba(255, 255, 255, 0.1);
						color: rgba(255, 255, 255, 0.4);
						padding: 0.75rem;
						border-radius: 12px;
						font-size: 0.8rem;
						font-weight: 600;
						cursor: pointer;
						margin-top: 0.5rem;
						transition: all 0.2s;
					}
					.load-more:hover {
						background: rgba(20, 184, 166, 0.05);
						color: #14B8A6;
						border-color: rgba(20, 184, 166, 0.3);
					}
					.load-more:focus-visible { outline: 2px solid #14B8A6; outline-offset: 2px; }
					@media (prefers-reduced-motion: reduce) {
						.content-wrapper { transition: none; }
						.chevron { transition: none; }
					}
				</style>
				<div class="card">
					<h2>
			<span class="icon" aria-hidden="true">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
								<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
								<polyline points="14 2 14 8 20 8"></polyline>
								<line x1="16" y1="13" x2="8" y2="13"></line>
								<line x1="16" y1="17" x2="8" y2="17"></line>
							</svg>
						</span>
						${this.tr('briefing_history', 'Briefing')}
					<span class="subtitle" aria-hidden="true">${this.tr('briefing_subtitle', 'Daily Reports')}</span>
				</h2>
				<div id="briefing-list" role="list" aria-label="Briefing history entries" aria-live="polite">${this.tr('loading', 'Loading...')}</div>
				</div>
			`;
		}
	}
}

customElements.define('briefing-history', BriefingHistory);
