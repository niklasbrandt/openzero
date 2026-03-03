import { BUTTON_STYLES } from '../services/buttonStyles';

export class ZPersonality extends HTMLElement {
	private personality: any = null;
	private protocols: any[] = [];
	private activeTab: 'personality' | 'protocols' = 'personality';
	private isEditing = false;
	private isLoading = true;
	private t: Record<string, string> = {};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	private async loadTranslations() {
		try {
			const res = await fetch('/api/dashboard/translations');
			if (res.ok) this.t = await res.json();
		} catch (_) { }
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] || fallback;
	}

	connectedCallback() {
		this.loadTranslations().then(() => this.fetchData());
	}

	async fetchData() {
		this.isLoading = true;
		this.render();
		try {
			const [perRes, protRes] = await Promise.all([
				fetch('/api/dashboard/personality'),
				fetch('/api/dashboard/protocols')
			]);
			if (perRes.ok) this.personality = await perRes.json();
			if (protRes.ok) {
				const data = await protRes.json();
				this.protocols = data.tools || [];
			}
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
			}
		} catch (e) {
			alert('Failed to save personality.');
		}
	}

	render() {
		if (!this.shadowRoot) return;

		const per = this.personality;
		const prot = this.protocols;
		const agentInitial = (per?.agent_name || 'Z').charAt(0).toUpperCase();

		this.shadowRoot.innerHTML = `
			<style>
				${BUTTON_STYLES}
				:host { display: block; height: 100%; font-family: 'Inter', system-ui, sans-serif; }
				.card { height: 100%; display: flex; flex-direction: column; gap: 1.25rem; color: #fff; }
				
				.header { display: flex; justify-content: space-between; align-items: center; }
				h2 { margin: 0; font-size: 1.5rem; display: flex; align-items: center; gap: 0.5rem; color: #fff; font-weight: bold; letter-spacing: 0.02em; }
				.icon {
					width: 28px; height: 28px;
					background: linear-gradient(135deg, var(--accent-color) 0%, var(--accent-secondary) 100%);
					border-radius: 0.4rem; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
					font-weight: 800; font-size: 0.8rem;
				}
				.subtitle { font-size: 0.65rem; font-weight: 400; color: rgba(255, 255, 255, 0.3); margin-left: 0.5rem; text-transform: uppercase; letter-spacing: 0.1em; }

				.edit-btn {
					padding: 0.18rem 0.55rem;
					font-size: 0.7rem;
					text-transform: uppercase;
					letter-spacing: 0.05em;
				}

				.tabs { display: flex; gap: 1rem; border-bottom: 1px solid rgba(255,255,255,0.05); }
				.tab { 
					padding: 0.5rem 0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; 
					color: rgba(255,255,255,0.4); cursor: pointer; border-bottom: 2px solid transparent;
					transition: all 0.2s;
				}
				.tab.active { color: #14B8A6; border-color: #14B8A6; }
				.tab:focus-visible { outline: 2px solid #14B8A6; outline-offset: 2px; border-radius: 2px 2px 0 0; }
				.edit-btn:focus-visible, .save-btn:focus-visible, .cancel-btn:focus-visible { outline: 2px solid #14B8A6; outline-offset: 2px; border-radius: 4px; }
				input[type="text"]:focus-visible, textarea:focus-visible, select:focus-visible, input[type="range"]:focus-visible, input[type="color"]:focus-visible { outline: 2px solid #14B8A6; outline-offset: 2px; }
				.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
				@media (prefers-reduced-motion: reduce) {
					*, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
				}

				.content { flex: 1; overflow-y: auto; padding-right: 4px; }
				.content::-webkit-scrollbar { width: 4px; }
				.content::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }

				.trait-grid { display: grid; gap: 1rem; margin-top: 0.5rem; }
				.trait-item { 
					background: rgba(20, 184, 166, 0.03); padding: 0.75rem 1rem; border-radius: 0.75rem;
					border: 1px solid rgba(255,255,255,0.05);
				}
				.trait-label { font-size: 0.65rem; color: rgba(255,255,255,0.4); text-transform: uppercase; margin-bottom: 4px; display: block; }
				.trait-value { font-size: 0.9rem; color: #fff; font-weight: 500; }

				.form-group { margin-bottom: 1.25rem; }
				.form-label { font-size: 0.75rem; color: #14B8A6; font-weight: 700; display: block; margin-bottom: 0.5rem; }
				input[type="text"], textarea {
					background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1);
					color: #fff; padding: 10px; border-radius: 0.5rem; width: 100%; box-sizing: border-box;
					font-family: inherit; font-size: 0.85rem;
				}
				textarea { height: 80px; resize: none; }
				
				.range-container { display: flex; align-items: center; gap: 1rem; }
				.range-tag { font-size: 0.65rem; color: rgba(255,255,255,0.4); width: 60px; }
				input[type="range"] { flex: 1; accent-color: #14B8A6; cursor: pointer; }

				.actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 1rem; }


				.prot-list { display: flex; flex-direction: column; gap: 0.75rem; margin-top: 0.5rem; }
				.prot-item { 
					background: rgba(255, 255, 255, 0.03); padding: 0.75rem 1rem; border-radius: 0.75rem;
					border-left: 3px solid #0066FF; animation: slideIn 0.3s ease-out backwards;
				}
				.prot-name { font-size: 0.8rem; font-weight: 700; letter-spacing: 0.02em; display: block; margin-bottom: 0.25rem; }
				.prot-desc { font-size: 0.75rem; color: rgba(255,255,255,0.5); line-height: 1.4; }

				@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
				@keyframes slideIn { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }

				.empty { text-align: center; padding: 2rem; color: rgba(255,255,255,0.2); font-size: 0.85rem; font-style: italic; }
			</style>

			<div class="card">
				<div class="header">
					<h2>
						<div class="icon" aria-hidden="true">${agentInitial}</div>
						${this.isEditing ? this.tr('agent_config', 'Agent Config') : (this.activeTab === 'personality' ? this.tr('agent_personality', 'Agent Personality') : this.tr('agent_protocols', 'Agent Protocols'))}
					</h2>
					${!this.isEditing && !this.isLoading && this.activeTab === 'personality' ? `<button class="edit-btn" id="edit-trigger" aria-label="Edit agent personality settings">${this.tr('refine', 'Refine')}</button>` : ''}
				</div>

				${!this.isEditing ? `
					<div class="tabs" role="tablist" aria-label="${this.tr('aria_personality_views', 'Personality views')}">
						<div class="tab ${this.activeTab === 'personality' ? 'active' : ''}" id="tab-per" role="tab" aria-selected="${this.activeTab === 'personality'}" tabindex="${this.activeTab === 'personality' ? '0' : '-1'}">${this.tr('tab_identity', 'Identity')}</div>
						<div class="tab ${this.activeTab === 'protocols' ? 'active' : ''}" id="tab-prot" role="tab" aria-selected="${this.activeTab === 'protocols'}" tabindex="${this.activeTab === 'protocols' ? '0' : '-1'}">${this.tr('tab_protocols', 'Protocols')}</div>
					</div>
				` : ''}

				<div class="content" role="tabpanel" id="tabpanel-main" aria-labelledby="${this.activeTab === 'personality' ? 'tab-per' : 'tab-prot'}">
					${this.isLoading ? `<div class="empty">${this.tr('aligning', 'Aligning neural paths...')}</div>` : ''}
					
					${!this.isLoading && this.isEditing ? `
						<div class="form">
							${per.questions.map((q: any) => `
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
									` : q.type === 'select' ? `
										<select id="input-${q.id}" class="theme-selector">
											${q.options.map((opt: any) => `
												<option value="${opt.value}" ${per[q.id] === opt.value ? 'selected' : ''} data-colors='${JSON.stringify(opt.colors)}'>${opt.label}</option>
											`).join('')}
										</select>
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
								<button class="cancel-btn" id="cancel-trigger">${this.tr('cancel', 'Cancel')}</button>
								<button class="save-btn" id="save-trigger">${this.tr('save_persona', 'Save Persona')}</button>
							</div>
						</div>
					` : !this.isLoading && this.activeTab === 'personality' ? `
						<div class="trait-grid">
							<div class="trait-item">
								<span class="trait-label">${this.tr('digital_avatar', 'Digital Avatar')}</span>
								<div class="trait-value" style="color: #14B8A6; font-weight: 800; letter-spacing: 0.05em;">${per?.agent_name || 'Z'}</div>
							</div>
							<div class="trait-item">
								<span class="trait-label">${this.tr('core_identity', 'Core Identity')}</span>
								<div class="trait-value">${per?.role || 'Agent Operator'}</div>
							</div>
							<div class="trait-item" style="display: flex; justify-content: space-between;">
								<div>
									<span class="trait-label">${this.tr('humor_score', 'Humor Score')}</span>
									<div class="trait-value" style="color: #0066FF;">${per?.humor || 0}/10</div>
								</div>
								<div style="text-align: center;">
									<span class="trait-label">${this.tr('roast_level', 'Roast Level')}</span>
									<div class="trait-value" style="color: #EF4444;">${per?.roast || 0}/5</div>
								</div>
								<div style="text-align: right;">
									<span class="trait-label">${this.tr('honesty_score', 'Honesty Score')}</span>
									<div class="trait-value" style="color: #14B8A6;">${per?.honesty || 0}/10</div>
								</div>
							</div>
							<div class="trait-item">
								<span class="trait-label">${this.tr('communication', 'Communication')}</span>
								<div class="trait-value">${['', 'Elaborate', 'Nuanced', 'Balanced', 'Direct', 'Concise'][per?.directness || 3]} (${per?.directness}/5)</div>
							</div>
						</div>
					` : ''}

					${!this.isLoading && !this.isEditing && this.activeTab === 'protocols' ? `
						<div class="prot-explanation" style="font-size: 0.75rem; color: rgba(255,255,255,0.4); margin-bottom: 1rem; line-height: 1.4; padding: 0.5rem; background: rgba(0,102,255,0.05); border-radius: 4px; border-left: 2px solid #0066FF;">
							Operational Protocols are the agent's internal "Action Tags". They define the specific strategic actions ${per?.agent_name || 'Z'} can perform across integrated services. These are core system capabilities.
						</div>
					<div class="prot-list" role="list">
						${prot.map((p: any, i: number) => `
							<div class="prot-item" role="listitem" style="animation-delay: ${i * 0.05}s">
								<span class="prot-name" style="display: flex; align-items: center; gap: 0.5rem;">
									<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
										${p.name.replace(/_/g, ' ')}
									</span>
									<span class="prot-desc">${p.description}</span>
								</div>
							`).join('')}
							${prot.length === 0 ? '<div class="empty">No active strategic protocols.</div>' : ''}
						</div>
					` : ''}
				</div>
			</div>
		`;

		this.shadowRoot.querySelector('#edit-trigger')?.addEventListener('click', () => { this.isEditing = true; this.render(); });
		this.shadowRoot.querySelector('#cancel-trigger')?.addEventListener('click', () => { this.isEditing = false; this.render(); });
		this.shadowRoot.querySelector('#save-trigger')?.addEventListener('click', () => this.savePersonality());

		this.shadowRoot.querySelector('#tab-per')?.addEventListener('click', () => {
			this.activeTab = 'personality';
			this.isEditing = false;
			this.render();
		});
		this.shadowRoot.querySelector('#tab-prot')?.addEventListener('click', () => {
			this.activeTab = 'protocols';
			this.isEditing = false;
			this.render();
		});
		// Keyboard navigation for tabs (ARIA tablist pattern)
		this.shadowRoot.querySelector('.tabs')?.addEventListener('keydown', (e: Event) => {
			const ke = e as KeyboardEvent;
			if (ke.key === 'ArrowRight' || ke.key === 'ArrowLeft') {
				ke.preventDefault();
				const newTab = this.activeTab === 'personality' ? 'protocols' : 'personality';
				this.activeTab = newTab;
				this.isEditing = false;
				this.render();
				const focusId = newTab === 'personality' ? '#tab-per' : '#tab-prot';
				(this.shadowRoot?.querySelector(focusId) as HTMLElement)?.focus();
			}
		});
	}
}

customElements.define('z-personality', ZPersonality);
