import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { GLASS_TOOLTIP_STYLES } from '../services/glassTooltipStyles';
import { STATUS_STYLES } from '../services/statusStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { GOO_STYLES, initGoo } from '../services/gooStyles';

export class HardwareMonitor extends HTMLElement {
	private cpuData: any = null;
	private serverData: any = null;
	private llmConfig: any = null;
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
			this.fetchAll();
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
				this.fetchAll();
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
		// 3 s to track LLM activity transitions in near-real-time
		this._refreshTimer = setInterval(() => this.fetchAll(), 3_000);
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

	async fetchAll() {
		try {
			const [cpuRes, serverRes, llmRes] = await Promise.all([
				fetch('/api/dashboard/benchmark/cpu'),
				fetch('/api/dashboard/server-info'),
				fetch('/api/dashboard/llm-config'),
			]);
			if (cpuRes.ok) this.cpuData = await cpuRes.json();
			if (serverRes.ok) this.serverData = await serverRes.json();
			if (llmRes.ok) this.llmConfig = await llmRes.json();
			this.updatePanel();
		} catch (e) {
			console.error('Failed to fetch hardware info:', e);
			const el = this.shadowRoot?.querySelector('#hw-panel');
			if (el) el.innerHTML = `<div class="empty-state">${this.tr('hw_error', 'Could not reach hardware probe. Is the backend running?')}</div>`;
		}
	}

