import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';

export class ZProtocols extends HTMLElement {
    private protocols: any[] = [];
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
    }

    async fetchData() {
        this.isLoading = true;
        this.render();
        try {
            const protRes = await fetch('/api/dashboard/protocols');
            if (protRes.ok) {
                const data = await protRes.json();
                this.protocols = data.tools || [];
            }
        } catch (e) {
            console.error('Failed to fetch protocols data', e);
        } finally {
            this.isLoading = false;
            this.render();
        }
    }

    render() {
        if (!this.shadowRoot) return;

        const prot = this.protocols;

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
				h2 .h-icon {
					font-weight: 800; font-size: 0.8rem;
				}

				.content { flex: 1; overflow-y: auto; padding-right: 4px; }

				.prot-list { display: flex; flex-direction: column; gap: 0.75rem; margin-top: 0.5rem; }
				.prot-item { 
					background: var(--surface-card, hsla(0,0%,100%,0.03)); padding: 0.75rem 1rem; border-radius: 0.75rem;
					border-left: 3px solid var(--accent-secondary, hsla(216, 100%, 50%, 1)); animation: slideIn 0.3s ease-out backwards;
				}
				.cmd-item { border-left-color: var(--accent-tertiary, hsla(280, 80%, 50%, 1)); }

				.prot-name { font-size: 0.85rem; font-weight: 700; letter-spacing: 0.02em; display: block; margin-bottom: 0.25rem; display: flex; align-items: center; gap: 0.5rem; }
				.prot-desc { font-size: 0.8rem; color: var(--text-muted, hsla(0,0%,100%,0.5)); line-height: 1.5; }

				@keyframes slideIn { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }
				
				@media (prefers-reduced-motion: reduce) {
					.prot-item { transition: none !important; animation: none !important; }
				}
				@media (forced-colors: active) {
					.prot-item { border-left-color: Highlight; border: 1px solid CanvasText; }
				}

				.section-title {
					font-size: 0.85rem;
					font-weight: 600;
					text-transform: uppercase;
					letter-spacing: 0.05em;
					color: var(--text-muted, hsla(0,0%,100%,0.5));
					margin-bottom: 0.5rem;
					margin-top: 1.5rem;
					display: flex; align-items: center; gap: 0.5rem;
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
						
						<div class="prot-explanation" style="font-size: 0.75rem; color: rgba(255,255,255,0.4); margin-bottom: 1rem; line-height: 1.4; padding: 0.5rem; background: rgba(0,102,255,0.05); border-radius: 4px; border-left: 2px solid var(--accent-secondary, hsla(216, 100%, 50%, 1));">
							${this.tr('prot_explanation', `Operational Protocols are the agent's internal capabilities and commands. They define specific strategic actions the agent can perform across integrated services.`)}
						</div>

						<div class="section-title">System Commands</div>
						<div class="prot-list" role="list">
							<div class="prot-item cmd-item" role="listitem" style="animation-delay: 0.05s">
								<span class="prot-name">
									<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m3 15 2 2 4-4"/></svg>
									/day
								</span>
								<span class="prot-desc">Triggers the morning briefing and daily agenda overview manually.</span>
							</div>
							<div class="prot-item cmd-item" role="listitem" style="animation-delay: 0.1s">
								<span class="prot-name">
									<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>
									/unlearn
								</span>
								<span class="prot-desc">Instructs the agent to forget or remove specific information from its active or semantic memory.</span>
							</div>
							<div class="prot-item cmd-item" role="listitem" style="animation-delay: 0.15s">
								<span class="prot-name">
									<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
									/save
								</span>
								<span class="prot-desc">Forces saving current state and context into long-term semantic memory explicitly.</span>
							</div>
						</div>

						<div class="section-title">Operational Protocols</div>
						<div class="prot-list" role="list">
							${prot.map((p: any, i: number) => `
								<div class="prot-item" role="listitem" style="animation-delay: ${(i + 3) * 0.05}s">
									<span class="prot-name">
										<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
										${p.name.replace(/_/g, ' ')}
									</span>
									<span class="prot-desc">${p.description}</span>
								</div>
							`).join('')}
							${prot.length === 0 ? `<div class="empty-state">${this.tr('no_protocols', 'No active strategic protocols.')}</div>` : ''}
						</div>
					`}
				</div>
			</div>
		`;
    }
}

customElements.define('z-protocols', ZProtocols);
