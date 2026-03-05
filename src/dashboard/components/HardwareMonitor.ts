import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { GLASS_TOOLTIP_STYLES } from '../services/glassTooltipStyles';
import { STATUS_STYLES } from '../services/statusStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';

export class HardwareMonitor extends HTMLElement {
	private cpuData: any = null;
	private serverData: any = null;
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
		this._refreshTimer = setInterval(() => this.fetchAll(), 10_000);
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
			const [cpuRes, serverRes] = await Promise.all([
				fetch('/api/dashboard/benchmark/cpu'),
				fetch('/api/dashboard/server-info'),
			]);
			if (cpuRes.ok) this.cpuData = await cpuRes.json();
			if (serverRes.ok) this.serverData = await serverRes.json();
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
		const ramBarClass = ramPct > 90 ? 'critical' : ramPct > 75 ? 'warning' : 'healthy';
		const ramHtml = s.ram_total_gb ? `
			<div class="ram-section">
				<div class="ram-header">
					<span class="spec-label">${this.tr('ram', 'RAM')}</span>
					<span class="ram-values">${(s.ram_total_gb - s.ram_available_gb).toFixed(1)} / ${s.ram_total_gb} GB</span>
				</div>
				<div class="ram-bar-track has-tip" data-tip="${this.tr('tip_ram_usage', 'Total system RAM usage. LLM models are memory-mapped (mlock) so they consume significant RAM. If usage exceeds ~90%, swapping will severely degrade performance.')}" role="presentation">
					<div class="ram-bar-fill ${ramBarClass}" role="progressbar" aria-valuenow="${ramPct}" aria-valuemin="0" aria-valuemax="100" aria-label="${this.tr('ram_usage_label', 'RAM usage')}: ${ramPct}%" style="width: ${Math.min(ramPct, 100)}%"></div>
				</div>
				<span class="ram-pct ${ramBarClass}" aria-hidden="true">${ramPct}% ${this.tr('used', 'used')}</span>
			</div>
		` : '';

		// Uptime
		const uptimeHtml = s.uptime_human ? `
			<div class="spec-item has-tip" data-tip="${this.tr('tip_uptime', 'How long the server has been running since last reboot.')}">
				<span class="spec-label">${this.tr('uptime', 'Uptime')}</span>
				<span class="spec-value">${s.uptime_human}</span>
			</div>
		` : '';

		// Per-tier LLM thread allocation
		const tiers = s.tiers || {};
		const tierNames = ['instant', 'standard', 'deep'];
		const totalConfiguredThreads = tierNames.reduce((sum, t) => sum + ((tiers[t] || {}).threads || 0), 0);
		const tierRows = tierNames.map(t => {
			const tier = tiers[t] || {};
			const statusCls = tier.status === 'ok' || tier.status === 'online' || tier.status === 'no slot available' ? 'online' : 'offline';
			const statusLabelKey = statusCls === 'online' ? 'status_online' : 'status_offline';
			const statusLabel = this.tr(statusLabelKey, statusCls === 'online' ? 'Online' : 'Offline');
			const warningHtml = tier.thread_warning
				? `<span class="tier-warning has-tip" data-tip="${tier.thread_warning}">\u26A0</span>`
				: '';
			return `
				<div class="tier-row">
					<span class="tier-name">${t}</span>
					<span class="tier-status ${statusCls}" aria-label="${t} ${this.tr('tier_is', 'tier is')} ${statusLabel}">${statusLabel}</span>
					<span class="tier-threads has-tip" data-tip="${this.tr('tip_threads_assigned', 'Threads assigned to this tier\'s llama-server instance.')}">${tier.threads || '?'}T</span>
					${warningHtml}
				</div>
			`;
		}).join('');

