import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { GLASS_TOOLTIP_STYLES } from '../services/glassTooltipStyles';
import { STATUS_STYLES } from '../services/statusStyles';

export class CrewsWidget extends HTMLElement {
	private crews: any[] = [];
	private history: any[] = [];
	private isLoading = true;
	private t: Record<string, string> = {};
	private openSections: Set<string> = new Set();
	private observer: IntersectionObserver | null = null;
	private isVisible: boolean = false;
	private pollInterval: number | null = null;

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
		this.loadTranslations().then(() => {
			this.render();
			this.setupIntersectionObserver();
		});
	}

	disconnectedCallback() {
		if (this.observer) this.observer.disconnect();
		this.stopPolling();
	}

	private setupIntersectionObserver() {
		this.observer = new IntersectionObserver(
			(entries) => {
				entries.forEach((entry) => {
					this.isVisible = entry.isIntersecting;
					if (this.isVisible) {
						this.fetchData();
						this.startPolling();
					} else {
						this.stopPolling();
					}
				});
			},
			{ threshold: 0.1 }
		);
		this.observer.observe(this);
	}

	private startPolling() {
		if (this.pollInterval === null) {
			this.pollInterval = window.setInterval(() => {
				if (this.isVisible) this.fetchData(true);
			}, 30000); // 30s background polling
		}
	}

	private stopPolling() {
		if (this.pollInterval !== null) {
			window.clearInterval(this.pollInterval);
			this.pollInterval = null;
		}
	}

	async fetchData(silent = false) {
		if (!silent) {
			this.isLoading = true;
			this.render();
		}
		
		try {
			const [crewsRes, historyRes] = await Promise.all([
				fetch('/api/dashboard/crews'),
				fetch('/api/dashboard/crews/history')
			]);
			
			if (crewsRes.ok) {
				const data = await crewsRes.json();
				this.crews = data.crews || [];
			}
			if (historyRes.ok) {
				const hisData = await historyRes.json();
				this.history = hisData.history || [];
			}
		} catch (e) {
			console.error('Failed to fetch crews data', e);
		} finally {
			this.isLoading = false;
			this.render();
		}
	}

	private toggleSection(section: string) {
		if (this.openSections.has(section)) {
			this.openSections.delete(section);
		} else {
			this.openSections.add(section);
		}
		this.render();
	}

	private async handleRunNow(crewId: string) {
		const btn = this.shadowRoot?.querySelector(`#btn-run-${crewId}`) as HTMLButtonElement;
		if (btn) btn.classList.add('loading');
		
		try {
			const res = await fetch(`/api/dashboard/crews/${crewId}/run`, { method: 'POST' });
			if (res.ok) {
				// Re-fetch to show updated active state
				await this.fetchData();
			}
		} catch (e) {
			console.error('Failed to trigger run', e);
		} finally {
			if (btn) btn.classList.remove('loading');
		}
	}

	render() {
		if (!this.shadowRoot) return;

		this.shadowRoot.innerHTML = `
			<style>
				${BUTTON_STYLES}
				${ACCESSIBILITY_STYLES}
				${SECTION_HEADER_STYLES}
				${SCROLLBAR_STYLES}
				${EMPTY_STATE_STYLES}
				${GLASS_TOOLTIP_STYLES}
				${STATUS_STYLES}

				:host { display: block; height: 100%; font-family: 'Inter', system-ui, sans-serif; }
				.card { height: 100%; display: flex; flex-direction: column; gap: 1rem; color: var(--text-primary, hsla(0, 0%, 100%, 1)); }
				
				.header { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; }
				.header-right { display: flex; align-items: center; gap: 0.5rem; }
				
				.content { flex: 1; overflow-y: auto; padding-right: 4px; display: flex; flex-direction: column; gap: 1rem; }

				.crew-grid {
					display: grid;
					grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
					gap: 0.75rem;
				}

				.crew-card {
					background: rgba(255, 255, 255, 0.02);
					border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
					border-radius: 0.75rem;
					padding: 1rem;
					display: flex;
					flex-direction: column;
					gap: 0.75rem;
					transition: border-color 0.2s, background 0.2s;
				}

				.crew-card:hover {
					background: rgba(255, 255, 255, 0.04);
					border-color: rgba(255, 255, 255, 0.1);
				}

				.crew-header {
					display: flex;
					justify-content: space-between;
					align-items: flex-start;
					gap: 0.5rem;
				}

				.crew-title-area {
					display: flex;
					align-items: center;
					gap: 0.5rem;
				}

				.crew-name {
					font-weight: 600;
					font-size: 0.85rem;
					color: var(--text-primary);
					letter-spacing: 0.02em;
				}

				.crew-type {
					font-size: 0.65rem;
					text-transform: uppercase;
					letter-spacing: 0.05em;
					color: var(--text-muted);
					background: rgba(255, 255, 255, 0.05);
					padding: 0.15rem 0.4rem;
					border-radius: 4px;
				}

				.crew-desc {
					font-size: 0.75rem;
					line-height: 1.4;
					color: var(--text-muted);
					display: -webkit-box;
					-webkit-line-clamp: 2;
					-webkit-box-orient: vertical;
					overflow: hidden;
				}

				/* Accordion for characters */
				.char-accordion {
					margin-top: 0.5rem;
				}

				.char-toggle {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					background: none;
					border: none;
					color: var(--accent-color, #14b8a6);
					font-size: 0.75rem;
					font-weight: 500;
					cursor: pointer;
					padding: 0;
					opacity: 0.8;
					transition: opacity 0.2s;
				}

				.char-toggle:hover { opacity: 1; }

				.char-toggle svg {
					transition: transform 0.3s ease;
				}

				.char-toggle[aria-expanded="true"] svg {
					transform: rotate(180deg);
				}

				.char-list {
					max-height: 0;
					overflow: hidden;
					transition: max-height 0.3s ease, margin-top 0.3s ease;
					opacity: 0;
					display: flex;
					flex-direction: column;
					gap: 0.5rem;
				}

				.char-list.open {
					max-height: 500px;
					opacity: 1;
					margin-top: 0.75rem;
				}

				.char-item {
					font-size: 0.7rem;
					padding: 0.4rem 0.5rem;
					background: rgba(0, 0, 0, 0.2);
					border-radius: 4px;
					border-left: 2px solid var(--accent-secondary, hsla(216, 100%, 50%, 1));
					color: var(--text-secondary);
				}

				.crew-actions {
					margin-top: auto;
					padding-top: 0.75rem;
					border-top: 1px solid rgba(255, 255, 255, 0.05);
					display: flex;
					justify-content: flex-end;
				}

				.run-btn {
					font-size: 0.7rem;
					padding: 0.3rem 0.75rem;
				}

				/* History Panel */
				.history-panel {
					margin-top: 1rem;
					border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
					border-radius: 0.75rem;
					overflow: hidden;
				}

				.history-header {
					padding: 0.75rem 1rem;
					background: rgba(255, 255, 255, 0.02);
					font-size: 0.8rem;
					font-weight: 600;
					color: var(--text-primary);
					border-bottom: 1px solid var(--border-subtle);
					display: flex;
					align-items: center;
					gap: 0.5rem;
				}

				.history-list {
					display: flex;
					flex-direction: column;
					max-height: 200px;
					overflow-y: auto;
				}

				.history-item {
					display: grid;
					grid-template-columns: 100px 1fr auto auto;
					gap: 1rem;
					padding: 0.6rem 1rem;
					font-size: 0.75rem;
					align-items: center;
					border-bottom: 1px solid rgba(255, 255, 255, 0.02);
				}

				.history-item:last-child { border-bottom: none; }
				
				.hist-time { color: var(--text-muted); font-variant-numeric: tabular-nums; }
				.hist-name { color: var(--text-secondary); font-weight: 500; }
				.hist-dur { color: var(--text-muted); font-size: 0.7rem; }
				
				.status-badge {
					font-size: 0.65rem;
					padding: 0.15rem 0.4rem;
					border-radius: 4px;
					text-transform: uppercase;
					letter-spacing: 0.05em;
					font-weight: 600;
				}
				.status-success { background: rgba(20, 184, 166, 0.1); color: #14b8a6; }
				.status-failed { background: rgba(239, 68, 68, 0.1); color: #ef4444; }

				@media (prefers-reduced-motion: reduce) {
					.char-list, .char-toggle svg, .crew-card { transition: none !important; }
				}
			</style>

			<div class="card">
				<div class="header">
					<h2>
						<div class="h-icon" aria-hidden="true">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
							</svg>
						</div>
						${this.tr('crews_title', 'Dify Orchestration Crews')}
					</h2>
					<div class="header-right">
						<button class="btn btn-icon btn-glass" aria-label="${this.tr('refresh', 'Refresh')}" id="btn-refresh">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<polyline points="23 4 23 10 17 10"></polyline>
								<polyline points="1 20 1 14 7 14"></polyline>
								<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
							</svg>
						</button>
					</div>
				</div>

				<div class="content">
					${this.isLoading ? `<div class="empty-state">${this.tr('loading_crews', 'Loading crews...')}</div>` : `
						
						${this.crews.length === 0 ? `
							<div class="empty-state">${this.tr('no_crews_found', 'No Dify Crews provisioned or active.')}</div>
						` : `
							<div class="crew-grid" role="list">
								${this.crews.map(c => `
									<div class="crew-card" role="listitem">
										<div class="crew-header">
											<div class="crew-title-area">
												<span class="status-dot ${c.is_running ? 'running pulse' : (c.dify_app_id ? 'ok' : 'offline')}" 
													aria-label="${c.is_running ? 'Running' : (c.dify_app_id ? 'Ready' : 'Unprovisioned')}"></span>
												<span class="crew-name">${c.name}</span>
											</div>
											<span class="crew-type">${c.type}</span>
										</div>
										<div class="crew-desc">${c.description}</div>
										
										${c.characters && c.characters.length > 0 ? `
											<div class="char-accordion">
												<button class="char-toggle" aria-expanded="${this.openSections.has('char-' + c.id) ? 'true' : 'false'}" data-crew="${c.id}">
													<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
														<polyline points="6 9 12 15 18 9"></polyline>
													</svg>
													${this.tr('view_characters', 'View Characters')} (${c.characters.length})
												</button>
												<div class="char-list ${this.openSections.has('char-' + c.id) ? 'open' : ''}">
													${c.characters.map((char: any) => `
														<div class="char-item">
															<strong>${char.role}:</strong> ${char.goal}
														</div>
													`).join('')}
												</div>
											</div>
										` : ''}

										<div class="crew-actions">
											<button class="btn btn-outline run-btn" id="btn-run-${c.id}" data-id="${c.id}" ${c.is_running || !c.dify_app_id ? 'disabled' : ''}>
												<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
													<polygon points="5 3 19 12 5 21 5 3"></polygon>
												</svg>
												${c.is_running ? this.tr('running', 'Running...') : this.tr('run_now', 'Run Now')}
											</button>
										</div>
									</div>
								`).join('')}
							</div>
						`}

						${this.history && this.history.length > 0 ? `
							<div class="history-panel">
								<div class="history-header">
									<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
										<circle cx="12" cy="12" r="10"></circle>
										<polyline points="12 6 12 12 16 14"></polyline>
									</svg>
									${this.tr('run_history', 'Run History')}
								</div>
								<div class="history-list">
									${this.history.map(h => `
										<div class="history-item">
											<span class="hist-time">${new Date(h.timestamp).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
											<span class="hist-name">${h.crew_name}</span>
											<span class="hist-dur">${h.duration_s ? h.duration_s.toFixed(1) + 's' : '-'}</span>
											<span class="status-badge status-${h.status === 'success' ? 'success' : 'failed'}">${h.status}</span>
										</div>
									`).join('')}
								</div>
							</div>
						` : ''}
					`}
				</div>
			</div>
		`;

		this.setupEventListeners();
	}

	private setupEventListeners() {
		const refreshBtn = this.shadowRoot?.querySelector('#btn-refresh');
		refreshBtn?.addEventListener('click', () => this.fetchData());

		const toggles = this.shadowRoot?.querySelectorAll('.char-toggle');
		toggles?.forEach(t => {
			t.addEventListener('click', (e) => {
				const id = (e.currentTarget as HTMLButtonElement).dataset.crew;
				if (id) this.toggleSection('char-' + id);
			});
		});

		const runBtns = this.shadowRoot?.querySelectorAll('.run-btn');
		runBtns?.forEach(b => {
			b.addEventListener('click', (e) => {
				const id = (e.currentTarget as HTMLButtonElement).dataset.id;
				if (id) this.handleRunNow(id);
			});
		});
	}
}

customElements.define('crews-widget', CrewsWidget);
