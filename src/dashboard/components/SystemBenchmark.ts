export class SystemBenchmark extends HTMLElement {
	private cpuData: any = null;
	private benchResults: any[] = [];
	private isRunning: boolean = false;

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
			this.updateCpuPanel();
		} catch (e) {
			console.error('Failed to fetch CPU info:', e);
		}
	}

	async runBenchmark(tier: string) {
		if (this.isRunning) return;
		this.isRunning = true;
		const btn = this.shadowRoot?.querySelector(`#bench-${tier}`) as HTMLButtonElement;
		if (btn) {
			btn.classList.add('running');
			btn.textContent = 'Running...';
		}

		try {
			const res = await fetch(`/api/dashboard/benchmark/llm?tier=${tier}`, { method: 'POST' });
			if (!res.ok) throw new Error('API error');
			const data = await res.json();
			this.benchResults = this.benchResults.filter(r => r.tier !== tier);
			this.benchResults.push(data);
			this.updateBenchPanel();
		} catch (e) {
			console.error('Benchmark failed:', e);
		} finally {
			this.isRunning = false;
			if (btn) {
				btn.classList.remove('running');
				btn.textContent = `Bench ${tier}`;
			}
		}
	}

	async runAllBenchmarks() {
		if (this.isRunning) return;
		const tiers = ['instant', 'standard', 'deep'];
		for (const tier of tiers) {
			await this.runBenchmark(tier);
		}
	}

	updateCpuPanel() {
		const el = this.shadowRoot?.querySelector('#cpu-panel');
		if (!el || !this.cpuData) return;
		const d = this.cpuData;
		const simdBadges = [
			{ name: 'SSE4.2', active: d.sse4_2 },
			{ name: 'AVX2', active: d.avx2 },
			{ name: 'AVX-512', active: d.avx512 },
		];
		const badgesHtml = simdBadges.map(b =>
			`<span class="simd-badge ${b.active ? 'active' : 'inactive'}">${b.name}</span>`
		).join('');

		el.innerHTML = `
			<div class="cpu-model">${d.cpu_model}</div>
			<div class="cpu-specs">
				<div class="spec-item">
					<span class="spec-label">Cores</span>
					<span class="spec-value">${d.cores_physical}P / ${d.cores_logical}L</span>
				</div>
				<div class="spec-item">
					<span class="spec-label">Arch</span>
					<span class="spec-value">${d.architecture}</span>
				</div>
				<div class="spec-item">
					<span class="spec-label">Platform</span>
					<span class="spec-value">${d.platform}</span>
				</div>
			</div>
			<div class="simd-row">
				<span class="spec-label">SIMD</span>
				<div class="simd-badges">${badgesHtml}</div>
			</div>
		`;
	}

	updateBenchPanel() {
		const el = this.shadowRoot?.querySelector('#bench-results');
		if (!el) return;

		if (this.benchResults.length === 0) {
			el.innerHTML = '<div class="empty">No benchmarks run yet.</div>';
			return;
		}

		const html = this.benchResults.map(r => {
			if (r.error) {
				return `
					<div class="bench-card error">
						<div class="bench-tier">${r.tier}</div>
						<div class="bench-model">${r.model}</div>
						<div class="bench-error">${r.error}</div>
					</div>
				`;
			}

			const tpsClass = r.tokens_per_second >= 10 ? 'excellent' :
				r.tokens_per_second >= 5 ? 'good' :
				r.tokens_per_second >= 2 ? 'moderate' : 'slow';

			return `
				<div class="bench-card">
					<div class="bench-header">
						<span class="bench-tier">${r.tier}</span>
						<span class="bench-model">${r.model}</span>
					</div>
					<div class="bench-tps ${tpsClass}">
						<span class="tps-value">${r.tokens_per_second}</span>
						<span class="tps-unit">tok/s</span>
					</div>
					<div class="bench-details">
						<div class="detail">
							<span class="detail-label">TTFT</span>
							<span class="detail-value">${r.time_to_first_token}s</span>
						</div>
						<div class="detail">
							<span class="detail-label">Tokens</span>
							<span class="detail-value">${r.tokens}</span>
						</div>
						<div class="detail">
							<span class="detail-label">Total</span>
							<span class="detail-value">${r.total_seconds}s</span>
						</div>
					</div>
				</div>
			`;
		}).join('');

		el.innerHTML = html;
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
					background: linear-gradient(135deg, #0066FF 0%, #14B8A6 100%);
					border-radius: 0.4rem;
					align-items: center;
					justify-content: center;
				}

				.bench-grid {
					display: grid;
					grid-template-columns: 1fr 1fr;
					gap: 1.5rem;
				}

				@media (max-width: 900px) {
					.bench-grid { grid-template-columns: 1fr; }
				}

				.panel {
					background: rgba(0, 0, 0, 0.25);
					border: 1px solid rgba(255, 255, 255, 0.04);
					border-radius: 0.75rem;
					padding: 1.25rem;
				}

				.panel-header {
					display: flex;
					justify-content: space-between;
					align-items: center;
					margin-bottom: 1rem;
				}

				.panel-title {
					font-size: 0.75rem;
					text-transform: uppercase;
					letter-spacing: 0.12em;
					color: rgba(255, 255, 255, 0.35);
					font-weight: 600;
				}

				.cpu-model {
					font-size: 1rem;
					font-weight: 600;
					color: #fff;
					margin-bottom: 1rem;
					line-height: 1.4;
					font-family: 'Fira Code', 'SF Mono', monospace;
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

				.bench-actions {
					display: flex;
					gap: 0.4rem;
					flex-wrap: wrap;
				}

				.bench-btn {
					background: rgba(0, 102, 255, 0.08);
					color: #0066FF;
					border: 1px solid rgba(0, 102, 255, 0.2);
					padding: 0.3rem 0.7rem;
					border-radius: 0.4rem;
					font-size: 0.7rem;
					font-weight: 600;
					cursor: pointer;
					transition: all 0.2s;
					font-family: 'Fira Code', monospace;
					text-transform: uppercase;
					letter-spacing: 0.05em;
				}

				.bench-btn:hover {
					background: rgba(0, 102, 255, 0.2);
					border-color: #0066FF;
				}

				.bench-btn:focus-visible {
					outline: 2px solid #0066FF;
					outline-offset: 2px;
				}

				.bench-btn.running {
					opacity: 0.6;
					pointer-events: none;
					animation: pulse 1.5s ease-in-out infinite;
				}

				.bench-btn.all {
					background: rgba(20, 184, 166, 0.08);
					color: #14B8A6;
					border-color: rgba(20, 184, 166, 0.2);
				}

				.bench-btn.all:hover {
					background: rgba(20, 184, 166, 0.2);
					border-color: #14B8A6;
				}

				@keyframes pulse {
					0%, 100% { opacity: 0.6; }
					50% { opacity: 1; }
				}

				#bench-results {
					display: flex;
					flex-direction: column;
					gap: 0.75rem;
				}

				.bench-card {
					background: rgba(255, 255, 255, 0.02);
					border: 1px solid rgba(255, 255, 255, 0.04);
					border-radius: 0.6rem;
					padding: 1rem;
				}

				.bench-card.error {
					border-color: rgba(239, 68, 68, 0.2);
				}

				.bench-header {
					display: flex;
					justify-content: space-between;
					align-items: center;
					margin-bottom: 0.75rem;
				}

				.bench-tier {
					font-size: 0.7rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
					font-weight: 700;
					color: #0066FF;
					font-family: 'Fira Code', monospace;
				}

				.bench-model {
					font-size: 0.75rem;
					color: rgba(255, 255, 255, 0.4);
					font-family: 'Fira Code', monospace;
				}

				.bench-error {
					color: #ef4444;
					font-size: 0.8rem;
					margin-top: 0.5rem;
				}

				.bench-tps {
					display: flex;
					align-items: baseline;
					gap: 0.3rem;
					margin-bottom: 0.75rem;
				}

				.tps-value {
					font-size: 2rem;
					font-weight: 800;
					font-family: 'Fira Code', monospace;
					line-height: 1;
				}

				.tps-unit {
					font-size: 0.7rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
					opacity: 0.5;
					font-weight: 600;
				}

				.bench-tps.excellent .tps-value { color: #14B8A6; }
				.bench-tps.good .tps-value { color: #22c55e; }
				.bench-tps.moderate .tps-value { color: #eab308; }
				.bench-tps.slow .tps-value { color: #ef4444; }

				.bench-details {
					display: grid;
					grid-template-columns: repeat(3, 1fr);
					gap: 0.5rem;
				}

				.detail {
					display: flex;
					flex-direction: column;
					gap: 0.1rem;
				}

				.detail-label {
					font-size: 0.6rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
					color: rgba(255, 255, 255, 0.25);
					font-weight: 600;
				}

				.detail-value {
					font-size: 0.85rem;
					color: rgba(255, 255, 255, 0.7);
					font-family: 'Fira Code', monospace;
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
						<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
					</svg>
				</span>
				System Benchmark
			</h2>

			<div class="bench-grid">
				<div class="panel">
					<div class="panel-header">
						<span class="panel-title">CPU / Hardware</span>
					</div>
					<div id="cpu-panel">
						<div class="empty">Detecting hardware...</div>
					</div>
				</div>

				<div class="panel">
					<div class="panel-header">
						<span class="panel-title">LLM Throughput</span>
						<div class="bench-actions">
							<button class="bench-btn" id="bench-instant" aria-label="Benchmark instant tier">Bench instant</button>
							<button class="bench-btn" id="bench-standard" aria-label="Benchmark standard tier">Bench standard</button>
							<button class="bench-btn" id="bench-deep" aria-label="Benchmark deep tier">Bench deep</button>
							<button class="bench-btn all" id="bench-all" aria-label="Run all benchmarks">Run All</button>
						</div>
					</div>
					<div id="bench-results">
						<div class="empty">Click a tier to measure tokens/second.</div>
					</div>
				</div>
			</div>
		`;

		this.shadowRoot?.querySelector('#bench-instant')?.addEventListener('click', () => this.runBenchmark('instant'));
		this.shadowRoot?.querySelector('#bench-standard')?.addEventListener('click', () => this.runBenchmark('standard'));
		this.shadowRoot?.querySelector('#bench-deep')?.addEventListener('click', () => this.runBenchmark('deep'));
		this.shadowRoot?.querySelector('#bench-all')?.addEventListener('click', () => this.runAllBenchmarks());
	}
}

customElements.define('system-benchmark', SystemBenchmark);
