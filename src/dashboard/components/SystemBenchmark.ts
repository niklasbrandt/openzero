export class SystemBenchmark extends HTMLElement {
	private benchResults: any[] = [];
	private isRunning: boolean = false;

	// Expected tok/s ranges per tier on CPU-only (Q4_K_M quantized)
	private static readonly EXPECTATIONS: Record<string, { model: string; fast: number; good: number; ok: number }> = {
		instant: { model: '~3-4B', fast: 15, good: 8, ok: 3 },
		standard: { model: '~8B', fast: 10, good: 5, ok: 2 },
		deep: { model: '~14B', fast: 6, good: 3, ok: 1.5 },
	};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
	}

	async runBenchmark(tier: string) {
		if (this.isRunning) return;
		this.isRunning = true;
		const btn = this.shadowRoot?.querySelector(`#bench-${tier}`) as HTMLButtonElement;
		if (btn) {
			btn.classList.add('running');
			btn.textContent = 'Running\u2026';
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

	private getRating(tps: number, tier: string): { cls: string; icon: string; label: string; hint: string } {
		const exp = SystemBenchmark.EXPECTATIONS[tier] || SystemBenchmark.EXPECTATIONS['standard'];
		if (tps >= exp.fast) return {
			cls: 'excellent',
			icon: '\uD83D\uDE80',
			label: 'Excellent',
			hint: `Fast real-time conversation. This ${exp.model} model is running well on your hardware.`,
		};
		if (tps >= exp.good) return {
			cls: 'good',
			icon: '\u2705',
			label: 'Good',
			hint: `Comfortable for interactive use. Typical for CPU-only inference with a ${exp.model} model.`,
		};
		if (tps >= exp.ok) return {
			cls: 'moderate',
			icon: '\u26A0\uFE0F',
			label: 'Moderate',
			hint: `Usable but with noticeable latency. Consider fewer concurrent requests or a smaller quantization.`,
		};
		return {
			cls: 'slow',
			icon: '\uD83D\uDC0C',
			label: 'Slow',
			hint: `Below expected for a ${exp.model} model. Check: thread count, available RAM, SIMD support, or try a smaller model.`,
		};
	}

	private getTtftHint(ttft: number): string {
		if (ttft <= 1) return 'Model loaded and warmed up -- great first-token latency.';
		if (ttft <= 3) return 'Normal startup time. The model may be loading from cache.';
		if (ttft <= 8) return 'High TTFT. Model may still be loading into memory or swapping.';
		return 'Very high TTFT -- likely cold-loading the model or the server is memory-constrained. Subsequent runs should be faster.';
	}

	updateBenchPanel() {
		const el = this.shadowRoot?.querySelector('#bench-results');
		if (!el) return;

		if (this.benchResults.length === 0) {
			el.innerHTML = '<div class="empty">Click a tier button to measure tokens/second.</div>';
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

			const rating = this.getRating(r.tokens_per_second, r.tier);
			const ttftHint = this.getTtftHint(parseFloat(r.time_to_first_token));
			const exp = SystemBenchmark.EXPECTATIONS[r.tier] || SystemBenchmark.EXPECTATIONS['standard'];

			return `
				<div class="bench-card">
					<div class="bench-header">
						<span class="bench-tier" title="The '${r.tier}' tier typically runs a ${exp.model} parameter model.">${r.tier}</span>
						<span class="bench-model" title="Exact model file loaded by llama-server for this tier.">${r.model}</span>
					</div>
					<div class="bench-tps ${rating.cls}" title="Tokens generated per second. Higher is better. ${rating.hint}">
						<span class="tps-value">${r.tokens_per_second}</span>
						<span class="tps-unit">tok/s</span>
					</div>
					<div class="rating-badge ${rating.cls}" title="${rating.hint}">
						<span class="rating-icon">${rating.icon}</span>
						<span class="rating-label">${rating.label}</span>
					</div>
					<div class="rating-hint">${rating.hint}</div>
					<div class="bench-details">
						<div class="detail" title="${ttftHint}">
							<span class="detail-label">TTFT</span>
							<span class="detail-value">${r.time_to_first_token}s</span>
							<span class="detail-hint">${ttftHint}</span>
						</div>
						<div class="detail" title="Number of tokens the model generated during the benchmark prompt. More tokens = more reliable throughput measurement.">
							<span class="detail-label">Tokens</span>
							<span class="detail-value">${r.tokens}</span>
						</div>
						<div class="detail" title="Wall-clock time from request to last token. Includes TTFT + generation time.">
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
				h2 .subtitle {
					font-size: 0.65rem;
					font-weight: 400;
					color: rgba(255, 255, 255, 0.3);
					margin-left: 0.5rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
				}

				.bench-header-bar {
					display: flex;
					justify-content: space-between;
					align-items: center;
					margin-bottom: 1.25rem;
					flex-wrap: wrap;
					gap: 0.5rem;
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
					padding: 0.35rem 0.8rem;
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

				.legend {
					display: flex;
					gap: 1rem;
					flex-wrap: wrap;
					margin-bottom: 1.25rem;
					padding: 0.6rem 0.8rem;
					background: rgba(0, 0, 0, 0.15);
					border-radius: 0.5rem;
					border: 1px solid rgba(255, 255, 255, 0.03);
				}

				.legend-item {
					display: flex;
					align-items: center;
					gap: 0.35rem;
					font-size: 0.65rem;
					color: rgba(255, 255, 255, 0.45);
					cursor: help;
				}

				.legend-dot {
					width: 8px;
					height: 8px;
					border-radius: 50%;
					flex-shrink: 0;
				}

				.legend-dot.excellent { background: #14B8A6; }
				.legend-dot.good { background: #22c55e; }
				.legend-dot.moderate { background: #eab308; }
				.legend-dot.slow { background: #ef4444; }

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
					margin-bottom: 0.6rem;
				}

				.bench-tier {
					font-size: 0.7rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
					font-weight: 700;
					color: #0066FF;
					font-family: 'Fira Code', monospace;
					cursor: help;
				}

				.bench-model {
					font-size: 0.75rem;
					color: rgba(255, 255, 255, 0.4);
					font-family: 'Fira Code', monospace;
					cursor: help;
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
					margin-bottom: 0.4rem;
					cursor: help;
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

				.rating-badge {
					display: inline-flex;
					align-items: center;
					gap: 0.3rem;
					padding: 0.2rem 0.6rem;
					border-radius: 1rem;
					font-size: 0.7rem;
					font-weight: 600;
					margin-bottom: 0.5rem;
					cursor: help;
				}

				.rating-icon { font-size: 0.8rem; }

				.rating-badge.excellent {
					background: rgba(20, 184, 166, 0.1);
					color: #14B8A6;
					border: 1px solid rgba(20, 184, 166, 0.2);
				}
				.rating-badge.good {
					background: rgba(34, 197, 94, 0.1);
					color: #22c55e;
					border: 1px solid rgba(34, 197, 94, 0.2);
				}
				.rating-badge.moderate {
					background: rgba(234, 179, 8, 0.1);
					color: #eab308;
					border: 1px solid rgba(234, 179, 8, 0.2);
				}
				.rating-badge.slow {
					background: rgba(239, 68, 68, 0.1);
					color: #ef4444;
					border: 1px solid rgba(239, 68, 68, 0.2);
				}

				.rating-hint {
					font-size: 0.72rem;
					color: rgba(255, 255, 255, 0.35);
					line-height: 1.4;
					margin-bottom: 0.75rem;
					font-style: italic;
				}

				.bench-details {
					display: grid;
					grid-template-columns: repeat(3, 1fr);
					gap: 0.5rem;
				}

				.detail {
					display: flex;
					flex-direction: column;
					gap: 0.1rem;
					cursor: help;
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

				.detail-hint {
					font-size: 0.6rem;
					color: rgba(255, 255, 255, 0.2);
					line-height: 1.35;
					margin-top: 0.15rem;
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
				LLM Benchmark
				<span class="subtitle">Throughput &amp; Performance Rating</span>
			</h2>

			<div class="bench-header-bar">
				<div class="bench-actions">
					<button class="bench-btn" id="bench-instant" title="Benchmark the instant tier (~3-4B model). Used for quick tasks like fact extraction and classification." aria-label="Benchmark instant tier">Bench instant</button>
					<button class="bench-btn" id="bench-standard" title="Benchmark the standard tier (~8B model). Used for general conversation and reasoning." aria-label="Benchmark standard tier">Bench standard</button>
					<button class="bench-btn" id="bench-deep" title="Benchmark the deep tier (~14B model). Used for complex analysis and strategic thinking." aria-label="Benchmark deep tier">Bench deep</button>
					<button class="bench-btn all" id="bench-all" title="Run all three tier benchmarks sequentially to get a complete performance picture." aria-label="Run all benchmarks">Run All</button>
				</div>
			</div>

			<div class="legend" title="Performance rating scale based on expected throughput for each model size on CPU-only inference with Q4_K_M quantization.">
				<span class="legend-item" title="Fast real-time conversation. No noticeable delay between tokens."><span class="legend-dot excellent"></span>Excellent</span>
				<span class="legend-item" title="Comfortable interactive speed with slight streaming visible."><span class="legend-dot good"></span>Good</span>
				<span class="legend-item" title="Usable but noticeable word-by-word generation."><span class="legend-dot moderate"></span>Moderate</span>
				<span class="legend-item" title="Below expected. Check SIMD, thread count, or try a smaller model."><span class="legend-dot slow"></span>Slow</span>
			</div>

			<div id="bench-results">
				<div class="empty">Click a tier button to measure tokens/second.</div>
			</div>
		`;

		this.shadowRoot?.querySelector('#bench-instant')?.addEventListener('click', () => this.runBenchmark('instant'));
		this.shadowRoot?.querySelector('#bench-standard')?.addEventListener('click', () => this.runBenchmark('standard'));
		this.shadowRoot?.querySelector('#bench-deep')?.addEventListener('click', () => this.runBenchmark('deep'));
		this.shadowRoot?.querySelector('#bench-all')?.addEventListener('click', () => this.runAllBenchmarks());
	}
}

customElements.define('system-benchmark', SystemBenchmark);
