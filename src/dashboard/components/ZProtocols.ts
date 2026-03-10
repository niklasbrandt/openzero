import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { LIST_ITEM_STYLES } from '../services/listItemStyles';

export class ZProtocols extends HTMLElement {
	private protocols: any[] = [];
	private commands: any[] = [];
	private isLoading = true;
	private t: Record<string, string> = {};
	private openSections: Set<string> = new Set(['commands', 'tools']);

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
	}

	async fetchData() {
		this.isLoading = true;
		this.render();
		try {
			const protRes = await fetch('/api/dashboard/protocols');
			if (protRes.ok) {
				const data = await protRes.json();
				this.protocols = data.tools || [];
				this.commands = data.commands || [];
			}
		} catch (e) {
			console.error('Failed to fetch protocols data', e);
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

	render() {
		if (!this.shadowRoot) return;

		const prot = this.protocols;
		const cmd = this.commands;

		this.shadowRoot.innerHTML = `
			<style>
				${BUTTON_STYLES}
				${ACCESSIBILITY_STYLES}
				${SECTION_HEADER_STYLES}
				${SCROLLBAR_STYLES}
				${EMPTY_STATE_STYLES}
				${LIST_ITEM_STYLES}

				:host { display: block; height: 100%; font-family: 'Inter', system-ui, sans-serif; }
				.card { height: 100%; display: flex; flex-direction: column; gap: 1rem; color: var(--text-primary, hsla(0, 0%, 100%, 1)); }
				
				.header { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; }
				
				.content { flex: 1; overflow-y: auto; padding-right: 4px; }

				.accordion-section {
					margin-bottom: 0.5rem;
					border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
					border-radius: 0.75rem;
					overflow: hidden;
					background: rgba(255, 255, 255, 0.01);
					transition: background 0.3s ease;
				}

				.accordion-header {
					width: 100%;
					display: flex;
					align-items: center;
					justify-content: space-between;
					padding: 0.75rem 1rem;
					background: none;
					border: none;
					color: var(--text-primary);
					font-size: 0.85rem;
					font-weight: 600;
					text-transform: uppercase;
					letter-spacing: 0.05em;
					cursor: pointer;
					text-align: left;
				}

				.accordion-header:hover {
					background: rgba(255, 255, 255, 0.03);
				}

				.accordion-icon {
					transition: transform 0.3s ease;
					color: var(--text-muted);
				}

				.accordion-section.open .accordion-icon {
					transform: rotate(180deg);
				}

				.accordion-content {
					max-height: 0;
					overflow: hidden;
					transition: max-height 0.3s ease-out, padding 0.3s ease;
					opacity: 0;
				}

				.accordion-section.open .accordion-content {
					max-height: 1000px;
					opacity: 1;
					padding: 0 0.75rem 0.75rem 0.75rem;
				}

				.prot-list { display: flex; flex-direction: column; gap: 0.5rem; }
				
				.prot-item { 
					padding: 0.6rem 0.75rem;
					border-left: 2px solid var(--accent-secondary, hsla(216, 100%, 50%, 1));
					animation: slideIn 0.3s ease-out backwards;
					background: rgba(255, 255, 255, 0.02);
				}
				
				.cmd-item { border-left-color: var(--accent-tertiary, hsla(280, 80%, 50%, 1)); }

				.prot-name { 
					font-size: 0.8rem; 
					font-weight: 700; 
					letter-spacing: 0.02em; 
					display: flex; 
					align-items: center; 
					gap: 0.5rem; 
					color: var(--accent-color, #14b8a6);
					margin-bottom: 0.15rem;
				}
				
				.prot-desc { font-size: 0.75rem; color: var(--text-muted, hsla(0,0%,100%,0.6)); line-height: 1.4; }

				.prot-explanation {
					font-size: 0.75rem; 
					color: rgba(255,255,255,0.4); 
					margin-bottom: 0.75rem; 
					line-height: 1.4; 
					padding: 0.6rem 0.75rem; 
					background: rgba(var(--accent-primary-rgb), 0.05); 
					border-radius: 8px; 
					border-left: 3px solid var(--accent-color, #14b8a6);
				}

				@keyframes slideIn { from { opacity: 0; transform: translateX(-5px); } to { opacity: 1; transform: translateX(0); } }
				
				@media (prefers-reduced-motion: reduce) {
					.accordion-content, .accordion-icon, .prot-item { transition: none !important; animation: none !important; }
				}
			</style>

			<div class="card">
				<div class="header">
					<h2>
						<div class="h-icon" aria-hidden="true">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
							</svg>
						</div>
						${this.tr('agent_protocols', 'Protocols & Commands')}
					</h2>
				</div>

				<div class="content">
					${this.isLoading ? `<div class="empty-state">${this.tr('loading', 'Loading protocols...')}</div>` : `
						
						<div class="prot-explanation">
							${this.tr('prot_explanation', `Operational Protocols are the agent's internal capabilities and commands. They define specific strategic actions the agent can perform across integrated services.`)}
						</div>

						<!-- System Commands Accordion -->
						<div class="accordion-section ${this.openSections.has('commands') ? 'open' : ''}">
							<button class="accordion-header" id="btn-toggle-commands">
								<span>System Commands</span>
								<svg class="accordion-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
									<polyline points="6 9 12 15 18 9"></polyline>
								</svg>
							</button>
							<div class="accordion-content">
								<div class="prot-list" role="list">
									${cmd.map((c: any, i: number) => `
										<div class="prot-item cmd-item" role="listitem" style="animation-delay: ${i * 0.03}s">
											<span class="prot-name">
												${this.getCommandIcon(c.name)}
												${c.name}
											</span>
											<span class="prot-desc">${c.description}</span>
										</div>
									`).join('')}
								</div>
							</div>
						</div>

						<!-- Strategic Tools Accordion -->
						<div class="accordion-section ${this.openSections.has('tools') ? 'open' : ''}">
							<button class="accordion-header" id="btn-toggle-tools">
								<span>Strategic Tools</span>
								<svg class="accordion-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
									<polyline points="6 9 12 15 18 9"></polyline>
								</svg>
							</button>
							<div class="accordion-content">
								<div class="prot-list" role="list">
									${prot.map((p: any, i: number) => `
										<div class="prot-item" role="listitem" style="animation-delay: ${i * 0.05}s">
											<span class="prot-name">
												<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
												${p.name.replace(/_/g, ' ')}
											</span>
											<span class="prot-desc">${p.description}</span>
										</div>
									`).join('')}
									${prot.length === 0 ? `<div class="empty-state" style="padding: 1rem 0">${this.tr('no_protocols', 'No active strategic protocols.')}</div>` : ''}
								</div>
							</div>
						</div>
					`}
				</div>
			</div>
		`;

		this.setupEventListeners();
	}

	private setupEventListeners() {
		const btnCommands = this.shadowRoot?.querySelector('#btn-toggle-commands');
		const btnTools = this.shadowRoot?.querySelector('#btn-toggle-tools');

		if (btnCommands) {
			btnCommands.addEventListener('click', () => this.toggleSection('commands'));
		}
		if (btnTools) {
			btnTools.addEventListener('click', () => this.toggleSection('tools'));
		}
	}

	private getCommandIcon(name: string): string {
		const icons: Record<string, string> = {
			'/day': '<path d="M12 2v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="M20 12h2"/><path d="m19.07 4.93-1.41 1.41"/><path d="M15.89 16.75 12 14.81 8.11 16.75l.74-4.33-3.15-3.07 4.35-.63L12 4.79l1.95 3.93 4.35.63-3.15 3.07.74 4.33Z"/>',
			'/week': '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
			'/month': '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/><path d="M8 18h.01"/><path d="M12 18h.01"/><path d="M16 18h.01"/>',
			'/quarter': '<path d="M12 2v20"/><path d="M2 12h20"/><path d="M12 12 2.1 2.1"/><path d="m12 12 9.9 9.9"/>',
			'/year': '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="M7 14h.01"/><path d="M12 14h.01"/><path d="M17 14h.01"/><path d="M7 18h.01"/><path d="M12 18h.01"/><path d="M17 18h.01"/>',
			'/search': '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
			'/memories': '<path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 15a5 5 0 1 1 5-5 5 5 0 0 1-5 5z"/>',
			'/add': '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
			'/unlearn': '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
			'/tree': '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
			'/think': '<path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.04-2.44 2.5 2.5 0 0 1-2.04-2.44 2.5 2.5 0 0 1 1.96-2.44V4.5a2.5 2.5 0 0 1 2.5-2.5z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.04-2.44 2.5 2.5 0 0 0 2.04-2.44 2.5 2.5 0 0 0-1.96-2.44V4.5A2.5 2.5 0 0 0 14.5 2z"/>',
			'/remind': '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
			'/custom': '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M12 7v5l4 2"/>',
			'/purge': '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
			'/personal': '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
			'/agent': '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
			'/status': '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
			'/protocols': '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
		};

		const d = icons[name] || icons[name.split(' ')[0]] || '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>';
		return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${d}</svg>`;
	}

}


customElements.define('z-protocols', ZProtocols);

