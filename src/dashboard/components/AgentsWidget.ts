import { BUTTON_STYLES } from '../services/buttonStyles';
import { initGoo } from '../services/gooStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';

interface Personality {
	directness: number;
	warmth: number;
	agency: number;
	critique: number;
	humor: number;
	honesty: number;
	depth: number;
	roast: number;
	role: string;
	relationship: string;
	values: string;
	behavior: string;
	questions: any[];
}

interface Crew {
	id: string;
	name: string;
	description: string;
	type: 'workflow' | 'agent';
	dify_app_id: string;
	is_running: boolean;
	characters: Array<{ name: string; role: string }>;
	schedule?: string;
	feeds_briefing?: string;
	briefing_day?: string;
	briefing_dom?: string;
	briefing_months?: string;
}

export class AgentsWidget extends HTMLElement {
	private personality: Personality | null = null;
	private crews: Crew[] = [];
	private loading = true;
	private isEditing = false;
	private saving = false;
	private runningCrews = new Set<string>();
	private t: Record<string, string> = {};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
		this.loadTranslations().then(() => {
			this.render();
			this.loadData();
		});
		initGoo(this);
		window.addEventListener('goo-changed', () => initGoo(this));
		this.addEventListener('refresh-data', () => this.loadData());
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

	private async loadData() {
		this.loading = true;
		try {
			const [pRes, cRes] = await Promise.all([
				fetch('/api/dashboard/personality'),
				fetch('/api/dashboard/crews')
			]);
			
			if (pRes.ok) this.personality = await pRes.json();
			if (cRes.ok) {
				const data = await cRes.json();
				this.crews = data.crews || [];
			}
		} catch (e) {
			console.error('Failed to load Agents data:', e);
		} finally {
			this.loading = false;
			this.render();
		}
	}