		const tierHtml = Object.keys(tiers).length > 0 ? `
			<div class="tier-section">
				<span class="spec-label has-tip" data-tip="${this.tr('tip_llm_tiers', 'Thread allocation across the 3 LLM tiers. Total should not exceed physical cores to avoid contention.')}">${this.tr('llm_tiers', 'LLM Tiers')} (${totalConfiguredThreads}T / ${d.cores_physical || s.physical_cores || '?'}C)</span>
				<div class="tier-grid">${tierRows}</div>
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
			<div class="simd-row has-tip" data-tip="${this.tr('tip_simd', 'SIMD (Single Instruction, Multiple Data) extensions allow the CPU to process multiple values in parallel. Higher SIMD = faster LLM inference.')}">
				<span class="spec-label">${this.tr('simd', 'SIMD')}</span>
				<div class="simd-badges">${badgesHtml}</div>
			</div>
			${tierHtml}
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
					height: 8px;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.05));
					border-radius: 4px;
					overflow: hidden;
					cursor: help;
				}
				.ram-bar-fill {
					height: 100%;
					border-radius: 4px;
					transition: width var(--duration-slow, 0.5s);
				}
				.ram-bar-fill.healthy { background: var(--accent-primary, hsla(173, 80%, 40%, 1)); }
				.ram-bar-fill.warning { background: var(--status-warning, hsla(45, 93%, 47%, 1)); }
				.ram-bar-fill.critical { background: var(--status-danger, hsla(0, 84%, 60%, 1)); }
				.ram-pct {
					font-size: 0.65rem;
					font-weight: 500;
					margin-top: 0.25rem;
					display: block;
				}
				.ram-pct.healthy { color: var(--accent-primary, hsla(173, 80%, 40%, 0.8)); }
				.ram-pct.warning { color: var(--status-warning, hsla(45, 93%, 47%, 0.8)); }
				.ram-pct.critical { color: var(--status-danger, hsla(0, 84%, 60%, 0.85)); }

				/* ── LLM Tier Grid ── */
				.tier-section {
					margin-bottom: 1rem;
				}
				.tier-grid {
					display: flex;
					gap: 0.5rem;
					margin-top: 0.4rem;
				}
				.tier-row {
					display: flex;
					align-items: center;
					gap: 0.4rem;
					padding: 0.35rem 0.65rem;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.06));
					border-radius: 0.4rem;
					flex: 1;
					min-height: 44px;
				}
				.tier-name {
					font-size: 0.65rem;
					font-weight: 700;
					text-transform: uppercase;
					letter-spacing: 0.08em;
					color: var(--accent-secondary, hsla(216, 100%, 50%, 1));
					font-family: var(--font-mono, 'Fira Code', monospace);
				}
				.tier-status {
					font-size: 0.6rem;
					font-weight: 600;
					text-transform: uppercase;
					letter-spacing: 0.05em;
				}
				.tier-status.online { color: var(--accent-primary, hsla(173, 80%, 40%, 1)); }
				.tier-status.offline { color: var(--status-danger, hsla(0, 84%, 60%, 1)); }
				.tier-threads {
					font-size: 0.7rem;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.5));
					font-family: var(--font-mono, 'Fira Code', monospace);
					margin-left: auto;
				}
				.tier-warning {
					color: var(--status-warning, hsla(45, 93%, 47%, 1));
					font-size: 0.75rem;
					cursor: help;
				}

				.simd-badge:focus-visible, .tier-row:focus-visible { 
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); 
					outline-offset: 2px; 
				}
				@media (forced-colors: active) {
					.h-icon { background: ButtonFace; border: 1px solid ButtonText; }
					.simd-badge.active { border-color: Highlight; }
					.status-dot { background: ButtonText; }
					.capability-summary.excellent { border-color: Highlight; }
					.capability-summary.limited { border-color: LinkText; }
					.ram-bar-fill { background: Highlight; }
					.ram-bar-fill.critical { background: LinkText; }
					.tier-status.online { color: ButtonText; }
					.tier-status.offline { color: LinkText; }
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
