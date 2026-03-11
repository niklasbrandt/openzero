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
		// 3 s so activity transitions (idle → busy → idle) are caught in near-real-time
		this._refreshTimer = setInterval(() => this.fetchStatus(), 3_000);
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

		// Service health grid
		const services = [
			{
				name: 'Intelligence',
				status: (tiers.fast || {}).status === 'online' || d.status === 'online' ? 'online' : 'offline',
				detail: d.llm_model_short || 'Deep',
				tip: `Active Provider: ${d.llm_provider}. Model: ${d.llm_model_full}`,
				icon: 'brain'
			},
			{
				name: this.tr('memory_search', 'Memory'),
				status: (d.memory_points || 0) >= 0 ? 'online' : 'offline',
				detail: `${d.memory_points || 0} pts`,
				tip: this.tr('tip_memory', 'Qdrant vector database storing semantic long-term memory.'),
				icon: 'database'
			},
			{
				name: 'Database',
				status: d.db_size ? 'online' : 'warning',
				detail: d.db_size || '0 MB',
				tip: 'PostgreSQL storage used by projects, events, and core OS state.',
				icon: 'server'
			},
			{
				name: 'Cache / PubSub',
				status: d.redis_stats ? 'online' : 'warning',
				detail: d.redis_stats || 'offline',
				tip: 'Redis memory usage and key count for background tasks.',
				icon: 'zap'
			},
			{
				name: 'DNS / Adblock',
				status: d.dns_ok === true ? 'online' : d.dns_ok === false ? 'offline' : 'warning',
				detail: d.dns_detail || 'online',
				tip: this.tr('tip_dns', 'Pi-hole DNS resolver. Resolves open.zero for all Tailscale peers.'),
				icon: 'shield'
			},
			{
				name: 'Project Board',
				status: d.status === 'online' ? 'online' : 'offline',
				detail: 'Planka OSS',
				tip: 'Shared Kanban operating surface for task management.',
				icon: 'trello'
			},
		];

		const serviceGrid = services.map(s => `
			<div class="svc-item has-tip" role="listitem" data-tip="${s.tip}" tabindex="0" aria-label="${s.name}: ${s.status}">
				<div class="svc-main">
					<span class="svc-dot ${s.status}" aria-hidden="true"></span>
					<span class="sr-only">${s.status}</span>
					<span class="svc-name">${s.name}</span>
				</div>
				<span class="svc-detail">${s.detail}</span>
			</div>
		`).join('');

		// Stack summary - adding more detailed stats
		const stackItems = [
			{ label: 'Uptime', value: d.uptime_human || '?', tip: 'Time since last system reboot.' },
			{ label: 'Vector Vault', value: 'Qdrant', tip: 'Semantic memory storage engine.' },
			{ label: 'Realtime Queue', value: 'Redis', tip: 'Asynchronous task queue handler.' },
			{ label: 'Network', value: 'Traefik', tip: 'Reverse proxy and request router.' },
		];

		const stackHtml = stackItems.map(s => `
			<div class="stack-item has-tip" data-tip="${s.tip}" tabindex="0" aria-label="${s.label}: ${s.value}">
				<span class="stack-label">${s.label}</span>
				<span class="stack-value">${s.value}</span>
			</div>
		`).join('');

		// 3-Tier summary
		const intelHtml = `
			<div class="intel-stats">
				<div class="intel-stat">
					<span class="intel-label">Fast</span>
					<span class="intel-value">0.6B / ${(tiers.fast || {}).threads || 7}T</span>
				</div>
				<div class="intel-stat">
					<span class="intel-label">Deep</span>
					<span class="intel-value">8B-Q4 / ${(tiers.deep || {}).threads || 7}T</span>
				</div>
			</div>
		`;

		el.innerHTML = `
			<div class="svc-grid" role="list" aria-label="${this.tr('aria_service_status', 'Service status overview')}">${serviceGrid}</div>
			<div class="stack-section">
				<span class="section-label">${this.tr('stack', 'Stack')}</span>
				<div class="stack-grid">${stackHtml}</div>
				${intelHtml}
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
					flex-direction: column;
					align-items: flex-start;
					gap: 0.15rem;
					padding: 0.5rem 0.65rem;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.06));
					border-radius: 0.4rem;
					cursor: help;
					min-height: 52px;
				}
				.svc-main {
					display: flex;
					align-items: center;
					gap: 0.4rem;
					width: 100%;
				}
				.svc-dot {
					width: 10px;
					height: 10px;
					border-radius: 50%;
					flex-shrink: 0;
					transition: background 0.3s, box-shadow 0.3s;
				}
				.svc-dot.online { 
					background: var(--accent-primary, hsla(173, 80%, 40%, 1)); 
					box-shadow: 0 0 10px var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.35)); 
				}
				.svc-dot.offline { 
					background: var(--status-danger, hsla(0, 84%, 60%, 1)); 
					box-shadow: 0 0 8px var(--surface-danger-subtle, hsla(0, 84%, 60%, 0.25)); 
				}
				.svc-dot.warning { 
					background: var(--status-warning, hsla(45, 93%, 47%, 1)); 
					box-shadow: 0 0 8px var(--surface-warning-subtle, hsla(45, 93%, 47%, 0.25)); 
				}
				.svc-name {
					font-size: 0.7rem;
					font-weight: 600;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.8));
					white-space: nowrap;
					overflow: hidden;
					text-overflow: ellipsis;
				}
				.svc-detail {
					font-size: 0.62rem;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.5));
					font-family: var(--font-mono, 'Fira Code', monospace);
					white-space: nowrap;
					overflow: hidden;
					text-overflow: ellipsis;
					width: 100%;
					padding-left: 1.15rem; /* align with name text, past dot */
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
					margin-bottom: 1.25rem;
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

				/* ── Intelligence Stats Footer ── */
				.intel-stats {
					display: flex;
					justify-content: space-between;
					padding-top: 0.75rem;
					border-top: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.04));
					gap: 0.5rem;
				}
				.intel-stat {
					display: flex;
					flex-direction: column;
					gap: 0.1rem;
				}
				.intel-label {
					font-size: 0.55rem;
					text-transform: uppercase;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.3));
					font-weight: 700;
				}
				.intel-value {
					font-size: 0.7rem;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.5));
					font-weight: 500;
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
