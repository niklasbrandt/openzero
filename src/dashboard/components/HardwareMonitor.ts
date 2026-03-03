export class HardwareMonitor extends HTMLElement {
	private cpuData: any = null;

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
		this.fetchCpuInfo();
	}

	async fetchCpuInfo() {
		try {
			const res = await fetch('/api/dashboard/benchmark/cpu');
			if (!res.ok) throw new Error('API error');
			this.cpuData = await res.json();
			this.updatePanel();
		} catch (e) {
			console.error('Failed to fetch CPU info:', e);
			const el = this.shadowRoot?.querySelector('#hw-panel');
			if (el) el.innerHTML = '<div class="empty">Could not reach hardware probe. Is the backend running?</div>';
		}
	}

	updatePanel() {
		const el = this.shadowRoot?.querySelector('#hw-panel');
		if (!el || !this.cpuData) return;
		const d = this.cpuData;

		const simdBadges = [
			{ name: 'SSE4.2', active: d.sse4_2, tip: 'Baseline SIMD. Used by all modern llama.cpp builds for basic vectorized math.' },
			{ name: 'AVX2', active: d.avx2, tip: 'Advanced Vector Extensions 2. Doubles throughput for quantized matrix ops. Critical for good tok/s on CPU.' },
			{ name: 'AVX-512', active: d.avx512, tip: 'Widest SIMD. Up to 2x faster than AVX2 for large quantized models. Rare on consumer CPUs, common on EPYC/Xeon.' },
		];

		const badgesHtml = simdBadges.map(b =>
			`<span class="simd-badge ${b.active ? 'active' : 'inactive'}" title="${b.tip}" tabindex="0" role="img" aria-label="${b.name}: ${b.active ? 'Supported' : 'Not available'}. ${b.tip}">${b.name}</span>`
		).join('');

		// Compute a simple capability score for the summary
		const simdScore = (d.avx512 ? 3 : d.avx2 ? 2 : d.sse4_2 ? 1 : 0);
		const coreScore = Math.min(d.cores_physical || 1, 8); // cap at 8 for scoring
		const capabilityClass = simdScore >= 2 && coreScore >= 4 ? 'excellent' :
			simdScore >= 1 && coreScore >= 2 ? 'good' :
			'limited';
		const capabilityText = capabilityClass === 'excellent' ? 'Well-suited for local LLM inference' :
			capabilityClass === 'good' ? 'Adequate for small-to-medium models' :
			'Limited -- expect slow inference on larger models';

		el.innerHTML = `
			<div class="cpu-model" title="CPU model string as reported by the kernel">${d.cpu_model}</div>
			<div class="cpu-specs">
				<div class="spec-item" title="Physical cores run actual computations. Logical cores (hyperthreads) help with scheduling but add less throughput for LLM workloads.">
					<span class="spec-label">Cores</span>
					<span class="spec-value">${d.cores_physical}P / ${d.cores_logical}L</span>
				</div>
				<div class="spec-item" title="CPU instruction set architecture. x86_64 supports the widest range of SIMD extensions for llama.cpp.">
					<span class="spec-label">Arch</span>
					<span class="spec-value">${d.architecture}</span>
				</div>
				<div class="spec-item" title="Host operating system running the Docker containers.">
					<span class="spec-label">Platform</span>
					<span class="spec-value">${d.platform}</span>
				</div>
			</div>
			<div class="simd-row" title="SIMD (Single Instruction, Multiple Data) extensions allow the CPU to process multiple values in parallel. Higher SIMD = faster LLM inference.">
				<span class="spec-label">SIMD</span>
				<div class="simd-badges">${badgesHtml}</div>
			</div>
			<div class="capability-summary ${capabilityClass}">
				<span class="capability-dot"></span>
				<span class="capability-text">${capabilityText}</span>
			</div>
		`;
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
				Hardware
				<span class="subtitle">CPU &amp; SIMD Capabilities</span>
			</h2>

			<div id="hw-panel">
				<div class="empty">Detecting hardware...</div>
			</div>
		`;
	}
}

customElements.define('hardware-monitor', HardwareMonitor);
