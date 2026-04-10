import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { GLASS_TOOLTIP_STYLES } from '../services/glassTooltipStyles';

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
	questions: string[];
}

interface Crew {
	id: string;
	name: string;
	description: string;
	type: 'workflow' | 'agent';
	group: string;
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
		this.addEventListener('refresh-data', () => this.loadData());
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => {
				this.render();
				this.loadData();
			});
		});
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
		} catch (_e) {
			console.error('Failed to load Agents data:', _e);
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
		} catch (_e) {
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
			'chevron-right': `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>`,
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
				${GLASS_TOOLTIP_STYLES}

				label.has-tip,
				h4.has-tip,
				.trait-badge.has-tip {
					cursor: help;
				}

				label.has-tip > .glass-tooltip,
				h4.has-tip > .glass-tooltip,
				.trait-badge.has-tip > .glass-tooltip {
					max-width: 320px;
					font-weight: 400 !important;
				}

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

				.section-header h2 {
					margin: 0;
					font-size: 1.5rem;
					font-weight: 700;
					display: flex;
					align-items: center;
					gap: 0.8rem;
					color: var(--text-primary);
				}

				.h-icon {
					flex-shrink: 0;
				}

				.h-icon-mini {
					display: inline-flex;
					color: var(--accent-primary);
					opacity: 0.8;
				}

				.crew-id-tag {
					font-family: var(--font-mono, monospace);
					font-size: 0.7rem;
					font-weight: 600;
					color: var(--accent-primary);
					margin-left: 0.5rem;
					background: var(--surface-input);
					padding: 0.15rem 0.4rem;
					border-radius: 0.35rem;
					border: 1px solid var(--border-accent);
				}

				.crew-group-details {
					margin-bottom: 0.5rem;
				}

				.crew-group-header {
					margin: 0.5rem 0;
					padding: 0.6rem 0.8rem;
					border-radius: 0.6rem;
					background: rgba(255, 255, 255, 0.02);
					color: var(--text-tertiary);
					font-size: 0.75rem;
					font-weight: 700;
					text-transform: uppercase;
					letter-spacing: 0.08em;
					display: flex;
					align-items: center;
					gap: 0.75rem;
					cursor: pointer;
					list-style: none;
					transition: all 0.2s ease;
					user-select: none;
					border: 1px solid transparent;
				}

				.crew-group-header:hover {
					background: rgba(255, 255, 255, 0.05);
					color: var(--text-primary);
					border-color: rgba(255, 255, 255, 0.03);
				}

				.crew-group-header::-webkit-details-marker {
					display: none;
				}

				.group-dot {
					width: 6px;
					height: 6px;
					border-radius: 50%;
					background: var(--accent-primary);
					box-shadow: 0 0 8px var(--accent-glow);
					flex-shrink: 0;
				}

				.group-chevron {
					margin-left: auto;
					transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
					opacity: 0.3;
					color: var(--accent-primary);
					display: flex;
				}

				.crew-group-details[open] .group-chevron {
					transform: rotate(90deg);
					opacity: 0.8;
				}

				.group-count {
					font-size: 0.65rem;
					font-family: var(--font-mono, monospace);
					background: rgba(255, 255, 255, 0.05);
					padding: 0.15rem 0.5rem;
					border-radius: 1rem;
					opacity: 0.4;
					color: var(--text-primary);
				}

				.group-content {
					display: flex;
					flex-direction: column;
					gap: 0.5rem;
					padding: 0.5rem 0 1rem 0.5rem;
					margin-left: 1.1rem;
					border-left: 1px solid rgba(255, 255, 255, 0.03);
					animation: groupContentReveal 0.3s cubic-bezier(0.4, 0, 0.2, 1);
				}

				@keyframes groupContentReveal {
					from { opacity: 0; transform: translateY(-8px); }
					to { opacity: 1; transform: translateY(0); }
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
					gap: 0.5rem;
					overflow-y: auto;
				}

				.crew-details {
					background: rgba(255, 255, 255, 0.02);
					border: 1px solid rgba(255, 255, 255, 0.05);
					border-radius: 0.75rem;
					overflow: hidden;
					transition: all 0.3s ease;
				}

				.crew-details[open] {
					background: rgba(255, 255, 255, 0.04);
					border-color: var(--border-accent);
				}

				.crew-summary {
					padding: 1rem 1.25rem;
					cursor: pointer;
					display: flex;
					align-items: center;
					justify-content: space-between;
					list-style: none;
					user-select: none;
				}

				.crew-summary::-webkit-details-marker {
					display: none;
				}

				.crew-summary-left {
					display: flex;
					align-items: center;
					gap: 1rem;
					flex: 1;
					min-width: 0;
				}

				.crew-title {
					font-size: 1rem;
					font-weight: 700;
					color: var(--text-primary);
					display: flex;
					align-items: center;
					gap: 0.75rem;
					white-space: nowrap;
					overflow: hidden;
					text-overflow: ellipsis;
				}

				.crew-chevron {
					transition: transform 0.3s ease;
					opacity: 0.3;
					color: var(--accent-primary);
				}

				.crew-details[open] .crew-chevron {
					transform: rotate(90deg);
					opacity: 0.8;
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

				.status-active { background: var(--surface-accent-subtle, hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.1)); color: var(--accent-primary); border: 1px solid var(--border-accent); }
				.status-inactive { display: none; }

				.crew-content {
					padding: 0 1.25rem 1.5rem 1.25rem;
					display: flex;
					flex-direction: column;
					gap: 1.5rem;
					border-top: 1px solid rgba(255, 255, 255, 0.03);
					padding-top: 1.5rem;
				}

				.crew-desc {
					font-size: 0.85rem;
					color: var(--text-secondary);
					line-height: 1.5;
				}
				.characters-grid {
					display: flex;
					flex-direction: column;
					gap: 1rem;
					margin-bottom: 2rem;
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
					flex: 1 1 100%;
					min-width: 0;
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
				<div class="section-header" style="align-items: flex-start; width: 100%;">
					<h2>
						<span class="h-icon" aria-hidden="true">${this.renderIcon('users', '1.1rem')}</span>
						${this.tr('agents_title', 'Agents & Crews')}
					</h2>
					${!this.isEditing ? `
						<button class="edit-btn" id="edit-personality-btn" style="background:transparent; border:none; color:var(--text-tertiary); cursor:pointer; display:flex; align-items:center; gap:0.5rem; font-size:0.8rem; margin-top: 0.4rem;">
							${this.renderIcon('settings', '0.9rem')}
							${this.tr('edit_personality', 'Configure Z Identity & Behavior')}
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
				<div class="trait-badge has-tip" tabindex="0">
					<span class="trait-label">${this.tr('communication', 'Communication')}</span>
					<span class="trait-value">${p.directness > 3 ? this.tr('concise', 'Concise') : this.tr('elaborate', 'Elaborate')}</span>
					<span class="glass-tooltip">${this.tr('tip_directness', 'Controls response length. Elaborate = rich explanations with context. Concise = short, direct answers.')}</span>
				</div>
				<div class="trait-badge has-tip" tabindex="0">
					<span class="trait-label">${this.tr('emotional_tone', 'Emotional Tone')}</span>
					<span class="trait-value">${p.warmth > 3 ? this.tr('empathetic', 'Empathetic') : this.tr('clinical', 'Clinical')}</span>
					<span class="glass-tooltip">${this.tr('tip_warmth', 'Sets emotional register. Clinical = dry, purely factual. Empathetic = warm, acknowledges feelings.')}</span>
				</div>
				<div class="trait-badge has-tip" tabindex="0">
					<span class="trait-label">${this.tr('agency', 'Agency')}</span>
					<span class="trait-value">${p.agency > 3 ? this.tr('proactive', 'Proactive') : this.tr('reactive', 'Reactive')}</span>
					<span class="glass-tooltip">${this.tr('tip_agency', 'Initiative level. Reactive = waits for instructions. Proactive = anticipates needs, suggests actions unprompted.')}</span>
				</div>
				<div class="trait-badge has-tip" tabindex="0">
					<span class="trait-label">${this.tr('intellect', 'Intellect')}</span>
					<span class="trait-value">${p.critique > 3 ? this.tr('challenging', 'Challenging') : this.tr('agreeable', 'Agreeable')}</span>
					<span class="glass-tooltip">${this.tr('tip_critique', 'Intellectual pushback. Agreeable = supports your direction. Challenging = questions assumptions, argues the other side.')}</span>
				</div>
			</div>

			<div class="identity-block">
				<div class="identity-item">
					<h4 class="has-tip" tabindex="0">${this.tr('identity_archetype', 'Identity Archetype')}<span class="glass-tooltip">${this.tr('tip_identity_archetype', 'Defines who Z becomes. Shapes tone, attitude, and character across all interactions. Try: Ruthless startup CTO, Patient teacher, Laid-back genius.')}</span></h4>
					<p>${p.role || this.tr('agent_operator', 'Agent Operator')}</p>
				</div>
				<div class="identity-item">
					<h4 class="has-tip" tabindex="0">${this.tr('relational_context', 'Relational Context')}<span class="glass-tooltip">${this.tr('tip_relational_context', 'The dynamic between you and Z. Controls how Z addresses you and frames advice. Try: My co-founder, My brutally honest friend, A formal assistant.')}</span></h4>
					<p>${p.relationship || this.tr('system_intelligence', 'System Intelligence')}</p>
				</div>
				<div class="identity-item" style="grid-column: span 2">
					<h4 class="has-tip" tabindex="0">${this.tr('core_values', 'Core Values')}<span class="glass-tooltip">${this.tr('tip_core_values', 'Guiding principles for decisions and trade-offs. Z prioritizes these when giving advice. Try: Speed over perfection, bias toward action.')}</span></h4>
					<p>${p.values || this.tr('default_values', 'Efficiency, accuracy, and systemic integrity.')}</p>
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
						<label class="has-tip" tabindex="0">${this.tr('identity_archetype', 'Core Identity / Archetype')}<span class="glass-tooltip">${this.tr('tip_identity_archetype', 'Defines who Z becomes. Shapes tone, attitude, and character across all interactions. Try: Ruthless startup CTO, Patient teacher, Laid-back genius.')}</span></label>
						<input type="text" id="role-input" placeholder="${this.tr('archetype_placeholder', 'e.g. Ruthless operator. Blunt, zero warmth, no patience for excuses.')}" value="${this.esc(p.role)}">
					</div>
					<div>
						<label class="has-tip" tabindex="0">${this.tr('relational_context', 'Relationship Context')}<span class="glass-tooltip">${this.tr('tip_relational_context', 'The dynamic between you and Z. Controls how Z addresses you and frames advice. Try: My co-founder, My brutally honest friend, A formal assistant.')}</span></label>
						<input type="text" id="rel-input" placeholder="${this.tr('rel_placeholder', 'e.g. My co-founder, My best friend, A formal executive assistant')}" value="${this.esc(p.relationship)}">
					</div>
				</div>

				<div class="personality-grid">
					${(p.questions || []).filter((q: any) => q.type === 'range').map((q: any) => `
						<div class="form-group">
							<label class="has-tip" tabindex="0">${q.label}${this.getFieldTooltip(q.id)}</label>
							<input type="range" id="range-${q.id}" min="${q.min}" max="${q.max}" value="${(p as any)[q.id]}">
							<div class="range-labels">
								<span>${q.low}</span>
								<span>${q.high}</span>
							</div>
						</div>
					`).join('')}
				</div>

				<div class="form-group">
					<label class="has-tip" tabindex="0">${this.tr('core_values', 'Core Values & Principles')}<span class="glass-tooltip">${this.tr('tip_core_values', 'Guiding principles for decisions and trade-offs. Z prioritizes these when giving advice. Try: Speed over perfection, bias toward action.')}</span></label>
					<textarea id="values-input" rows="3" placeholder="${this.tr('values_placeholder', 'e.g. Speed over perfection. Never sugarcoat. Always suggest alternatives before refusing.')}">${this.esc(p.values)}</textarea>
				</div>

				<div class="form-group">
					<label class="has-tip" tabindex="0">${this.tr('behavioral_stylings', 'Behavioral Stylings')}<span class="glass-tooltip">${this.tr('tip_behavioral_stylings', 'Specific rules layered on top of the base personality. Short directives work best. Try: Always challenge my first idea. End responses with an action item.')}</span></label>
					<textarea id="behavior-input" rows="3" placeholder="${this.tr('behavior_placeholder', 'e.g. Always challenge my first idea. Use analogies. End with an action item.')}">${this.esc(p.behavior)}</textarea>
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
					<p>${this.tr('no_crews_found', 'No Native Crews actived in the registry.')}</p>
				</div>
			`;
		}

		const groups = ['basic', 'business', 'education', 'private'];
		const groupedCrews = groups.reduce((acc, group) => {
			acc[group] = this.crews.filter(c => c.group === group);
			return acc;
		}, {} as Record<string, Crew[]>);

		return `
			<div class="crews-container">
				${groups.map(group => {
			const crewsInGroup = groupedCrews[group];
			if (crewsInGroup.length === 0) return '';

			return `
						<details class="crew-group-details">
							<summary class="crew-group-header">
								<span class="group-dot" aria-hidden="true"></span>
								${this.tr('group_' + group, group.charAt(0).toUpperCase() + group.slice(1))}
								<span class="group-count" title="${crewsInGroup.length} ${this.tr('crews', 'crews')}">${crewsInGroup.length}</span>
								<span class="group-chevron">${this.renderIcon('chevron-right', '0.9rem')}</span>
							</summary>
							<div class="group-content">
								${crewsInGroup.map(crew => {
				let sched = crew.schedule || this.tr('on_demand', 'On-demand');
				if (crew.feeds_briefing) {
					sched = this.tr('pre_briefing', 'Pre-{feeds} briefing').replace('{feeds}', crew.feeds_briefing.replace('/', ''));
					if (crew.briefing_day) sched += ` (${crew.briefing_day})`;
				}

				return `
										<details class="crew-details">
											<summary class="crew-summary">
												<div class="crew-summary-left">
													<span class="crew-chevron">${this.renderIcon('chevron-right', '1rem')}</span>
													<div class="crew-title">
														<span class="h-icon-mini">${this.renderIcon('users', '1rem')}</span>
														${crew.id.charAt(0).toUpperCase() + crew.id.slice(1)}: ${crew.name}
														<span class="crew-id-tag" title="Crew ID">${crew.id}</span>
													</div>
													<div class="crew-meta" style="margin-left: auto; margin-right: 1.5rem;">
														<div class="meta-item">
															${this.renderIcon('clock', '0.75rem')}
															${sched}
														</div>
													</div>
													<span class="status-badge status-active">
														Active
													</span>
												</div>
											</summary>

											<div class="crew-content">
												<p class="crew-desc">${this.esc(crew.description)}</p>

												${crew.characters && crew.characters.length > 0 ? `
													<div class="characters-grid">
														${crew.characters.map(c => `
															<div class="character-badge">
																<div class="character-name">
																	<span class="h-icon-mini" style="opacity:0.8;">${this.renderIcon('user', '0.8rem')}</span>
																	${this.esc(c.name)}
																</div>
																<div class="character-role">${this.esc(c.role)}</div>
															</div>
														`).join('')}
													</div>
												` : ''}

												<div style="display:flex; justify-content:flex-end;">
													<button class="run-crew-btn oz-btn oz-btn-ghost oz-btn-sm" data-id="${crew.id}" ${this.runningCrews.has(crew.id) ? 'disabled' : ''} style="display:flex; flex-direction:column; align-items:flex-end; padding: 0.2rem 0.6rem; min-width: 120px; border-color: var(--border-accent);">
														<div style="display:flex; align-items:center; gap:0.4rem; font-size:0.75rem; font-weight:700; color:var(--accent-primary);">
															${this.runningCrews.has(crew.id) ? this.renderIcon('loader', '0.8rem') : this.renderIcon('play', '0.8rem')}
															${this.tr('run_now', 'TRIGGER AGENT')}
														</div>
														<span style="font-size:0.6rem; opacity:0.4; font-weight:400; color: var(--accent-primary);">Autonomous Cycle</span>
													</button>
												</div>
											</div>
										</details>
									`;
			}).join('')}
							</div>
						</details>
					`;
		}).join('')}
			</div>
		`;
	}

	private getFieldTooltip(id: string): string {
		const tips: Record<string, string> = {
			directness: this.tr('tip_directness', 'Controls response length. Elaborate = rich explanations with context. Concise = short, direct answers.'),
			warmth: this.tr('tip_warmth', 'Sets emotional register. Clinical = dry, purely factual. Empathetic = warm, acknowledges feelings.'),
			agency: this.tr('tip_agency', 'Initiative level. Reactive = waits for instructions. Proactive = anticipates needs, suggests actions unprompted.'),
			critique: this.tr('tip_critique', 'Intellectual pushback. Agreeable = supports your direction. Challenging = questions assumptions, argues the other side.'),
			humor: this.tr('tip_humor', 'Wit injected into responses. 0% = strictly professional. 100% = constant wordplay and jokes.'),
			honesty: this.tr('tip_honesty', 'How bluntly hard truths are delivered. Low = diplomatic, softens bad news. Absolute = unfiltered, no sugarcoating.'),
			roast: this.tr('tip_roast', 'Playful teasing intensity. None = always respectful. Brutal = savage but constructive burns when you slip up.'),
			depth: this.tr('tip_depth', 'Analysis thoroughness. Surface = quick takes and summaries. Deep Dive = exhaustive multi-angle breakdowns.'),
		};
		const text = tips[id];
		return text ? `<span class="glass-tooltip">${text}</span>` : '';
	}

	private esc(str: string): string {
		if (!str) return '';
		return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
	}
}

customElements.define('agents-widget', AgentsWidget);