	updatePanel() {
		const el = this.shadowRoot?.querySelector('#hw-panel');
		if (!el || !this.cpuData) return;
		const d = this.cpuData;
		const s = this.serverData || {};

		const simdBadges = [
			{ name: 'SSE4.2', active: d.sse4_2, tip: this.tr('tip_sse42', 'Baseline SIMD. Used by all modern llama.cpp builds for basic vectorized math.') },
			{ name: 'AVX2', active: d.avx2, tip: this.tr('tip_avx2', 'Advanced Vector Extensions 2. Doubles throughput for quantized matrix ops. Critical for good tok/s on CPU.') },
			{ name: 'AVX-512', active: d.avx512, tip: this.tr('tip_avx512', 'Widest SIMD. Up to 2x faster than AVX2 for large quantized models. Rare on consumer CPUs, common on EPYC/Xeon.') },
		];

		const badgesHtml = simdBadges.map(b =>
			`<span class="simd-badge ${b.active ? 'active' : 'inactive'} has-tip" data-tip="${b.tip}" tabindex="0" role="img" aria-label="${b.name}: ${b.active ? this.tr('simd_supported', 'Supported') : this.tr('simd_unavailable', 'Not available')}. ${b.tip}">${b.name}</span>`
		).join('');

		const simdScore = (d.avx512 ? 3 : d.avx2 ? 2 : d.sse4_2 ? 1 : 0);
		const coreScore = Math.min(d.cores_physical || 1, 8);
		const capabilityClass = simdScore >= 2 && coreScore >= 4 ? 'excellent' :
			simdScore >= 1 && coreScore >= 2 ? 'good' :
				'limited';
		const capabilityText = capabilityClass === 'excellent'
			? this.tr('excellent_hw', 'Well-suited for local LLM inference')
			: capabilityClass === 'good'
				? this.tr('good_hw', 'Adequate for small-to-medium models')
				: this.tr('limited_hw', 'Limited -- expect slow inference on larger models');

		// RAM section
		const ramPct = s.ram_used_pct || 0;
		const hasBreakdown = s.ram_apps_gb !== undefined && s.ram_bufcache_gb !== undefined;
		const appsPct = hasBreakdown ? Math.min(s.ram_apps_pct || 0, 100) : Math.min(ramPct, 100);
		const cachePct = hasBreakdown
			? Math.min((s.ram_bufcache_gb / Math.max(s.ram_total_gb, 0.1)) * 100, 100 - appsPct)
			: 0;
		const ramBarClass = ramPct > 90 ? 'critical' : ramPct > 75 ? 'warning' : 'healthy';
		const appsGb = hasBreakdown ? (s.ram_apps_gb as number).toFixed(1) : '';
		const cacheGb = hasBreakdown ? (s.ram_bufcache_gb as number).toFixed(1) : '';
		const freeGb = hasBreakdown
			? (s.ram_free_gb !== undefined ? (s.ram_free_gb as number) : (s.ram_available_gb as number)).toFixed(1)
			: '';
		const breakdownHtml = hasBreakdown ? `
			<div class="ram-legend" role="list">
				<span class="ram-legend-item ${ramBarClass}" role="listitem">
					<span class="ram-legend-swatch apps ${ramBarClass}" aria-hidden="true"></span>
					<span class="ram-legend-label has-tip" data-tip="${this.tr('tip_ram_apps', 'Memory actively used by processes and LLM models (mlock). Cannot be reclaimed without stopping services.')}">${appsGb} GB ${this.tr('ram_apps', 'apps')}</span>
				</span>
				<span class="ram-legend-item" role="listitem">
					<span class="ram-legend-swatch cache" aria-hidden="true"></span>
					<span class="ram-legend-label has-tip" data-tip="${this.tr('tip_ram_cache', 'Linux buffers and page cache. Automatically reclaimed by the kernel when apps need more memory.')}">${cacheGb} GB ${this.tr('ram_cache', 'cache')}</span>
				</span>
				<span class="ram-legend-item" role="listitem">
					<span class="ram-legend-swatch free" aria-hidden="true"></span>
					<span class="ram-legend-label has-tip" data-tip="${this.tr('tip_ram_free', 'Completely unallocated RAM.')}">${freeGb} GB ${this.tr('ram_free', 'free')}</span>
				</span>
			</div>
		` : '';
		const ramHtml = s.ram_total_gb ? `
			<div class="ram-section">
				<div class="ram-header">
					<span class="spec-label">${this.tr('ram', 'RAM')}</span>
					<span class="ram-values">${s.ram_total_gb} GB ${this.tr('total', 'total')}</span>
				</div>
				<div class="ram-bar-track" role="presentation" aria-label="${this.tr('ram_usage_label', 'RAM usage')}: ${ramPct}%">
					<div class="ram-seg ram-seg-apps ${ramBarClass}" role="progressbar" aria-valuenow="${appsPct}" aria-valuemin="0" aria-valuemax="100" aria-label="${this.tr('ram_apps', 'apps')}: ${appsPct}%" style="width: ${appsPct}%"></div>
					<div class="ram-seg ram-seg-cache has-tip" data-tip="${this.tr('tip_ram_cache', 'Linux buffers and page cache. Automatically reclaimed by the kernel when apps need more memory.')}" aria-hidden="true" style="width: ${cachePct}%"></div>
				</div>
				<span class="ram-pct ${ramBarClass}" aria-hidden="true">${ramPct}% ${this.tr('used', 'used')}</span>
				${breakdownHtml}
			</div>
		` : '';

		// Uptime
		const uptimeHtml = s.uptime_human ? `
			<div class="spec-item has-tip" data-tip="${this.tr('tip_uptime', 'How long the server has been running since last reboot.')}">
				<span class="spec-label">${this.tr('uptime', 'Uptime')}</span>
				<span class="spec-value">${s.uptime_human}</span>
			</div>
		` : '';



		// LLM Load section
		const tiers: any = (this.serverData || {}).tiers || {};
		const cfgTiers: any[] = (this.llmConfig || {}).tiers || [];
		const modelFor = (name: string) => {
			const t = cfgTiers.find((x: any) => x.tier === name);
			return t ? t.model : name;
		};
		const tierNames = ['instant', 'deep'];
		const anyTierData = tierNames.some(n => tiers[n]);

		const llmLoadHtml = anyTierData ? `
			<div class="llm-load-section">
				<div class="llm-load-header">
					<span class="spec-label">LLM Load</span>
				</div>
				<div class="llm-tiers">
					${tierNames.map(name => {
			const td = tiers[name] || {};
			const activity = td.activity || 'offline';
			const status = td.status || 'offline';
			const isOnline = status !== 'offline';
			const isBusy = activity === 'processing';
			const ctx = td.ctx_size ? `${td.ctx_size.toLocaleString()} ctx` : '';
			const threads = td.threads ? `${td.threads}T` : '';
			const model = modelFor(name);
			const pillClass = !isOnline ? 'offline' : isBusy ? 'busy' : 'idle';
			const pillText = !isOnline ? 'OFFLINE' : isBusy ? 'BUSY' : 'IDLE';
			const dotClass = !isOnline ? 'offline' : isBusy ? 'processing' : 'idle';
			return `
							<div class="llm-tier-row ${isBusy ? 'llm-tier-busy' : ''}">
								<span class="llm-tier-dot ${dotClass}"></span>
								<span class="llm-tier-name">${name.charAt(0).toUpperCase() + name.slice(1)}</span>
								<span class="llm-tier-model" title="${model}">${model}</span>
								<span class="llm-tier-meta">${[threads, ctx].filter(Boolean).join(' · ')}</span>
								<span class="llm-activity-pill ${pillClass}">${pillText}</span>
							</div>
						`;
		}).join('')}
				</div>
			</div>
		` : '';

		el.innerHTML = `
			<div class="cpu-model has-tip" data-tip="${this.tr('tip_cpu_model', 'CPU model string as reported by the kernel')}">${d.cpu_model}</div>
			<div class="cpu-specs">
				<div class="spec-item has-tip" data-tip="${this.tr('tip_cores', 'Physical cores run actual computations. Logical cores (hyperthreads) help with scheduling but add less throughput for LLM workloads.')}">
					<span class="spec-label">${this.tr('cores', 'Cores')}</span>
					<span class="spec-value">${d.cores_physical}P / ${d.cores_logical}L</span>
				</div>
				<div class="spec-item has-tip" data-tip="${this.tr('tip_arch', 'CPU instruction set architecture. x86_64 supports the widest range of SIMD extensions for llama.cpp.')}">
					<span class="spec-label">${this.tr('arch', 'Arch')}</span>
					<span class="spec-value">${d.architecture}</span>
				</div>
				${uptimeHtml || `
				<div class="spec-item has-tip" data-tip="${this.tr('tip_platform', 'Host operating system running the Docker containers.')}">
					<span class="spec-label">${this.tr('platform', 'Platform')}</span>
					<span class="spec-value">${d.platform}</span>
				</div>`}
			</div>
			${ramHtml}
			${llmLoadHtml}
			<div class="simd-row has-tip" data-tip="${this.tr('tip_simd', 'SIMD (Single Instruction, Multiple Data) extensions allow the CPU to process multiple values in parallel. Higher SIMD = faster LLM inference.')}">
				<span class="spec-label">${this.tr('simd', 'SIMD')}</span>
				<div class="simd-badges">${badgesHtml}</div>
			</div>
			<div class="capability-summary ${capabilityClass}" role="status" aria-label="${this.tr('aria_hw_capability', 'Hardware capability')}: ${capabilityText}">
				<span class="status-dot" aria-hidden="true"></span>
				<span class="capability-text">${capabilityText}</span>
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
				${STATUS_STYLES}
				${EMPTY_STATE_STYLES}
				${GOO_STYLES}

				/* ── Component: icon gradient override ── */
				.h-icon { background: linear-gradient(135deg, var(--accent-tertiary, hsla(239, 84%, 67%, 1)) 0%, var(--accent-color, hsla(173, 80%, 40%, 1)) 100%); }

				.cpu-model {
					font-size: 1rem;
					font-weight: 600;
				color: var(--text-primary, hsla(0, 0%, 100%, 1));
					margin-bottom: 1rem;
					line-height: 1.4;
					font-family: var(--font-mono, 'Fira Code', monospace);
					cursor: help;
				}

				.cpu-specs {
					display: grid;
					grid-template-columns: repeat(3, 1fr);
					gap: 0.75rem;
					margin-bottom: 1rem;
				}

				.spec-item {
					display: flex;
					flex-direction: column;
					gap: 0.2rem;
					cursor: help;
				}

				.spec-label {
					font-size: 0.65rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
					font-weight: 600;
				}

				.spec-value {
					font-size: 0.9rem;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.85));
					font-family: var(--font-mono, 'Fira Code', monospace);
				}

				.simd-row {
					display: flex;
					align-items: center;
					gap: 0.75rem;
					margin-bottom: 1rem;
					cursor: help;
					min-height: 44px;
				}

				.simd-badges {
					display: flex;
					gap: 0.4rem;
				}

				.simd-badge {
					font-size: 0.7rem;
					font-weight: 700;
					letter-spacing: 0.05em;
					padding: 0.2rem 0.6rem;
					border-radius: var(--radius-xs, 0.3rem);
					font-family: var(--font-mono, 'Fira Code', monospace);
					cursor: help;
					transition: transform var(--duration-fast, 0.15s), background var(--duration-fast), border var(--duration-fast);
					min-height: 28px;
					display: flex;
					align-items: center;
				}

				.simd-badge:hover, .simd-badge:focus-visible {
					transform: scale(1.08);
					outline: none;
				}

				.simd-badge.active {
					background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.15));
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					border: 1px solid var(--border-accent-subtle, hsla(173, 80%, 40%, 0.3));
				}

				.simd-badge.inactive {
					background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
					color: var(--text-muted, hsla(0, 0%, 100%, 0.2));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.06));
					text-decoration: line-through;
				}

				.capability-summary {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					padding: 0.6rem 0.8rem;
					border-radius: 0.5rem;
					font-size: 0.75rem;
					font-weight: 500;
					letter-spacing: 0.02em;
					min-height: 44px;
				}

				.capability-summary.excellent {
					background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.08));
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					border: 1px solid var(--border-accent-subtle, hsla(173, 80%, 40%, 0.15));
				}
				.capability-summary.excellent .status-dot { background: var(--accent-primary, hsla(173, 80%, 40%, 1)); }

				.capability-summary.good {
					background: var(--surface-warning-subtle, hsla(45, 93%, 47%, 0.08));
					color: var(--status-warning, hsla(45, 93%, 47%, 1));
					border: 1px solid var(--border-warning-subtle, hsla(45, 93%, 47%, 0.15));
				}
				.capability-summary.good .status-dot { background: var(--status-warning, hsla(45, 93%, 47%, 1)); }

				.capability-summary.limited {
					background: var(--surface-danger-subtle, hsla(0, 84%, 60%, 0.08));
					color: var(--status-danger, hsla(0, 84%, 60%, 1));
					border: 1px solid var(--border-danger-subtle, hsla(0, 84%, 60%, 0.15));
				}
				.capability-summary.limited .status-dot { background: var(--status-danger, hsla(0, 84%, 60%, 1)); }

				/* ── RAM Bar ── */
				.ram-section {
					margin-bottom: 1rem;
				}
				.ram-header {
					display: flex;
					justify-content: space-between;
					align-items: center;
					margin-bottom: 0.35rem;
				}
				.ram-values {
					font-size: 0.8rem;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.7));
					font-family: var(--font-mono, 'Fira Code', monospace);
				}
				.ram-bar-track {
					display: flex;
					height: 8px;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.05));
					border-radius: 4px;
					overflow: hidden;
				}
				.ram-seg {
					height: 100%;
					flex-shrink: 0;
					transition: width var(--duration-slow, 0.5s);
				}
				.ram-seg-apps.healthy { background: var(--accent-primary, hsla(173, 80%, 40%, 1)); }
				.ram-seg-apps.warning { background: var(--status-warning, hsla(45, 93%, 47%, 1)); }
				.ram-seg-apps.critical { background: var(--status-danger, hsla(0, 84%, 60%, 1)); }
				.ram-seg-cache { background: var(--accent-primary, hsla(173, 80%, 40%, 0.25)); }
				.ram-pct {
					font-size: 0.65rem;
					font-weight: 500;
					margin-top: 0.25rem;
					display: block;
				}
				.ram-pct.healthy { color: var(--accent-primary, hsla(173, 80%, 40%, 0.8)); }
				.ram-pct.warning { color: var(--status-warning, hsla(45, 93%, 47%, 0.8)); }
				.ram-pct.critical { color: var(--status-danger, hsla(0, 84%, 60%, 0.85)); }
				.ram-legend {
					display: flex;
					gap: 0.75rem;
					margin-top: 0.45rem;
					flex-wrap: wrap;
				}
				.ram-legend-item {
					display: flex;
					align-items: center;
					gap: 0.3rem;
				}
				.ram-legend-swatch {
					width: 8px;
					height: 8px;
					border-radius: 2px;
					flex-shrink: 0;
				}
				.ram-legend-swatch.apps.healthy { background: var(--accent-primary, hsla(173, 80%, 40%, 1)); }
				.ram-legend-swatch.apps.warning { background: var(--status-warning, hsla(45, 93%, 47%, 1)); }
				.ram-legend-swatch.apps.critical { background: var(--status-danger, hsla(0, 84%, 60%, 1)); }
				.ram-legend-swatch.cache { background: var(--accent-primary, hsla(173, 80%, 40%, 0.35)); }
				.ram-legend-swatch.free { background: var(--surface-card, hsla(0, 0%, 100%, 0.07)); border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.1)); }
				.ram-legend-label {
					font-size: 0.65rem;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.6));
					cursor: help;
				}

				.simd-badge:focus-visible { 
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); 
					outline-offset: 2px; 
				}

				/* ── LLM Load Section ── */
				.llm-load-section {
					margin-bottom: 1rem;
				}
				.llm-load-header {
					margin-bottom: 0.4rem;
				}
				.llm-tiers {
					display: flex;
					flex-direction: column;
					gap: 0.3rem;
				}
				.llm-tier-row {
					display: flex;
					align-items: center;
					gap: 0.45rem;
					padding: 0.35rem 0.55rem;
					border-radius: 0.35rem;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.06));
					transition: border-color 0.3s, background 0.3s, box-shadow 0.3s;
				}
				.llm-tier-busy {
					border-color: hsla(210, 100%, 62%, 0.4) !important;
					background: hsla(210, 100%, 62%, 0.05) !important;
					animation: hw-card-glow 2s ease-in-out infinite;
				}
				@keyframes hw-card-glow {
					0%, 100% { box-shadow: 0 0 0 0 hsla(210, 100%, 62%, 0); }
					50% { box-shadow: 0 0 10px 2px hsla(210, 100%, 62%, 0.18); }
				}
				.llm-tier-dot {
					width: 8px;
					height: 8px;
					border-radius: 50%;
					flex-shrink: 0;
					transition: background 0.3s, box-shadow 0.3s;
				}
				.llm-tier-dot.idle {
					background: var(--accent-primary, hsla(173, 80%, 40%, 1));
					box-shadow: 0 0 6px hsla(173, 80%, 40%, 0.35);
				}
				.llm-tier-dot.processing {
					background: hsla(210, 100%, 62%, 1);
					box-shadow: 0 0 10px hsla(210, 100%, 62%, 0.6);
					animation: hw-dot-pulse 1.2s infinite;
				}
				@keyframes hw-dot-pulse {
					0%   { box-shadow: 0 0 0 0   hsla(210, 100%, 62%, 0.7); }
					60%  { box-shadow: 0 0 0 6px hsla(210, 100%, 62%, 0); }
					100% { box-shadow: 0 0 0 0   hsla(210, 100%, 62%, 0); }
				}
				.llm-tier-dot.offline {
					background: var(--status-danger, hsla(0, 84%, 60%, 0.5));
				}
				.llm-tier-name {
					font-size: 0.65rem;
					font-weight: 700;
					text-transform: uppercase;
					letter-spacing: 0.06em;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.75));
					min-width: 52px;
					flex-shrink: 0;
				}
				.llm-tier-model {
					font-size: 0.7rem;
					font-weight: 600;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.85));
					font-family: var(--font-mono, 'Fira Code', monospace);
					white-space: nowrap;
					overflow: hidden;
					text-overflow: ellipsis;
					max-width: 140px;
					flex: 1;
					min-width: 0;
				}
				.llm-tier-meta {
					font-size: 0.6rem;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.35));
					font-family: var(--font-mono, 'Fira Code', monospace);
					white-space: nowrap;
					flex-shrink: 0;
				}
				.llm-activity-pill {
					font-size: 0.55rem;
					font-weight: 700;
					letter-spacing: 0.08em;
					padding: 0.1rem 0.4rem;
					border-radius: 0.25rem;
					line-height: 1.6;
					flex-shrink: 0;
					font-family: var(--font-mono, 'Fira Code', monospace);
					transition: background 0.3s, color 0.3s;
				}
				.llm-activity-pill.busy {
					background: hsla(210, 100%, 62%, 0.18);
					color: hsla(210, 100%, 72%, 1);
					border: 1px solid hsla(210, 100%, 62%, 0.4);
					animation: pill-flash 1.2s infinite;
				}
				@keyframes pill-flash {
					0%, 100% { opacity: 1; }
					50% { opacity: 0.6; }
				}
				.llm-activity-pill.idle {
					background: hsla(173, 80%, 40%, 0.1);
					color: hsla(173, 80%, 55%, 0.7);
					border: 1px solid hsla(173, 80%, 40%, 0.2);
				}
				.llm-activity-pill.offline {
					background: hsla(0, 84%, 60%, 0.07);
					color: hsla(0, 84%, 65%, 0.5);
					border: 1px solid hsla(0, 84%, 60%, 0.15);
				}
				@media (forced-colors: active) {
					.h-icon { background: ButtonFace; border: 1px solid ButtonText; }
					.simd-badge.active { border-color: Highlight; }
					.status-dot { background: ButtonText; }
					.capability-summary.excellent { border-color: Highlight; }
					.capability-summary.limited { border-color: LinkText; }
					.ram-seg-apps { background: Highlight; }
					.ram-seg-apps.critical { background: LinkText; }
					.ram-seg-cache { background: ButtonFace; border: 1px solid ButtonText; }
					.ram-legend-swatch.apps { background: Highlight; }
					.ram-legend-swatch.apps.critical { background: LinkText; }
					.ram-legend-swatch.cache, .ram-legend-swatch.free { background: ButtonFace; border: 1px solid ButtonText; }
				}
			</style>

			<h2>
				<span class="h-icon" aria-hidden="true">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
						<rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect>
						<rect x="9" y="9" width="6" height="6"></rect>
						<line x1="9" y1="1" x2="9" y2="4"></line>
						<line x1="15" y1="1" x2="15" y2="4"></line>
						<line x1="9" y1="20" x2="9" y2="23"></line>
						<line x1="15" y1="20" x2="15" y2="23"></line>
						<line x1="20" y1="9" x2="23" y2="9"></line>
						<line x1="20" y1="14" x2="23" y2="14"></line>
						<line x1="1" y1="9" x2="4" y2="9"></line>
						<line x1="1" y1="14" x2="4" y2="14"></line>
					</svg>
				</span>
				${this.tr('hardware', 'Hardware')}
			</h2>

			<div id="hw-panel" aria-live="polite" aria-label="${this.tr('aria_hw_status', 'Hardware status')}">
				<div class="empty-state">${this.tr('detecting_hw', 'Detecting hardware...')}</div>
			</div>
		`;
	}
}

customElements.define('hardware-monitor', HardwareMonitor);
