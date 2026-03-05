import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { initGoo } from '../services/gooStyles';

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

		// If a theme preset was selected, sync the individual color fields so
		// initTheme() on next page load picks up the correct palette.
		const themeSelect = shadow.querySelector<HTMLSelectElement>('.theme-selector');
		if (themeSelect) {
			const selectedOpt = themeSelect.options[themeSelect.selectedIndex];
			const colorsRaw = selectedOpt?.getAttribute('data-colors');
			if (colorsRaw) {
				try {
					const colors = JSON.parse(colorsRaw);
					payload.color_primary = colors.primary;
					payload.color_secondary = colors.secondary;
					payload.color_tertiary = colors.tertiary;
				} catch { /* not a theme select, ignore */ }
			}
		}

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
				.tab { 
					padding: 0.5rem 0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; 
					color: rgba(255,255,255,0.4); cursor: pointer; border-bottom: 2px solid transparent;
					transition: all 0.2s;
				}
				.tab.active { color: var(--accent-primary, hsla(173, 80%, 40%, 1)); border-color: var(--accent-primary, hsla(173, 80%, 40%, 1)); }
				.tab:focus-visible { outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); outline-offset: 2px; border-radius: 2px 2px 0 0; }
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

				select.theme-selector {
					background: var(--surface-card-subtle, hsla(0,0%,0%,0.3));
					border: 1px solid var(--border-subtle, hsla(0,0%,100%,0.1));
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					padding: 10px 12px;
					border-radius: 0.5rem;
					width: 100%;
					box-sizing: border-box;
					font-family: inherit;
					font-size: 0.9rem;
					cursor: pointer;
					appearance: auto;
					min-height: 44px;
				}
				select.theme-selector:focus-visible { outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); outline-offset: 2px; }
				.theme-swatch {
					display: flex;
					gap: 6px;
					margin-top: 12px;
					align-items: center;
					padding-bottom: 8px;
				}
				.swatch-dot {
					width: 24px;
					height: 24px;
					border-radius: 50%;
					border: 1px solid var(--border-subtle, hsla(0,0%,100%,0.15));
					flex-shrink: 0;
					transition: transform 0.2s ease;
				}
				.swatch-dot:hover { transform: scale(1.1); }
				.swatch-label {
					font-size: 0.7rem;
					color: var(--text-muted, hsla(0,0%,100%,0.4));
					margin-left: 4px;
				}

				.actions { display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.25rem; }


				.prot-list { display: flex; flex-direction: column; gap: 0.75rem; margin-top: 0.5rem; }
				.prot-item { 
					background: var(--surface-card, hsla(0,0%,100%,0.03)); padding: 0.75rem 1rem; border-radius: 0.75rem;
					border-left: 3px solid var(--accent-secondary, hsla(216, 100%, 50%, 1)); animation: slideIn 0.3s ease-out backwards;
				}
				.prot-name { font-size: 0.85rem; font-weight: 700; letter-spacing: 0.02em; display: block; margin-bottom: 0.25rem; }
				.prot-desc { font-size: 0.8rem; color: var(--text-muted, hsla(0,0%,100%,0.5)); line-height: 1.5; }

				@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
				@keyframes slideIn { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }
				
				@media (prefers-reduced-motion: reduce) {
					.tab, .edit-btn, .prot-item, .swatch-dot { transition: none !important; animation: none !important; }
				}
				@media (forced-colors: active) {
					.tab.active { border-color: Highlight; color: Highlight; }
					.prot-item { border-left-color: Highlight; border: 1px solid CanvasText; }
					input[type="range"] { accent-color: Highlight; }
					.swatch-dot { border-color: CanvasText; }
				}
			</style>

			<div class="card">
				<div class="header">
					<h2>
						<div class="h-icon" aria-hidden="true">${agentInitial}</div>
						${this.isEditing ? this.tr('agent_config', 'Config') : (this.activeTab === 'personality' ? this.tr('agent_personality', 'Personality') : this.tr('agent_protocols', 'Protocols'))}
					</h2>
					${!this.isEditing && !this.isLoading && this.activeTab === 'personality' ? `<button class="edit-btn" id="edit-trigger" aria-label="${this.tr('refine', 'Refine')} — ${this.tr('aria_edit_personality', 'Edit agent personality settings')}">${this.tr('refine', 'Refine')}</button>` : ''}
				</div>

				${!this.isEditing ? `
					<div class="tabs" role="tablist" aria-label="${this.tr('aria_personality_views', 'Personality views')}">
						<div class="tab ${this.activeTab === 'personality' ? 'active' : ''}" id="tab-per" role="tab" aria-selected="${this.activeTab === 'personality'}" tabindex="${this.activeTab === 'personality' ? '0' : '-1'}">${this.tr('tab_identity', 'Identity')}</div>
						<div class="tab ${this.activeTab === 'protocols' ? 'active' : ''}" id="tab-prot" role="tab" aria-selected="${this.activeTab === 'protocols'}" tabindex="${this.activeTab === 'protocols' ? '0' : '-1'}">${this.tr('tab_protocols', 'Protocols')}</div>
					</div>
				` : ''}

				<div class="content" role="tabpanel" id="tabpanel-main" aria-labelledby="${this.activeTab === 'personality' ? 'tab-per' : 'tab-prot'}">
					${this.isLoading ? `<div class="empty-state">${this.tr('aligning', 'Aligning neural paths...')}</div>` : ''}
					
					${!this.isLoading && this.isEditing ? `
						<div class="form">
							${per.questions.filter((q: any) => q.id !== 'agent_name').map((q: any) => `
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
							` : q.type === 'select' ? (() => {
				const currentOpt = q.options.find((o: any) => o.value === per[q.id]) || q.options[0];
				const c = currentOpt?.colors || {};
				return `
									<select id="input-${q.id}" class="theme-selector" aria-label="${q.label}">
										${q.options.map((opt: any) => `
											<option value="${opt.value}" ${per[q.id] === opt.value ? 'selected' : ''} data-colors='${JSON.stringify(opt.colors)}'>${this.tr('theme_' + opt.value, opt.label)}</option>
										`).join('')}
									</select>
									<div class="theme-swatch" id="swatch-${q.id}" aria-hidden="true">
										<div class="swatch-dot" style="background: ${c.primary || 'hsla(173, 80%, 40%, 1)'}"></div>
										<div class="swatch-dot" style="background: ${c.secondary || 'hsla(216, 100%, 50%, 1)'}"></div>
										<div class="swatch-dot" style="background: ${c.tertiary || 'hsla(239, 84%, 67%, 1)'}"></div>
										<span class="swatch-label">${currentOpt?.label || ''}</span>
									</div>
								`;
			})() : q.type === 'color' ? `
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
					` : !this.isLoading && this.activeTab === 'personality' ? `
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

					${!this.isLoading && !this.isEditing && this.activeTab === 'protocols' ? `
						<div class="prot-explanation" style="font-size: 0.75rem; color: rgba(255,255,255,0.4); margin-bottom: 1rem; line-height: 1.4; padding: 0.5rem; background: rgba(0,102,255,0.05); border-radius: 4px; border-left: 2px solid hsla(216, 100%, 50%, 1);">
							${this.tr('prot_explanation', `Operational Protocols are the agent's internal "Action Tags". They define the specific strategic actions ${per?.agent_name || 'Z'} can perform across integrated services. These are core system capabilities.`)}
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
							${prot.length === 0 ? `<div class="empty-state">${this.tr('no_protocols', 'No active strategic protocols.')}</div>` : ''}
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

		// ── Live theme preview ──
		// When the user picks a theme from the select, immediately apply the
		// palette to the document root so they can see the preview before saving.
		const themeSelector = this.shadowRoot.querySelector<HTMLSelectElement>('.theme-selector');
		if (themeSelector) {
			themeSelector.addEventListener('change', () => {
				const selectedOpt = themeSelector.options[themeSelector.selectedIndex];
				const colorsRaw = selectedOpt.getAttribute('data-colors');
				if (!colorsRaw) return;
				try {
					const colors = JSON.parse(colorsRaw);
					const hexToRgb = (hex: string) => {
						const h = hex.replace('#', '');
						return `${parseInt(h.slice(0, 2), 16)}, ${parseInt(h.slice(2, 4), 16)}, ${parseInt(h.slice(4, 6), 16)}`;
					};
					const root = document.documentElement;
					root.style.setProperty('--accent-color', colors.primary);
					root.style.setProperty('--accent-color-rgb', hexToRgb(colors.primary));
					root.style.setProperty('--accent-secondary', colors.secondary);
					root.style.setProperty('--accent-tertiary', colors.tertiary);
					// Update the swatch dots in real time
					const swatchId = 'swatch-' + themeSelector.id.replace('input-', '');
					const swatchEl = this.shadowRoot!.getElementById(swatchId);
					if (swatchEl) {
						const dots = swatchEl.querySelectorAll<HTMLElement>('.swatch-dot');
						if (dots[0]) dots[0].style.background = colors.primary;
						if (dots[1]) dots[1].style.background = colors.secondary;
						if (dots[2]) dots[2].style.background = colors.tertiary;
						const label = swatchEl.querySelector<HTMLElement>('.swatch-label');
						if (label) label.textContent = selectedOpt.textContent || '';
					}
				} catch { /* ignore JSON parse errors */ }
			});
		}
	}
}

customElements.define('z-personality', ZPersonality);
