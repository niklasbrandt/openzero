import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { GLASS_TOOLTIP_STYLES } from '../services/glassTooltipStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { GOO_STYLES, initGoo } from '../services/gooStyles';

export class SoftwareStatus extends HTMLElement {
	private data: any = null;
	private t: Record<string, string> = {};
	private _refreshTimer: ReturnType<typeof setInterval> | null = null;
	private _observer: IntersectionObserver | null = null;
	private _visible = false;
	private _onVisChange = () => this._handleVisibilityChange();

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.loadTranslations().then(() => {
			this.render();
			this.fetchStatus();
		});
		this._observer = new IntersectionObserver(
			([entry]) => {
				this._visible = entry.isIntersecting;
				if (entry.isIntersecting && !document.hidden) {
					this._startPolling();
				} else {
					this._stopPolling();
				}
			},
			{ threshold: 0 }
		);
		this._observer.observe(this);
		document.addEventListener('visibilitychange', this._onVisChange);
		initGoo(this);
		window.addEventListener('goo-changed', () => initGoo(this));
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => {
				this.render();
				this.fetchStatus();
			});
		});
	}

	disconnectedCallback() {
		this._stopPolling();
		if (this._observer) {
			this._observer.disconnect();
			this._observer = null;
		}
		document.removeEventListener('visibilitychange', this._onVisChange);
	}

	private _handleVisibilityChange() {
		if (document.hidden) {
			this._stopPolling();
		} else if (this._visible) {
			this._startPolling();
		}
	}

	private _startPolling() {
		if (this._refreshTimer) return;
		this._refreshTimer = setInterval(() => this.fetchStatus(), 10_000);
	}

	private _stopPolling() {
		if (this._refreshTimer) {
			clearInterval(this._refreshTimer);
			this._refreshTimer = null;
		}
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

	async fetchStatus() {
		try {
			const [sysRes, infoRes, llmRes] = await Promise.all([
				fetch('/api/dashboard/system'),
				fetch('/api/dashboard/server-info'),
				fetch('/api/dashboard/llm-config'),
			]);
			const sys = sysRes.ok ? await sysRes.json() : {};
			const info = infoRes.ok ? await infoRes.json() : {};
			const llmConfig = llmRes.ok ? await llmRes.json() : {};
			this.data = { ...sys, ...info, llm_config: llmConfig };
			this.updatePanel();
		} catch (e) {
			console.error('Failed to fetch software status:', e);
			const el = this.shadowRoot?.querySelector('#sw-panel');
			if (el) el.innerHTML = '<div class="empty-state">Could not reach backend.</div>';
		}
	}

	updatePanel() {
		const el = this.shadowRoot?.querySelector('#sw-panel');
		if (!el || !this.data) return;
		const d = this.data;
		const tiers = d.tiers || {};

		// LLM tier config (fetch model names)
		const llmCfg = d.llm_config || {};
		const tierList: any[] = llmCfg.tiers || [];
		const modelFor = (tier: string) => {
			const t = tierList.find((x: any) => x.tier === tier);
			return t ? t.model : '?';
		};

		// Service health grid
		const services = [
			{
				name: 'Instant',
				model: modelFor('instant'),
				status: (tiers.instant || {}).status === 'ok' || (tiers.instant || {}).status === 'online' || (tiers.instant || {}).status === 'no slot available' ? 'online' : 'offline',
				detail: d.llm_provider === 'local' ? `${(tiers.instant || {}).threads || '?'}T` : 'cloud',
				tip: this.tr('tip_instant', 'Fast, trivial queries. Greetings, confirmations, memory distillation.'),
				isLlm: true,
			},
			{
				name: 'Standard',
				model: modelFor('standard'),
				status: (tiers.standard || {}).status === 'ok' || (tiers.standard || {}).status === 'online' || (tiers.standard || {}).status === 'no slot available' ? 'online' : 'offline',
				detail: d.llm_provider === 'local' ? `${(tiers.standard || {}).threads || '?'}T` : 'cloud',
				tip: this.tr('tip_standard', 'Normal conversation, moderate reasoning, tool-intent. The workhorse tier.'),
				isLlm: true,
			},
			{
				name: 'Deep',
				model: modelFor('deep'),
				status: (tiers.deep || {}).status === 'ok' || (tiers.deep || {}).status === 'online' || (tiers.deep || {}).status === 'no slot available' ? 'online' : 'offline',
				detail: d.llm_provider === 'local' ? `${(tiers.deep || {}).threads || '?'}T` : 'cloud',
				tip: this.tr('tip_deep', 'Complex reasoning, briefings, planning, strategic analysis.'),
				isLlm: true,
			},
			{
				name: this.tr('backend', 'Backend'),
				model: '',
				status: d.status === 'online' ? 'online' : 'offline',
				detail: `Provider: ${d.llm_provider || 'local'}`,
				tip: this.tr('tip_backend', 'FastAPI backend serving dashboard, Telegram bot, scheduled tasks, and LLM routing.'),
				isLlm: false,
			},
			{
				name: this.tr('memory_search', 'Memory'),
				model: '',
				status: (d.memory_points || 0) >= 0 ? 'online' : 'offline',
				detail: `${d.memory_points || 0} pts`,
				tip: this.tr('tip_memory', 'Qdrant vector database storing semantic long-term memory.'),
				isLlm: false,
			},
			{
				name: this.tr('tab_identity', 'Identity'),
				model: '',
				status: d.identity_active ? 'online' : 'warning',
				detail: d.identity_active ? this.tr('status_active', 'Active') : this.tr('not_set', 'Not set'),
				tip: this.tr('tip_identity_svc', 'Subject Zero identity profile. Required for personalized responses.'),
				isLlm: false,
			},
			{
				name: 'DNS',
				model: '',
				status: d.dns_ok === true ? 'online' : d.dns_ok === false ? 'offline' : 'warning',
				detail: d.dns_ok ? 'online' : 'offline',
				tip: this.tr('tip_dns', 'Pi-hole DNS resolver. Resolves open.zero for all Tailscale peers. Offline = mobile dashboard unreachable.'),
				isLlm: false,
			},
		];

		const serviceGrid = services.map(s => s.isLlm ? `
			<div class="svc-item svc-llm has-tip" role="listitem" data-tip="${s.tip}" tabindex="0" aria-label="${s.name}: ${s.status}">
				<div class="svc-row">
					<span class="svc-dot ${s.status}" aria-hidden="true"></span>
					<span class="sr-only">${s.status}</span>
					<span class="svc-name">${s.name}</span>
					<span class="svc-detail">${s.detail}</span>
				</div>
				<span class="svc-model">${s.model}</span>
			</div>
		` : `
			<div class="svc-item has-tip" role="listitem" data-tip="${s.tip}" tabindex="0" aria-label="${s.name}: ${s.status}">
				<span class="svc-dot ${s.status}" aria-hidden="true"></span>
				<span class="sr-only">${s.status}</span>
				<span class="svc-name">${s.name}</span>
				<span class="svc-detail">${s.detail}</span>
			</div>
		`).join('');

		// Stack summary
		const stackItems = [
			{ label: this.tr('llm_engine', 'LLM Engine'), value: 'llama.cpp', tip: this.tr('tip_llm_engine', 'Local inference engine running GGUF-quantized models via llama-server.') },
			{ label: this.tr('model_active', 'Model Active'), value: d.llm_model || 'unknown', tip: this.tr('tip_model_active', 'The model used for the most recent LLM request.') },
			{ label: this.tr('memory_db', 'Memory DB'), value: 'Qdrant', tip: this.tr('tip_memory_db', 'Vector similarity search for semantic long-term memory.') },
			{ label: this.tr('task_board', 'Task Board'), value: 'Planka', tip: this.tr('tip_task_board', 'Kanban project management board for task tracking.') },
		];

		const stackHtml = stackItems.map(s => `
			<div class="stack-item has-tip" data-tip="${s.tip}" tabindex="0" aria-label="${s.label}: ${s.value}">
				<span class="stack-label">${s.label}</span>
				<span class="stack-value">${s.value}</span>
			</div>
		`).join('');

		el.innerHTML = `
			<div class="svc-grid" role="list" aria-label="${this.tr('aria_service_status', 'Service status overview')}">${serviceGrid}</div>
			<div class="stack-section">
				<span class="section-label">${this.tr('stack', 'Stack')}</span>
				<div class="stack-grid">${stackHtml}</div>
			</div>
		`;
		this.injectTooltips();
	}

	/** Convert data-tip attributes into real DOM elements so backdrop-filter works */
	private injectTooltips() {
		if (!this.shadowRoot) return;
		this.shadowRoot.querySelectorAll('.has-tip[data-tip]').forEach(el => {
			const text = el.getAttribute('data-tip');
			if (!text || el.querySelector('.glass-tooltip')) return;
			const tip = document.createElement('span');
			tip.className = 'glass-tooltip';
			tip.setAttribute('aria-hidden', 'true');
			tip.textContent = text;
			el.appendChild(tip);
		});
	}

	render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
			<style>
				:host { display: block; }
				${ACCESSIBILITY_STYLES}
				${SECTION_HEADER_STYLES}
				${GLASS_TOOLTIP_STYLES}
				${EMPTY_STATE_STYLES}
				${GOO_STYLES}

				/* ── Service Grid ── */
				.svc-grid {
					display: grid;
					grid-template-columns: repeat(3, 1fr);
					gap: 0.5rem;
					margin-bottom: 1.25rem;
				}
				.svc-item {
					display: flex;
					align-items: center;
					gap: 0.4rem;
					padding: 0.5rem 0.65rem;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.06));
					border-radius: 0.4rem;
					cursor: help;
					min-height: 44px; /* WCAG touch target */
				}
				.svc-llm {
					flex-direction: column;
					align-items: stretch;
					gap: 0.2rem;
					padding: 0.55rem 0.65rem;
					min-height: 56px;
				}
				.svc-llm .svc-row {
					display: flex;
					align-items: center;
					gap: 0.4rem;
				}
				.svc-model {
					font-size: 0.82rem;
					font-weight: 600;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.85));
					font-family: var(--font-mono, 'Fira Code', monospace);
					letter-spacing: -0.01em;
				}
				.svc-dot {
					width: 8px;
					height: 8px;
					border-radius: 50%;
					flex-shrink: 0;
				}
				.svc-dot.online { 
					background: var(--accent-primary, hsla(173, 80%, 40%, 1)); 
					box-shadow: 0 0 8px var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.2)); 
				}
				.svc-dot.offline { 
					background: var(--status-danger, hsla(0, 84%, 60%, 1)); 
					box-shadow: 0 0 8px var(--surface-danger-subtle, hsla(0, 84%, 60%, 0.2)); 
				}
				.svc-dot.warning { 
					background: var(--status-warning, hsla(45, 93%, 47%, 1)); 
					box-shadow: 0 0 8px var(--surface-warning-subtle, hsla(45, 93%, 47%, 0.2)); 
				}
				.svc-name {
					font-size: 0.7rem;
					font-weight: 600;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.8));
					white-space: nowrap;
				}
				.svc-detail {
					font-size: 0.65rem;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.7));
					font-family: var(--font-mono, 'Fira Code', monospace);
					margin-left: auto;
					white-space: nowrap;
				}

				/* ── Stack Section ── */
				.section-label {
					font-size: 0.65rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
					font-weight: 600;
					display: block;
					margin-bottom: 0.5rem;
				}
				.stack-grid {
					display: grid;
					grid-template-columns: repeat(2, 1fr);
					gap: 0.4rem;
				}
				.stack-item {
					display: flex;
					flex-direction: column;
					gap: 0.15rem;
					cursor: help;
					padding: 0.4rem 0.65rem;
					background: var(--surface-card-subtle, hsla(0, 0%, 100%, 0.015));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.04));
					border-radius: 0.3rem;
					min-height: 48px;
				}
				.stack-label {
					font-size: 0.6rem;
					text-transform: uppercase;
					letter-spacing: 0.08em;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.3));
					font-weight: 600;
				}
				.stack-value {
					font-size: 0.82rem;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.7));
					font-family: var(--font-mono, 'Fira Code', monospace);
				}

				.svc-item:focus-visible, .stack-item:focus-visible { 
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); 
					outline-offset: 2px;
				}
				@media (forced-colors: active) {
					.svc-dot.online { background: ButtonText; }
					.svc-dot.offline { background: LinkText; }
					.svc-dot.warning { background: ButtonText; border: 1px solid LinkText; }
					.svc-dot { box-shadow: none; }
				}
			</style>

			<h2>
				<span class="h-icon" aria-hidden="true">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
						<polyline points="16 18 22 12 16 6"></polyline>
						<polyline points="8 6 2 12 8 18"></polyline>
					</svg>
				</span>
				${this.tr('software', 'Software')}
			</h2>

			<div id="sw-panel" aria-live="polite" aria-label="${this.tr('aria_sw_status', 'Software status')}">
				<div class="empty-state">${this.tr('loading_sw', 'Loading services...')}</div>
			</div>
		`;
	}
}

customElements.define('software-status', SoftwareStatus);