	private async savePersonality() {
		if (!this.personality) return;
		this.saving = true;
		this.render();
		try {
			const res = await fetch('/api/dashboard/personality', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(this.personality)
			});
			if (res.ok) {
				this.isEditing = false;
				window.dispatchEvent(new CustomEvent('theme-update'));
			}
		} finally {
			this.saving = false;
			this.render();
		}
	}

	private async runCrew(crewId: string) {
		this.runningCrews.add(crewId);
		this.render();
		try {
			const res = await fetch(`/api/dashboard/crews/${crewId}/run`, { method: 'POST' });
			if (res.ok) {
				setTimeout(() => {
					this.runningCrews.delete(crewId);
					this.render();
				}, 3000);
			}
		} catch (e) {
			this.runningCrews.delete(crewId);
			this.render();
		}
	}

	private renderIcon(name: string, size = '1rem'): string {
		const icons: Record<string, string> = {
			settings: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
			users: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,
			user: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
			activity: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
			clock: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
			play: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,
			loader: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spinning"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>`,
			x: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
			cloud_off: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22.61 16.95A5 5 0 0 0 18 10h-1.26a8 8 0 0 0-7.05-6M5 5a8 8 0 0 0 4 15h9a5 5 0 0 0 1.7-.3"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`
		};
		return icons[name] || '';
	}

	render() {
		if (!this.shadowRoot) return;

		this.shadowRoot.innerHTML = `
			<style>
				${ACCESSIBILITY_STYLES}
				${BUTTON_STYLES}
				${SECTION_HEADER_STYLES}
				:host {
					display: block;
					width: 100%;
					height: 100%;
				}

				.agents-container {
					height: 100%;
					display: flex;
					flex-direction: column;
					gap: 1.5rem;
					position: relative;
					overflow: hidden;
					box-sizing: border-box;
				}

				.section-header {
					display: flex;
					justify-content: space-between;
					align-items: center;
					margin-bottom: 0.5rem;
				}

				.title-group {
					display: flex;
					flex-direction: column;
				}

				.title-group h2 {
					margin: 0;
					font-size: 1.1rem;
					font-weight: 700;
					display: flex;
					align-items: center;
					gap: 0.5rem;
					background: var(--accent-gradient);
					-webkit-background-clip: text;
					-webkit-text-fill-color: transparent;
				}

				.title-group p {
					margin: 0;
					font-size: 0.75rem;
					color: var(--text-tertiary);
					display: flex;
					align-items: center;
					gap: 0.3rem;
				}

				.h-icon {
					color: #fff !important;
				}

				/* Personality Overview Styles */
				.personality-grid {
					display: grid;
					grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
					gap: 1rem;
					margin-bottom: 1rem;
				}

				.trait-badge {
					background: rgba(255, 255, 255, 0.03);
					border: 1px solid rgba(255, 255, 255, 0.05);
					border-radius: 0.75rem;
					padding: 0.75rem;
					display: flex;
					flex-direction: column;
					gap: 0.25rem;
				}

				.trait-label {
					font-size: 0.7rem;
					text-transform: uppercase;
					letter-spacing: 0.05em;
					color: var(--text-tertiary);
				}

				.trait-value {
					font-size: 0.9rem;
					font-weight: 600;
					color: var(--accent-primary);
				}

				.identity-block {
					display: grid;
					grid-template-columns: 1fr 1fr;
					gap: 1.5rem;
					background: rgba(0, 0, 0, 0.2);
					border-radius: 0.75rem;
					padding: 1.25rem;
					border: 1px solid rgba(255, 255, 255, 0.03);
				}

				.identity-item h4 {
					margin: 0 0 0.5rem 0;
					font-size: 0.8rem;
					color: var(--text-secondary);
					text-transform: uppercase;
				}

				.identity-item p {
					margin: 0;
					font-size: 0.95rem;
					color: var(--text-primary);
					line-height: 1.4;
				}

				/* Edit Form Styles */
				.edit-form {
					display: flex;
					flex-direction: column;
					gap: 1.25rem;
					animation: fadeIn 0.3s ease-out;
				}

				@keyframes fadeIn {
					from { opacity: 0; transform: translateY(5px); }
					to { opacity: 1; transform: translateY(0); }
				}

				.form-group {
					display: flex;
					flex-direction: column;
					gap: 0.5rem;
				}

				label {
					font-size: 0.85rem;
					color: var(--text-secondary);
					font-weight: 500;
				}

				input[type="text"], textarea {
					background: rgba(0, 0, 0, 0.2);
					border: 1px solid var(--border-color);
					border-radius: 0.5rem;
					padding: 0.75rem;
					color: var(--text-primary);
					font-family: inherit;
					font-size: 0.9rem;
					transition: border-color 0.2s;
				}

				input:focus, textarea:focus {
					outline: none;
					border-color: var(--accent-primary);
				}

				.range-group {
					display: grid;
					grid-template-columns: 120px 1fr 80px;
					align-items: center;
					gap: 1rem;
				}

				input[type="range"] {
					accent-color: var(--accent-primary);
					cursor: pointer;
				}

				.range-labels {
					display: flex;
					justify-content: space-between;
					font-size: 0.7rem;
					color: var(--text-tertiary);
					margin-top: -0.25rem;
				}

				/* Crews List Styles */
				.section-divider {
					border: 0;
					border-top: 1px solid var(--border-color);
					margin: 1rem 0;
					opacity: 0.5;
				}

				.crews-container {
					display: flex;
					flex-direction: column;
					gap: 1rem;
					overflow-y: auto;
					padding: 0.5rem;
				}

				.crew-card {
					background: rgba(255, 255, 255, 0.02);
					border: 1px solid var(--border-color);
					border-radius: 0.75rem;
					padding: 1.25rem;
					display: flex;
					flex-direction: column;
					gap: 0.75rem;
					transition: all 0.2s ease;
				}

				.crew-card:hover {
					border-color: var(--accent-primary);
					background: rgba(255, 255, 255, 0.04);
					transform: translateY(-2px);
				}

				.crew-header {
					display: flex;
					justify-content: space-between;
					align-items: flex-start;
				}

				.crew-title {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					font-weight: 600;
					color: var(--text-primary);
				}

				.status-badge {
					font-size: 0.6rem;
					padding: 0.2rem 0.5rem;
					border-radius: 0.5rem;
					text-transform: uppercase;
					font-weight: 700;
					flex-shrink: 0;
					white-space: nowrap;
				}

				.status-active { background: rgba(20, 184, 166, 0.1); color: #14B8A6; border: 1px solid rgba(20, 184, 166, 0.2); }
				.status-inactive { display: none; }

				.crew-desc {
					font-size: 0.85rem;
					color: var(--text-secondary);
					line-height: 1.5;
					margin: 0;
				}

				.characters-grid {
					display: flex;
					flex-wrap: wrap;
					gap: 0.5rem;
					margin-top: 0.5rem;
				}

				.character-badge {
					background: rgba(255, 255, 255, 0.03);
					padding: 0.5rem 0.75rem;
					border-radius: 0.75rem;
					font-size: 0.8rem;
					display: flex;
					flex-direction: column;
					gap: 0.2rem;
					border: 1px solid rgba(255, 255, 255, 0.05);
					flex: 0 1 auto;
					min-width: 180px;
				}

				.character-name {
					font-weight: 700;
					color: var(--text-primary);
					display: flex;
					align-items: center;
					gap: 0.4rem;
				}

				.character-role {
					font-size: 0.7rem;
					color: var(--text-tertiary);
					line-height: 1.3;
				}

				.crew-meta {
					display: flex;
					justify-content: space-between;
					align-items: center;
					margin-top: auto;
					padding-top: 0.75rem;
					border-top: 1px solid rgba(255, 255, 255, 0.03);
				}

				.schedule-tag {
					display: flex;
					align-items: center;
					gap: 0.4rem;
					font-size: 0.75rem;
					color: var(--text-tertiary);
				}

				.empty-state {
					grid-column: 1 / -1;
					padding: 3rem;
					text-align: center;
					color: var(--text-tertiary);
					display: flex;
					flex-direction: column;
					align-items: center;
					gap: 1rem;
				}

				.loading-state {
					grid-column: 1 / -1;
					padding: 3rem;
					text-align: center;
					color: var(--accent-primary);
				}

				.btn-actions {
					display: flex;
					justify-content: flex-end;
					gap: 1rem;
					margin-top: 1rem;
				}

				.spinning {
					animation: spin 2s linear infinite;
				}

				@keyframes spin {
					from { transform: rotate(0deg); }
					to { transform: rotate(360deg); }
				}
			</style>

			<div class="agents-container">
				<div class="section-header">
					<div class="title-group">
						<h2>
							<span style="color:var(--accent-primary)">${this.renderIcon('users', '1.2rem')}</span>
							Agents & Orchestration
						</h2>
						<p>
							${this.renderIcon('activity', '0.7rem')}
							Autonomous cycles run on-schedule. Results appear in chat.
						</p>
					</div>
					${!this.isEditing ? `
						<button class="edit-btn" id="edit-personality-btn" style="background:transparent; border:none; color:var(--text-tertiary); cursor:pointer; display:flex; align-items:center; gap:0.5rem; font-size:0.8rem;">
							${this.renderIcon('settings', '0.9rem')}
							${this.tr('edit_personality', 'Configure Personality')}
						</button>
					` : ''}
				</div>

				<div class="personality-viewport">
					${this.isEditing ? this.renderEditForm() : this.renderPersonalityOverview()}
				</div>

				<hr class="section-divider">

				<div class="crews-viewport">
					${this.renderCrews()}
				</div>
			</div>
		`;

		this.setupEventListeners();
	}

	private setupEventListeners() {
		const shadow = this.shadowRoot!;
		
		shadow.querySelector('#edit-personality-btn')?.addEventListener('click', () => {
			this.isEditing = true;
			this.render();
		});

		shadow.querySelector('#cancel-edit-btn')?.addEventListener('click', () => {
			this.isEditing = false;
			this.render();
		});

		shadow.querySelector('#save-personality-btn')?.addEventListener('click', () => this.savePersonality());

		shadow.querySelectorAll('.run-crew-btn').forEach(btn => {
			btn.addEventListener('click', () => {
				const id = btn.getAttribute('data-id');
				if (id) this.runCrew(id);
			});
		});

		// Range and Input sync
		if (this.isEditing && this.personality) {
			shadow.querySelectorAll('input[type="range"]').forEach(input => {
				input.addEventListener('input', (e: any) => {
					const id = input.id.replace('range-', '');
					(this.personality as any)[id] = parseInt(e.target.value);
				});
			});
			shadow.querySelector('#role-input')?.addEventListener('input', (e: any) => this.personality!.role = e.target.value);
			shadow.querySelector('#rel-input')?.addEventListener('input', (e: any) => this.personality!.relationship = e.target.value);
			shadow.querySelector('#values-input')?.addEventListener('input', (e: any) => this.personality!.values = e.target.value);
			shadow.querySelector('#behavior-input')?.addEventListener('input', (e: any) => this.personality!.behavior = e.target.value);
		}
	}

	private renderPersonalityOverview(): string {
		if (!this.personality) return '';
		const p = this.personality;
		return `
			<div class="personality-grid">
				<div class="trait-badge">
					<span class="trait-label">Communication</span>
					<span class="trait-value">${p.directness > 3 ? 'Concise' : 'Elaborate'}</span>
				</div>
				<div class="trait-badge">
					<span class="trait-label">Emotional Tone</span>
					<span class="trait-value">${p.warmth > 3 ? 'Empathetic' : 'Clinical'}</span>
				</div>
				<div class="trait-badge">
					<span class="trait-label">Agency</span>
					<span class="trait-value">${p.agency > 3 ? 'Proactive' : 'Reactive'}</span>
				</div>
				<div class="trait-badge">
					<span class="trait-label">Intellect</span>
					<span class="trait-value">${p.critique > 3 ? 'Challenging' : 'Agreeable'}</span>
				</div>
			</div>

			<div class="identity-block">
				<div class="identity-item">
					<h4>Identity Archetype</h4>
					<p>${p.role || 'Agent Operator'}</p>
				</div>
				<div class="identity-item">
					<h4>Relational Context</h4>
					<p>${p.relationship || 'System Intelligence'}</p>
				</div>
				<div class="identity-item" style="grid-column: span 2">
					<h4>Core Values</h4>
					<p>${p.values || 'Efficiency, accuracy, and systemic integrity.'}</p>
				</div>
			</div>
		`;
	}

	private renderEditForm(): string {
		if (!this.personality) return '';
		const p = this.personality;
		return `
			<div class="edit-form">
				<div class="form-group" style="display:grid; grid-template-columns:1fr 1fr; gap:1rem;">
					<div>
						<label>Core Identity / Archetype</label>
						<input type="text" id="role-input" value="${this.esc(p.role)}">
					</div>
					<div>
						<label>Relationship Context</label>
						<input type="text" id="rel-input" value="${this.esc(p.relationship)}">
					</div>
				</div>

				<div class="personality-grid">
					${(p.questions || []).filter((q:any) => q.type === 'range').map((q: any) => `
						<div class="form-group">
							<label>${q.label}</label>
							<input type="range" id="range-${q.id}" min="${q.min}" max="${q.max}" value="${(p as any)[q.id]}">
							<div class="range-labels">
								<span>${q.low}</span>
								<span>${q.high}</span>
							</div>
						</div>
					`).join('')}
				</div>

				<div class="form-group">
					<label>Core Values & Principles</label>
					<textarea id="values-input" rows="3">${this.esc(p.values)}</textarea>
				</div>

				<div class="form-group">
					<label>Behavioral Stylings</label>
					<textarea id="behavior-input" rows="3">${this.esc(p.behavior)}</textarea>
				</div>

				<div class="btn-actions">
					<button class="oz-btn oz-btn-secondary" id="cancel-edit-btn">${this.tr('cancel', 'Cancel')}</button>
					<button class="oz-btn oz-btn-primary" id="save-personality-btn" ${this.saving ? 'disabled' : ''}>
						${this.saving ? this.tr('saving', 'Saving...') : this.tr('save_personality', 'Save Agent State')}
					</button>
				</div>
			</div>
		`;
	}

	private renderCrews(): string {
		if (this.loading) return `<div class="loading-state">${this.tr('loading_crews', 'Hydrating Agent Registry...')}</div>`;
		
		if (this.crews.length === 0) {
			return `
				<div class="empty-state">
					<span style="opacity:0.2;">${this.renderIcon('cloud_off', '3rem')}</span>
					<p>${this.tr('no_crews_found', 'No Dify Crews provisioned or active.')}</p>
				</div>
			`;
		}

		return `
			<div class="crews-container">
				${this.crews.map(crew => {
					let sched = crew.schedule || 'On-demand';
					if (crew.feeds_briefing) {
						sched = `Pre-${crew.feeds_briefing.replace('/','')} briefing`;
						if (crew.briefing_day) sched += ` (${crew.briefing_day})`;
					}

					return `
						<div class="crew-card">
							<div class="crew-header">
								<div class="crew-title">
									<span style="color:var(--accent-primary)">${this.renderIcon('users', '1.2rem')}</span>
									${crew.name}
								</div>
								<span class="status-badge ${crew.dify_app_id ? 'status-active' : 'status-inactive'}">
									${crew.dify_app_id ? 'Active' : ''}
								</span>
							</div>

							<p class="crew-desc">${crew.description}</p>

							${crew.characters && crew.characters.length > 0 ? `
								<div class="characters-grid">
									${crew.characters.map(c => `
										<div class="character-badge">
											<div class="character-name">
												<span style="opacity:0.5; color:var(--accent-primary)">${this.renderIcon('user', '0.8rem')}</span>
												${this.esc(c.name)}
											</div>
											<div class="character-role">${this.esc(c.role)}</div>
										</div>
									`).join('')}
								</div>
							` : ''}

							<div class="crew-meta">
								<div class="schedule-tag">
									${this.renderIcon('clock', '0.8rem')}
									${sched}
								</div>
								<button class="run-crew-btn oz-btn oz-btn-ghost oz-btn-sm" data-id="${crew.id}" ${this.runningCrews.has(crew.id) ? 'disabled' : ''} style="display:flex; flex-direction:column; align-items:flex-end; padding: 0.2rem 0.6rem; min-width: 100px;">
									<div style="display:flex; align-items:center; gap:0.4rem; font-size:0.75rem; font-weight:700; color:var(--accent-primary);">
										${this.runningCrews.has(crew.id) ? this.renderIcon('loader', '0.8rem') : this.renderIcon('play', '0.8rem')}
										${this.tr('run_now', 'TRIGGER AGENT')}
									</div>
									<span style="font-size:0.6rem; opacity:0.4; font-weight:400;">Autonomous Cycle</span>
								</button>
							</div>
						</div>
					`;
				}).join('')}
			</div>
		`;
	}

	private esc(str: string): string {
		if (!str) return '';
		return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
	}
}

customElements.define('agents-widget', AgentsWidget);
