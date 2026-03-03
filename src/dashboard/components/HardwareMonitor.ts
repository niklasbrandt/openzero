export class HardwareMonitor extends HTMLElement {
	private cpuData: any = null;
	private serverData: any = null;
	private t: Record<string, string> = {};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
		this.loadTranslations().then(() => this.fetchAll());
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => this.updatePanel());
		});
	}

	private async loadTranslations() {
		try {
			const res = await fetch('/api/dashboard/translations');
			if (res.ok) this.t = await res.json();
		} catch (_) {}
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
			if (el) el.innerHTML = `<div class="empty">${this.tr('hw_error', 'Could not reach hardware probe. Is the backend running?')}</div>`;
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
			`<span class="simd-badge ${b.active ? 'active' : 'inactive'} has-tip" data-tip="${b.tip}" tabindex="0" role="img" aria-label="${b.name}: ${b.active ? 'Supported' : 'Not available'}. ${b.tip}">${b.name}</span>`
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
				<div class="ram-bar-track has-tip" data-tip="Total system RAM usage. LLM models are memory-mapped (mlock) so they consume significant RAM. If usage exceeds ~90%, swapping will severely degrade performance.">
					<div class="ram-bar-fill ${ramBarClass}" style="width: ${Math.min(ramPct, 100)}%"></div>
				</div>
				<span class="ram-pct ${ramBarClass}">${ramPct}% used</span>
			</div>
		` : '';

		// Uptime
		const uptimeHtml = s.uptime_human ? `
			<div class="spec-item has-tip" data-tip="How long the server has been running since last reboot.">
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
			const statusLabel = statusCls === 'online' ? 'online' : 'offline';
			const warningHtml = tier.thread_warning
				? `<span class="tier-warning has-tip" data-tip="${tier.thread_warning}">\u26A0</span>`
				: '';
			return `
				<div class="tier-row">
					<span class="tier-name">${t}</span>
					<span class="tier-status ${statusCls}" aria-label="${t} tier is ${statusLabel}">${statusLabel}</span>
					<span class="tier-threads has-tip" data-tip="Threads assigned to this tier's llama-server instance.">${tier.threads || '?'}T</span>
					${warningHtml}
				</div>
			`;
		}).join('');

		const tierHtml = Object.keys(tiers).length > 0 ? `
			<div class="tier-section">
				<span class="spec-label has-tip" data-tip="Thread allocation across the 3 LLM tiers. Total should not exceed physical cores to avoid contention.">${this.tr('llm_tiers', 'LLM Tiers')} (${totalConfiguredThreads}T / ${d.cores_physical || s.physical_cores || '?'}C)</span>
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
			<div class="capability-summary ${capabilityClass}">
				<span class="capability-dot"></span>
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
			tip.textContent = text;
			el.appendChild(tip);
		});
	}

	render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
			<style>
				:host { display: block; }
				h2 {
					font-size: 1.5rem;
					font-weight: bold;
					margin: 0 0 1.5rem 0;
					color: #fff;
					letter-spacing: 0.02em;
					display: flex;
					align-items: center;
					gap: 0.5rem;
				}
				h2 .icon {
					display: inline-flex;
					width: 28px;
					height: 28px;
					background: linear-gradient(135deg, #6366f1 0%, #14B8A6 100%);
					border-radius: 0.4rem;
					align-items: center;
					justify-content: center;
				}
				h2 .subtitle {
					font-size: 0.65rem;
					font-weight: 400;
					color: rgba(255, 255, 255, 0.3);
					margin-left: 0.5rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
				}

				/* ── Custom tooltip system (real DOM for backdrop-filter) ── */
				.has-tip {
					position: relative;
				}
				.glass-tooltip {
					position: absolute;
					bottom: calc(100% + 10px);
					left: 0;
					background: rgba(255, 255, 255, 0.06);
					backdrop-filter: blur(32px) saturate(1.6) brightness(1.1);
					-webkit-backdrop-filter: blur(32px) saturate(1.6) brightness(1.1);
					color: rgba(255, 255, 255, 0.92);
					font-size: 0.68rem;
					line-height: 1.5;
					padding: 0.55rem 0.75rem;
					border-radius: 0.5rem;
					border: 1px solid rgba(255, 255, 255, 0.18);
					white-space: normal;
					width: max-content;
					max-width: 280px;
					pointer-events: none;
					opacity: 0;
					transition: opacity 0.18s ease;
					z-index: 1000;
					box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.12), inset 0 0 0 0.5px rgba(255, 255, 255, 0.08);
				}
				.has-tip:hover > .glass-tooltip,
				.has-tip:focus-visible > .glass-tooltip {
					opacity: 1;
				}
				/* Suppress parent tooltip when a nested child is hovered */
				.has-tip:has(.has-tip:hover) > .glass-tooltip,
				.has-tip:has(.has-tip:focus-visible) > .glass-tooltip {
					opacity: 0 !important;
				}

				.cpu-model {
					font-size: 1rem;
					font-weight: 600;
					color: #fff;
					margin-bottom: 1rem;
					line-height: 1.4;
					font-family: 'Fira Code', 'SF Mono', monospace;
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
					color: rgba(255, 255, 255, 0.3);
					font-weight: 600;
				}

				.spec-value {
					font-size: 0.9rem;
					color: rgba(255, 255, 255, 0.85);
					font-family: 'Fira Code', monospace;
				}

				.simd-row {
					display: flex;
					align-items: center;
					gap: 0.75rem;
					margin-bottom: 1rem;
					cursor: help;
				}

				.simd-badges {
					display: flex;
					gap: 0.4rem;
				}

				.simd-badge {
					font-size: 0.7rem;
					font-weight: 700;
					letter-spacing: 0.05em;
					padding: 0.2rem 0.5rem;
					border-radius: 0.3rem;
					font-family: 'Fira Code', monospace;
					cursor: help;
					transition: transform 0.15s ease;
				}

				.simd-badge:hover, .simd-badge:focus-visible {
					transform: scale(1.08);
					outline: none;
				}

				.simd-badge.active {
					background: rgba(20, 184, 166, 0.15);
					color: #14B8A6;
					border: 1px solid rgba(20, 184, 166, 0.3);
				}

				.simd-badge.inactive {
					background: rgba(255, 255, 255, 0.03);
					color: rgba(255, 255, 255, 0.2);
					border: 1px solid rgba(255, 255, 255, 0.06);
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
				}

				.capability-dot {
					width: 8px;
					height: 8px;
					border-radius: 50%;
					flex-shrink: 0;
				}

				.capability-summary.excellent {
					background: rgba(20, 184, 166, 0.08);
					color: #14B8A6;
					border: 1px solid rgba(20, 184, 166, 0.15);
				}
				.capability-summary.excellent .capability-dot { background: #14B8A6; }

				.capability-summary.good {
					background: rgba(234, 179, 8, 0.08);
					color: #eab308;
					border: 1px solid rgba(234, 179, 8, 0.15);
				}
				.capability-summary.good .capability-dot { background: #eab308; }

				.capability-summary.limited {
					background: rgba(239, 68, 68, 0.08);
					color: #ef4444;
					border: 1px solid rgba(239, 68, 68, 0.15);
				}
				.capability-summary.limited .capability-dot { background: #ef4444; }

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
					color: rgba(255, 255, 255, 0.7);
					font-family: 'Fira Code', monospace;
				}
				.ram-bar-track {
					height: 8px;
					background: rgba(255, 255, 255, 0.05);
					border-radius: 4px;
					overflow: hidden;
					cursor: help;
				}
				.ram-bar-fill {
					height: 100%;
					border-radius: 4px;
					transition: width 0.5s ease;
				}
				.ram-bar-fill.healthy { background: #14B8A6; }
				.ram-bar-fill.warning { background: #eab308; }
				.ram-bar-fill.critical { background: #ef4444; }
				.ram-pct {
					font-size: 0.65rem;
					font-weight: 500;
					margin-top: 0.25rem;
					display: block;
				}
				.ram-pct.healthy { color: rgba(20, 184, 166, 0.7); }
				.ram-pct.warning { color: rgba(234, 179, 8, 0.7); }
				.ram-pct.critical { color: rgba(239, 68, 68, 0.8); }

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
					background: rgba(255, 255, 255, 0.02);
					border: 1px solid rgba(255, 255, 255, 0.04);
					border-radius: 0.4rem;
					flex: 1;
				}
				.tier-name {
					font-size: 0.65rem;
					font-weight: 700;
					text-transform: uppercase;
					letter-spacing: 0.08em;
					color: #0066FF;
					font-family: 'Fira Code', monospace;
				}
				.tier-status {
					font-size: 0.6rem;
					font-weight: 600;
					text-transform: uppercase;
					letter-spacing: 0.05em;
				}
				.tier-status.online { color: #14B8A6; }
				.tier-status.offline { color: #ef4444; }
				.tier-threads {
					font-size: 0.7rem;
					color: rgba(255, 255, 255, 0.5);
					font-family: 'Fira Code', monospace;
					margin-left: auto;
				}
				.tier-warning {
					color: #eab308;
					font-size: 0.75rem;
					cursor: help;
				}

				.empty {
					color: rgba(255, 255, 255, 0.2);
					font-size: 0.85rem;
					font-style: italic;
					text-align: center;
					padding: 1.5rem;
				}
			</style>

			<h2>
				<span class="icon">
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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
				<span class="subtitle">${this.tr('hw_subtitle', 'CPU &amp; SIMD Capabilities')}</span>
			</h2>

			<div id="hw-panel">
				<div class="empty">${this.tr('detecting_hw', 'Detecting hardware...')}</div>
			</div>
		`;
	}
}

customElements.define('hardware-monitor', HardwareMonitor);
