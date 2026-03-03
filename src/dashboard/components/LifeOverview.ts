import { BUTTON_STYLES } from '../services/buttonStyles';

export class LifeOverview extends HTMLElement {
	private t: Record<string, string> = {};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
		this.loadTranslations().then(() => this.fetchData());
		window.addEventListener('refresh-data', () => {
			this.fetchData();
		});
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => this.fetchData());
		});
	}

	private async loadTranslations() {
		try {
			const res = await fetch('/api/dashboard/translations');
			if (res.ok) this.t = await res.json();
		} catch (_) { /* fallback to empty -- render() uses defaults */ }
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] || fallback;
	}

	async fetchData() {
		try {
			const response = await fetch('/api/dashboard/life-tree');
			if (!response.ok) throw new Error('API error');
			const data = await response.json();
			this.updateUI(data);
		} catch (e) {
			console.error('Failed to fetch life tree', e);
			this.showError();
		}
	}

	showError() {
		const container = this.shadowRoot?.querySelector('#overview-container');
		if (container) {
			container.innerHTML = `<div class="error">${this.tr('api_error_life', 'Unable to load Life Overview. Check backend connection.')}</div>`;
		}
	}

	updateUI(data: any) {
		const container = this.shadowRoot?.querySelector('#overview-container');
		if (!container) return;

		const innerHtml = data.social_circles.inner.length > 0
			? data.social_circles.inner.map((p: any) => `<li>${p.name} <span class="rel">(${p.relationship})</span></li>`).join('')
			: `<li class="empty-li">${this.tr('no_family', 'No family connections.')}</li>`;

		const closeHtml = data.social_circles.close.length > 0
			? data.social_circles.close.map((p: any) => `<li>${p.name} <span class="rel">(${p.relationship})</span></li>`).join('')
			: `<li class="empty-li">${this.tr('no_social', 'No social circle added.')}</li>`;

		const timelineHtml = data.timeline.length > 0
			? data.timeline.map((e: any) => `
					<div class="timeline-item" role="listitem">
						<span class="time">${e.time}</span>
						<span class="summary">${e.summary} ${!e.is_local ? '<small style="color: #14B8A6;">(Google)</small>' : ''}</span>
					</div>
				`).join('')
			: `<div class="empty">${this.tr('no_events', 'No upcoming events for the next 3 days.')}</div>`;

		container.innerHTML = `
			<div class="overview-grid">
				<section class="mission-control">
					<div class="section-header">
						<h3>${this.tr('boards_heading', 'Boards')}</h3>
						<button class="action-btn" onclick="this.closest('life-overview').parentElement.querySelector('create-project').toggle()">${this.tr('new_board', '+ New Board')}</button>
					</div>
					<div class="tree-content">${data.projects_tree || this.tr('initializing_projects', 'Initializing projects...')}</div>
				</section>
				
				<div class="side-panel">
					<section class="social-section">
						<div class="circle-group">
								<h3>${this.tr('inner_circle', 'Inner Circle')} <small>(${this.tr('inner_subtitle', 'Family & Care')})</small></h3>
								<ul>${innerHtml}</ul>
						</div>
						<div class="circle-group" style="margin-top: 1.5rem;">
								<h3>${this.tr('close_circle', 'Close Circle')} <small>(${this.tr('close_subtitle', 'Friends & Social')})</small></h3>
								<ul>${closeHtml}</ul>
						</div>
					</section>

					<section class="timeline">
						<h3>${this.tr('timeline_heading', 'Timeline (Next 3 Days)')}</h3>
						<div class="timeline-list">${timelineHtml}</div>
					</section>
				</div>
			</div>
		`;
	}

	render() {
		if (this.shadowRoot) {
			this.shadowRoot.innerHTML = `
				<style>
					${BUTTON_STYLES}
					:host { display: block; }
					h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1.5rem 0; color: #fff; letter-spacing: 0.02em; display: flex; align-items: center; gap: 0.5rem; }
					.h-icon { display: inline-flex; width: 28px; height: 28px; background: linear-gradient(135deg, #14B8A6 0%, #6366f1 100%); border-radius: 0.4rem; align-items: center; justify-content: center; flex-shrink: 0; }
					.h-subtitle { font-size: 0.65rem; font-weight: 400; color: rgba(255, 255, 255, 0.3); margin-left: 0.5rem; text-transform: uppercase; letter-spacing: 0.1em; }
					h3 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.1em; color: rgba(255, 255, 255, 0.4); margin-bottom: 1rem; }
					h3 small { font-size: 0.65rem; text-transform: none; letter-spacing: 0.02em; opacity: 0.8; margin-left: 0.4rem; font-weight: 400; }
					
					.overview-grid {
						display: grid;
						grid-template-columns: 1.5fr 1fr;
						gap: 2rem;
					}

					@media (max-width: 900px) {
						.overview-grid { grid-template-columns: 1fr; }
					}

					pre, .tree-content {
						background: rgba(0, 0, 0, 0.2);
						padding: 1.25rem;
						border-radius: 0.75rem;
						font-family: 'Fira Code', monospace;
						font-size: 0.9rem;
						line-height: 1.6;
						color: rgba(255, 255, 255, 0.85);
						margin: 0;
						overflow-x: auto;
						border: 1px solid rgba(255, 255, 255, 0.03);
						white-space: pre-wrap;
					}

					.tree-content b { color: #14B8A6; font-weight: 600; }
					.tree-content a { color: inherit; text-decoration: none; border-bottom: 1px solid rgba(255,255,255,0.1); transition: all 0.2s; }
					.tree-content a:hover { color: #0066FF; border-bottom-color: #0066FF; }

					.section-header {
						display: flex;
						justify-content: space-between;
						align-items: center;
						margin-bottom: 1rem;
					}

					.action-btn {
						padding: 0.25rem 0.75rem;
						font-size: 0.75rem;
					}

					.side-panel { display: flex; flex-direction: column; gap: 2rem; }

					ul { list-style: none; padding: 0; margin: 0; }
					li { 
						font-size: 0.95rem; 
						line-height: 1.4;
						color: #fff; 
						margin-bottom: 0.5rem; 
						display: flex;
						align-items: center;
						gap: 0.5rem;
					}
					.rel { color: rgba(255, 255, 255, 0.4); font-size: 0.8rem; }
					.empty-li { font-size: 0.85rem; color: rgba(255, 255, 255, 0.25); font-style: italic; }

					.timeline-list { display: flex; flex-direction: column; gap: 0.75rem; }
					.timeline-item {
						display: flex;
						gap: 1rem;
						background: rgba(255, 255, 255, 0.02);
						padding: 0.75rem;
						border-radius: 0.6rem;
						font-size: 0.85rem;
					}
					.time { color: #14B8A6; font-weight: 600; min-width: 70px; }
					.summary { color: rgba(255, 255, 255, 0.8); }
					.summary small { color: #3b82f6; opacity: 0.7; font-size: 0.7rem; margin-left: 0.3rem; }


					.error { color: #ef4444; text-align: center; padding: 2rem; }
				.action-btn:focus-visible { outline: 2px solid #14B8A6; outline-offset: 3px; }
				.tree-content a:focus-visible { outline: 2px solid #14B8A6; outline-offset: 2px; }
				@media (prefers-reduced-motion: reduce) {
					*, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
				}
				</style>
				<div class="card">
					<h2>
					<span class="h-icon" aria-hidden="true">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
							<circle cx="12" cy="12" r="10"></circle>
							<line x1="2" y1="12" x2="22" y2="12"></line>
							<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
						</svg>
					</span>
					${this.tr('life_overview', 'Life Overview')}
					</h2>
					<div id="overview-container">
						<div style="text-align: center; padding: 2rem; color: rgba(255,255,255,0.3);">${this.tr('mapping_world', 'Mapping your world...')}</div>
					</div>
				</div>
			`;
		}
	}
}

customElements.define('life-overview', LifeOverview);
