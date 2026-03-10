import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { initGoo } from '../services/gooStyles';

export class ZPersonality extends HTMLElement {
	private personality: any = null;
	private isEditing = false;
	private isLoading = true;
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
		this.loadTranslations().then(() => this.fetchData());
		initGoo(this);
		window.addEventListener('goo-changed', () => { initGoo(this); this.render(); });
	}

	async fetchData() {
		this.isLoading = true;
		this.render();
		try {
			const perRes = await fetch('/api/dashboard/personality');
			if (perRes.ok) this.personality = await perRes.json();
		} catch (e) {
			console.error('Failed to fetch personality data', e);
		} finally {
			this.isLoading = false;
			this.render();
		}
	}

	async savePersonality() {
		const shadow = this.shadowRoot!;
		const payload: any = { ...this.personality };
		delete payload.questions;

		this.personality.questions.forEach((q: any) => {
			const input = shadow.querySelector(`#input-${q.id}`) as any;
			if (input) payload[q.id] = q.type === 'range' ? parseInt(input.value) : input.value;
		});

		try {
			const res = await fetch('/api/dashboard/personality', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(payload)
			});
			if (res.ok) {
				const data = await res.json();
				this.personality = { ...data.personality, questions: this.personality.questions };
				this.isEditing = false;
				this.render();
				window.location.reload();
			}
		} catch (_e) {
			alert('Failed to save personality.');
		}
	}

	render() {
		if (!this.shadowRoot) return;

		const per = this.personality;
		const agentInitial = (per?.agent_name || 'Z').charAt(0).toUpperCase();

		this.shadowRoot.innerHTML = `
			<style>
				${BUTTON_STYLES}
				${ACCESSIBILITY_STYLES}
				${SECTION_HEADER_STYLES}
				${SCROLLBAR_STYLES}
				${EMPTY_STATE_STYLES}
				:host { display: block; height: 100%; font-family: 'Inter', system-ui, sans-serif; }
				.card { height: 100%; display: flex; flex-direction: column; gap: 1.25rem; color: var(--text-primary, hsla(0, 0%, 100%, 1)); }
				
				.header { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; flex-wrap: wrap; }
				/* Override h-icon for personality: show agent initial, not SVG */
				h2 .h-icon {
					font-weight: 800; font-size: 0.8rem;
				}

				.edit-btn {
					padding: 0.18rem 0.55rem;
					font-size: 0.7rem;
					text-transform: uppercase;
					letter-spacing: 0.05em;
				}

				.tabs { display: flex; gap: 1rem; border-bottom: 1px solid rgba(255,255,255,0.05); }
				.edit-btn:focus-visible, .save-btn:focus-visible, .cancel-btn:focus-visible { outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); outline-offset: 2px; border-radius: 4px; }
				input[type="text"]:focus-visible, textarea:focus-visible, select:focus-visible, input[type="range"]:focus-visible, input[type="color"]:focus-visible { outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); outline-offset: 2px; }

				.content { flex: 1; overflow-y: auto; padding-right: 4px; }

				.trait-grid { display: grid; gap: 1rem; margin-top: 0.5rem; }
				.trait-item { 
					background: var(--surface-card, hsla(0,0%,100%,0.05)); padding: 0.75rem 1rem; border-radius: 0.75rem;
					border: 1px solid var(--border-subtle, hsla(0,0%,100%,0.1));
					transition: background var(--duration-fast, 0.2s);
					position: relative;
					overflow: hidden;
				}
				.trait-item.oz-goo-container {
					border: none;
					background: var(--accent-primary, hsla(173, 80%, 40%, 0.1));
				}
				.trait-indicator {
					position: absolute;
					bottom: 0;
					left: 0;
					height: 2px;
					background: linear-gradient(90deg, var(--accent-primary), var(--accent-secondary));
					width: 100%;
					opacity: 0.3;
				}
				.trait-item.oz-goo-container .trait-indicator {
					height: 4px;
					border-radius: 2px;
					bottom: 4px;
					left: 4px;
					width: calc(100% - 8px);
					opacity: 0.6;
				}
				.trait-label { font-size: 0.65rem; color: var(--text-muted, hsla(0,0%,100%,0.4)); text-transform: uppercase; margin-bottom: 4px; display: block; }
				.trait-value { font-size: 0.9rem; color: var(--text-primary, hsla(0, 0%, 100%, 1)); font-weight: 500; }

				.form-group { margin-bottom: 1.25rem; }
				.form-label { font-size: 0.75rem; color: var(--accent-primary, hsla(173, 80%, 40%, 1)); font-weight: 700; display: block; margin-bottom: 0.5rem; }
				input[type="text"], textarea {
					background: var(--surface-card-subtle, hsla(0,0%,0%,0.3)); border: 1px solid var(--border-subtle, hsla(0,0%,100%,0.1));
					color: var(--text-primary, hsla(0, 0%, 100%, 1)); padding: 12px; border-radius: 0.5rem; width: 100%; box-sizing: border-box;
					font-family: inherit; font-size: 0.9rem; min-height: 44px;
				}
				textarea { height: 120px; resize: vertical; }
				
				.range-container { display: flex; align-items: center; gap: 1rem; min-height: 44px; }
				.range-tag { font-size: 0.65rem; color: var(--text-muted, hsla(0,0%,100%,0.4)); width: 60px; }
				input[type="range"] { flex: 1; accent-color: var(--accent-primary, hsla(173, 80%, 40%, 1)); cursor: pointer; min-height: 44px; }

				.actions { display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.25rem; }

				@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
				
				@media (prefers-reduced-motion: reduce) {
					.edit-btn { transition: none !important; animation: none !important; }
				}
				@media (forced-colors: active) {
					input[type="range"] { accent-color: Highlight; }
				}
			</style>

			<div class="card">
				<div class="header">
					<h2>
						<div class="h-icon" aria-hidden="true">${agentInitial}</div>
						${this.isEditing ? this.tr('agent_config', 'Config') : this.tr('agent_personality', 'Personality')}
					</h2>
					${!this.isEditing && !this.isLoading ? `<button class="edit-btn" id="edit-trigger" aria-label="${this.tr('refine', 'Refine')} — ${this.tr('aria_edit_personality', 'Edit agent personality settings')}">${this.tr('refine', 'Refine')}</button>` : ''}
				</div>

				<div class="content" id="tabpanel-main">
					${this.isLoading ? `<div class="empty-state">${this.tr('aligning', 'Aligning neural paths...')}</div>` : ''}
					
					${!this.isLoading && this.isEditing ? `
						<div class="form">
							${per.questions.filter((q: any) => q.id !== 'agent_name' && q.type !== 'select').map((q: any) => `
								<div class="form-group">
									<label class="form-label">${q.label}</label>
									${q.type === 'range' ? `
										<div class="range-container">
										<span class="range-tag" aria-hidden="true">${q.low}</span>
										<input type="range" id="input-${q.id}" min="${q.min}" max="${q.max}" value="${per[q.id] || 3}" aria-label="${q.label}" aria-valuenow="${per[q.id] || 3}" aria-valuemin="${q.min}" aria-valuemax="${q.max}" aria-valuetext="${per[q.id] || 3} of ${q.max}">
										<span class="range-tag" style="text-align: right;" aria-hidden="true">${q.high}</span>
										</div>
									` : q.type === 'textarea' ? `
										<textarea id="input-${q.id}" placeholder="${q.placeholder}">${per[q.id] || ''}</textarea>
							` : q.type === 'color' ? `
										<div style="display: flex; align-items: center; gap: 1rem;">
											<input type="color" id="input-${q.id}" value="${per[q.id] || '#ffffff'}" style="width: 40px; height: 32px; padding: 2px; border: none; cursor: pointer; background: transparent;">
											<span style="font-size: 0.75rem; color: rgba(255,255,255,0.4);">${per[q.id] || ''}</span>
										</div>
									` : `
										<input type="text" id="input-${q.id}" placeholder="${q.placeholder}" value="${per[q.id] || ''}">
									`}
								</div>
							`).join('')}
							<div class="actions">
								<button class="oz-btn oz-btn-secondary" id="cancel-trigger">${this.tr('cancel', 'Cancel')}</button>
								<button class="oz-btn oz-btn-primary" id="save-trigger">${this.tr('save_persona', 'Save Persona')}</button>
							</div>
						</div>
					` : !this.isLoading ? `
						<div class="trait-grid">
							${(() => {
					const isGoo = localStorage.getItem('goo-mode') === 'true';
					const traits = [
						{ label: this.tr('core_identity', 'Core Identity'), value: per?.role || 'Agent Operator' },
						{ label: this.tr('communication', 'Communication'), value: `${['', 'Elaborate', 'Nuanced', 'Balanced', 'Direct', 'Concise'][per?.directness || 3]} (${per?.directness}/5)` }
					];
					return traits.map(t => `
									<div class="trait-item ${isGoo ? 'oz-goo-container' : ''}">
										<span class="trait-label">${t.label}</span>
										<div class="trait-value">${t.value}</div>
										<div class="trait-indicator" aria-hidden="true"></div>
									</div>
								`).join('');
				})()}
						</div>
					` : ''}
				</div>
			</div>
		`;

		this.shadowRoot.querySelector('#edit-trigger')?.addEventListener('click', () => { this.isEditing = true; this.render(); });
		this.shadowRoot.querySelector('#cancel-trigger')?.addEventListener('click', () => { this.isEditing = false; this.render(); });
		this.shadowRoot.querySelector('#save-trigger')?.addEventListener('click', () => this.savePersonality());

	}
}

customElements.define('z-personality', ZPersonality);
