import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { GLASS_TOOLTIP_STYLES } from '../services/glassTooltipStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { GOO_STYLES, initGoo } from '../services/gooStyles';

const BENCH_ACCENT = 'var(--accent-secondary-text, hsl(216, 100%, 65%))';
const BENCH_ACCENT_RGB = 'var(--accent-secondary-rgb, 0, 102, 255)';

export class SystemBenchmark extends HTMLElement {
	private benchResults: any[] = [];
	private isRunning: boolean = false;
	private isRunningAll: boolean = false;
	private cloudConfigured: boolean = false;
	private t: Record<string, string> = {};

	// Expected tok/s ranges per tier on CPU-only (Q4_K_M quantized)
	private static readonly EXPECTATIONS: Record<string, { model: string; fast: number; good: number; ok: number }> = {
		local: { model: '~0.6B', fast: 20, good: 14, ok: 7 },
		cloud: { model: 'cloud', fast: 40, good: 20, ok: 8 },
	};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		Promise.all([this.loadTranslations(), this.fetchLlmConfig()]).then(() => this.render());
		initGoo(this);
		window.addEventListener('goo-changed', () => initGoo(this));
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => this.render());
		});
	}

	private async fetchLlmConfig() {
		try {
			const res = await fetch('/api/dashboard/llm-config');
			if (res.ok) {
				const data = await res.json();
				this.cloudConfigured = data.cloud_configured ?? false;
			}
		} catch (_) { }
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

	async runBenchmark(tier: string) {
		if (this.isRunning && !this.isRunningAll) return;
		this.isRunning = true;
		this.toggleButtons(true);
		const btn = this.shadowRoot?.querySelector(`#bench-${tier}`) as HTMLButtonElement;
		if (btn) {
			btn.classList.add('running');
			btn.textContent = 'Running\u2026';
			btn.setAttribute('aria-busy', 'true');
			btn.setAttribute('aria-label', `${this.tr('aria_benchmarking_tier', 'Benchmarking')} ${tier} tier…`);
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
			if (btn) {
				btn.classList.remove('running');
				btn.textContent = this.tr(`bench_${tier}`, `Bench ${tier}`);
				btn.removeAttribute('aria-busy');
				btn.setAttribute('aria-label', `${this.tr('aria_benchmark_tier', 'Benchmark')} ${tier} tier`);
			}
			if (!this.isRunningAll) {
				this.isRunning = false;
				this.toggleButtons(false);
			}
		}
	}

	async runAllBenchmarks() {
		if (this.isRunning || this.isRunningAll) return;
		this.isRunningAll = true;
		this.isRunning = true;
		this.toggleButtons(true);

		const allBtn = this.shadowRoot?.querySelector('#bench-all') as HTMLButtonElement;
		if (allBtn) {
			allBtn.classList.add('running');
			allBtn.textContent = 'Running\u2026';
		}

		try {
			const tiers = ['local', ...(this.cloudConfigured ? ['cloud'] : [])];
			for (const tier of tiers) {
				await this.runBenchmark(tier);
			}
		} finally {
			if (allBtn) {
				allBtn.classList.remove('running');
				allBtn.textContent = this.tr('bench_run_all', 'Run All');
			}
			this.isRunningAll = false;
			this.isRunning = false;
			this.toggleButtons(false);
		}
	}

	private toggleButtons(disabled: boolean) {
		const btns = this.shadowRoot?.querySelectorAll('.bench-btn');
		btns?.forEach(b => {
			(b as HTMLButtonElement).disabled = disabled;
			if (disabled) b.classList.add('disabled-state');
			else b.classList.remove('disabled-state');
		});
	}

	private getRating(tps: number, tier: string): { cls: string; icon: string; label: string; hint: string } {
		const exp = SystemBenchmark.EXPECTATIONS[tier] || SystemBenchmark.EXPECTATIONS['local'];
		if (tps >= exp.fast) return {
			cls: 'excellent',
			icon: '\uD83D\uDE80',
			label: this.tr('excellent', 'Excellent'),
			hint: this.tr('hint_bench_excellent', `Fast real-time conversation. This ${exp.model} model is running well on your hardware.`),
		};
		if (tps >= exp.good) return {
			cls: 'good',
			icon: '\u2705',
			label: this.tr('good', 'Good'),
			hint: this.tr('hint_bench_good', `Comfortable for interactive use. Typical for CPU-only inference with a ${exp.model} model.`),
		};
		if (tps >= exp.ok) return {
			cls: 'moderate',
			icon: '\u26A0\uFE0F',
			label: this.tr('moderate', 'Moderate'),
			hint: this.tr('hint_bench_moderate', `Usable but with noticeable latency. Consider fewer concurrent requests or a smaller quantization.`),
		};
		return {
			cls: 'slow',
			icon: '\uD83D\uDC0C',
			label: this.tr('slow', 'Slow'),
			hint: this.tr('hint_bench_slow', `Below expected for a ${exp.model} model. Check: thread count, available RAM, SIMD support, or try a smaller model.`),
		};
	}

	private getTtftHint(ttft: number): string {
		if (ttft <= 1) return this.tr('hint_ttft_excellent', 'Model loaded and warmed up -- great first-token latency.');
		if (ttft <= 3) return this.tr('hint_ttft_good', 'Normal startup time. The model may be loading from cache.');
		if (ttft <= 8) return this.tr('hint_ttft_moderate', 'High TTFT. Model may still be loading into memory or swapping.');
		return this.tr('hint_ttft_slow', 'Very high TTFT -- likely cold-loading the model or the server is memory-constrained. Subsequent runs should be faster.');
	}

	updateBenchPanel() {
		const el = this.shadowRoot?.querySelector('#bench-results');
		if (!el) return;

		if (this.benchResults.length === 0) {
			el.innerHTML = `<div class="empty-state">${this.tr('bench_empty', 'Click a tier button to measure tokens/second.')}</div>`;
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
			const exp = SystemBenchmark.EXPECTATIONS[r.tier] || SystemBenchmark.EXPECTATIONS['local'];

			// Thread utilization warning
			const warningHtml = r.thread_warning
				? `<div class="thread-warning" tabindex="0" role="alert">
							<span class="warning-icon" aria-hidden="true">&#9888;&#65039;</span>
						<span class="warning-text">${r.thread_warning}</span>
					</div>`
				: '';

			// Thread info line
			const threadInfoHtml = r.configured_threads
				? `<div class="detail has-tip" data-tip="${this.tr('tip_threads_info', 'CPU threads assigned to this llama-server instance vs. total physical cores on the host.')}">
						<span class="detail-label">${this.tr('threads', 'Threads')}</span>
						<span class="detail-value">${r.configured_threads} / ${r.physical_cores}</span>
						<span class="detail-hint">${r.configured_threads} ${this.tr('of', 'of')} ${r.physical_cores} ${this.tr('cores_assigned', 'cores assigned')}</span>
					</div>`
				: '';

			return `
				<div class="bench-card">
					<div class="bench-header">
						<span class="bench-tier has-tip" data-tip="The '${r.tier}' tier typically runs a ${exp.model} parameter model.">${r.tier}</span>
						<span class="bench-model has-tip" data-tip="Exact model file loaded by llama-server for this tier.">${r.model}</span>
					</div>
					${warningHtml}
					<div class="bench-tps ${rating.cls} has-tip" data-tip="Tokens generated per second. Higher is better. ${rating.hint}">
						<span class="tps-value">${r.tokens_per_second}</span>
						<span class="tps-unit">tok/s</span>
					</div>
					<div class="rating-badge ${rating.cls} has-tip" data-tip="${rating.hint}">
						<span class="rating-icon" aria-hidden="true">${rating.icon}</span>
						<span class="rating-label">${rating.label}</span>
					</div>
					<div class="rating-hint">${rating.hint}</div>
					<div class="bench-details">
						<div class="detail has-tip" data-tip="${ttftHint}">
							<span class="detail-label">TTFT</span>
							<span class="detail-value">${r.time_to_first_token}s</span>
						</div>
						<div class="detail has-tip" data-tip="${this.tr('tip_tokens_count', 'Number of tokens the model generated during the benchmark prompt. More tokens = more reliable throughput measurement.')}">
							<span class="detail-label">${this.tr('tokens', 'Tokens')}</span>
							<span class="detail-value">${r.tokens}</span>
						</div>
						<div class="detail has-tip" data-tip="${this.tr('tip_total_time', 'Wall-clock time from request to last token. Includes TTFT + generation time.')}">
							<span class="detail-label">${this.tr('total', 'Total')}</span>
							<span class="detail-value">${r.total_seconds}s</span>
						</div>
						${threadInfoHtml}
					</div>
				</div>
			`;
		}).join('');

		el.innerHTML = html;
		this.injectTooltips();
	}

	render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
			<style>
				:host { display: block; }
				${ACCESSIBILITY_STYLES}
				${GLASS_TOOLTIP_STYLES}
				${SECTION_HEADER_STYLES}
				${EMPTY_STATE_STYLES}
				${GOO_STYLES}

				/* Override icon gradient for benchmark accent */
				h2 .h-icon {
					background: linear-gradient(135deg, ${BENCH_ACCENT} 0%, var(--accent-color, hsla(173, 80%, 40%, 1)) 100%);
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
					background: rgba(${BENCH_ACCENT_RGB}, 0.08);
					color: ${BENCH_ACCENT};
					border: 1px solid rgba(${BENCH_ACCENT_RGB}, 0.2);
					padding: 0.35rem 0.8rem;
					border-radius: var(--radius-sm, 0.4rem);
					font-size: 0.7rem;
					font-weight: 600;
					cursor: pointer;
					transition: all var(--duration-fast, 0.2s);
					font-family: var(--font-mono, 'Fira Code', monospace);
					text-transform: uppercase;
					letter-spacing: 0.05em;
				}

				.bench-btn:hover {
					background: rgba(${BENCH_ACCENT_RGB}, 0.2);
					border-color: ${BENCH_ACCENT};
				}

				.bench-btn:focus-visible {
					outline: 2px solid ${BENCH_ACCENT};
					outline-offset: 2px;
				}

				.bench-btn.running {
					opacity: 0.6;
					pointer-events: none;
					animation: pulse 1.5s ease-in-out infinite;
				}

				.bench-btn.all {
					background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.08);
					color: var(--accent-text, var(--accent-color, hsla(173, 80%, 40%, 1)));
					border-color: rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
				}

				.bench-btn.all:hover:not(:disabled) {
					background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
					border-color: var(--accent-color, hsla(173, 80%, 40%, 1));
				}

				.bench-btn:disabled, .bench-btn.disabled-state {
					opacity: 0.5;
					cursor: not-allowed;
					filter: grayscale(100%);
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
					background: var(--surface-input, hsla(0, 0%, 0%, 0.15));
					border-radius: var(--radius-md, 0.5rem);
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.03));
				}

				.legend-item {
					display: flex;
					align-items: center;
					gap: 0.35rem;
					font-size: 0.65rem;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.45));
					cursor: help;
				}

				.legend-dot {
					width: 8px;
					height: 8px;
					border-radius: 50%;
					flex-shrink: 0;
				}

				.legend-dot.excellent { background: var(--accent-color, hsla(173, 80%, 40%, 1)); }
				.legend-dot.good { background: var(--color-success, hsla(142, 69%, 58%, 1)); }
				.legend-dot.moderate { background: var(--color-warning, hsla(45, 93%, 47%, 1)); }
				.legend-dot.slow { background: var(--color-danger, hsla(0, 84%, 60%, 1)); }

				#bench-results {
					display: flex;
					flex-direction: column;
					gap: 0.75rem;
				}

				.bench-card {
					background: var(--surface-card, hsla(0, 0%, 100%, 0.02));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.04));
					border-radius: var(--radius-md, 0.6rem);
					padding: 1rem;
				}

				.bench-card.error {
					border-color: var(--color-danger, hsla(0, 84%, 60%, 0.2));
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
					color: ${BENCH_ACCENT};
					font-family: var(--font-mono, 'Fira Code', monospace);
					cursor: help;
				}

				.bench-model {
					font-size: 0.75rem;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
					font-family: var(--font-mono, 'Fira Code', monospace);
					cursor: help;
				}

				.thread-warning {
					display: flex;
					align-items: center;
					gap: 0.4rem;
					padding: 0.4rem 0.7rem;
					margin-bottom: 0.6rem;
					border-radius: var(--radius-sm, 0.4rem);
					background: var(--surface-danger-subtle, hsla(0, 84%, 60%, 0.08));
					border: 1px solid var(--color-danger, hsla(0, 84%, 60%, 0.2));
					font-size: 0.7rem;
					color: var(--color-danger, hsla(0, 84%, 60%, 1));
					font-weight: 500;
				}
				.thread-warning .warning-icon { font-size: 0.85rem; }
				.thread-warning .warning-text { line-height: 1.3; }

				.bench-error {
					color: var(--color-danger, hsla(0, 84%, 60%, 1));
					font-size: 0.8rem;
					margin-top: 0.5rem;
				}

				.bench-tps {
					display: baseline;
					gap: 0.3rem;
					margin-bottom: 0.4rem;
					cursor: help;
				}

				.tps-value {
					font-size: 2rem;
					font-weight: 800;
					font-family: var(--font-mono, 'Fira Code', monospace);
					line-height: 1;
				}

				.tps-unit {
					font-size: 0.7rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
					opacity: 0.5;
					font-weight: 600;
				}

				.bench-tps.excellent .tps-value { color: var(--accent-color, hsla(173, 80%, 40%, 1)); }
				.bench-tps.good .tps-value { color: var(--color-success, hsla(142, 69%, 58%, 1)); }
				.bench-tps.moderate .tps-value { color: var(--color-warning, hsla(45, 93%, 47%, 1)); }
				.bench-tps.slow .tps-value { color: var(--color-danger, hsla(0, 84%, 60%, 1)); }

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
					background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.1));
					color: var(--accent-color, hsla(173, 80%, 40%, 1));
					border: 1px solid var(--border-accent, hsla(173, 80%, 40%, 0.2));
				}
				.rating-badge.good {
					background: var(--surface-success-subtle, hsla(142, 69%, 58%, 0.1));
					color: var(--color-success, hsla(142, 69%, 58%, 1));
					border: 1px solid var(--color-success, hsla(142, 69%, 58%, 0.2));
				}
				.rating-badge.moderate {
					background: var(--surface-warning-subtle, hsla(45, 93%, 47%, 0.1));
					color: var(--color-warning, hsla(45, 93%, 47%, 1));
					border: 1px solid var(--color-warning, hsla(45, 93%, 47%, 0.2));
				}
				.rating-badge.slow {
					background: var(--surface-danger-subtle, hsla(0, 84%, 60%, 0.1));
					color: var(--color-danger, hsla(0, 84%, 60%, 1));
					border: 1px solid var(--color-danger, hsla(0, 84%, 60%, 0.2));
				}

				.rating-hint {
					font-size: 0.72rem;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
					opacity: 0.8;
					line-height: 1.4;
					margin-bottom: 0.75rem;
					font-style: italic;
				}

				.bench-details {
					display: grid;
					grid-template-columns: repeat(4, 1fr);
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
					color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
					opacity: 0.6;
					font-weight: 600;
				}

				.detail-value {
					font-size: 0.85rem;
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					opacity: 0.7;
					font-family: var(--font-mono, 'Fira Code', monospace);
				}

				.detail-hint {
					font-size: 0.6rem;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
					opacity: 0.5;
					line-height: 1.35;
					margin-top: 0.15rem;
				}

				.legend-item:focus-visible { outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1)); outline-offset: 2px; border-radius: 2px; }

				/* Light-theme contrast fix — WCAG AA ≥4.5:1
				 * --accent-secondary-text at 65% L works on dark surfaces but fails
				 * on near-white light backgrounds (~#f5f1f1).  Override to 32% L here
				 * so .bench-btn and .bench-tier always achieve ≥8:1 in light mode,
				 * regardless of the user's stored secondary hue.
				 *
				 * IMPORTANT: the media query MUST be guarded with :host-context so the
				 * 32% rule does NOT fire when data-theme="dark" is set on <html>, even
				 * if the OS/browser prefers-color-scheme is still "light" (e.g. Playwright
				 * Desktop Chrome which defaults to system light mode). Without the guard,
				 * the dark-red (#a30000) foreground would render on a dark surface. */
				@media (prefers-color-scheme: light) {
					:host-context(:root:not([data-theme="dark"])) .bench-btn,
					:host-context(:root:not([data-theme="dark"])) .bench-tier {
						color: hsl(var(--accent-secondary-h, 216), 100%, 32%);
					}
					:host-context(:root:not([data-theme="dark"])) .bench-btn:hover,
					:host-context(:root:not([data-theme="dark"])) .bench-btn:focus-visible {
						color: hsl(var(--accent-secondary-h, 216), 100%, 24%);
					}
				}
				:host-context([data-theme="light"]) .bench-btn,
				:host-context([data-theme="light"]) .bench-tier {
					color: hsl(var(--accent-secondary-h, 216), 100%, 32%);
				}
				:host-context([data-theme="light"]) .bench-btn:hover,
				:host-context([data-theme="light"]) .bench-btn:focus-visible {
					color: hsl(var(--accent-secondary-h, 216), 100%, 24%);
				}

				@media (forced-colors: active) {
					.h-icon { background: ButtonFace; border: 1px solid ButtonText; }
					.bench-btn { border: 1px solid Highlight; color: Highlight; }
					.legend-dot { border: 1px solid ButtonText; }
					.rating-badge { border: 1px solid ButtonText; }
					.thread-warning { border-color: LinkText; color: LinkText; }
				}
			</style>

			<h2>
				<span class="h-icon" aria-hidden="true">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
						<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
					</svg>
				</span>
				${this.tr('llm_benchmark', 'Benchmark')}
			</h2>

			<div class="bench-header-bar">
				<div class="bench-actions" aria-actions_for="${this.tr('bench_subtitle', 'Throughput & Performance Rating')}">
					<button class="bench-btn has-tip" id="bench-local" data-tip="${this.tr('tip_bench_local', 'Benchmark the local tier (~0.6B model). Used for quick tasks like greetings and memory distillation.')}" aria-label="${this.tr('bench_local', 'Bench local')}">${this.tr('bench_local', 'Bench local')}</button>
					${this.cloudConfigured ? `<button class="bench-btn has-tip" id="bench-cloud" data-tip="${this.tr('tip_bench_cloud', 'Benchmark the cloud tier. Used for complex analysis and reasoning tasks.')}" aria-label="${this.tr('bench_cloud', 'Bench cloud')}">${this.tr('bench_cloud', 'Bench cloud')}</button>` : ''}
					<button class="bench-btn all has-tip" id="bench-all" data-tip="${this.tr('tip_bench_all', 'Run both tier benchmarks sequentially to get a complete performance picture.')}" aria-label="${this.tr('bench_run_all', 'Run All')}">${this.tr('bench_run_all', 'Run All')}</button>
				</div>
			</div>

			<div class="legend has-tip" data-tip="${this.tr('tip_legend', 'Performance rating scale based on expected throughput for each model size on CPU-only inference with Q4_K_M quantization.')}">
				<span class="legend-item has-tip" data-tip="${this.tr('tip_legend_excellent', 'Fast real-time conversation. No noticeable delay between tokens.')}" tabindex="0"><span class="legend-dot excellent"></span>${this.tr('excellent', 'Excellent')}</span>
				<span class="legend-item has-tip" data-tip="${this.tr('tip_legend_good', 'Comfortable interactive speed with slight streaming visible.')}" tabindex="0"><span class="legend-dot good"></span>${this.tr('good', 'Good')}</span>
				<span class="legend-item has-tip" data-tip="${this.tr('tip_legend_moderate', 'Usable but noticeable word-by-word generation.')}" tabindex="0"><span class="legend-dot moderate"></span>${this.tr('moderate', 'Moderate')}</span>
				<span class="legend-item has-tip" data-tip="${this.tr('tip_legend_slow', 'Below expected. Check SIMD, thread count, or try a smaller model.')}" tabindex="0"><span class="legend-dot slow"></span>${this.tr('slow', 'Slow')}</span>
			</div>

			<div id="bench-results" aria-live="polite" aria-atomic="false" aria-label="${this.tr('aria_benchmark_results', 'Benchmark results')}">
				<div class="empty-state">${this.tr('bench_empty', 'Click a tier button to measure tokens/second.')}</div>
			</div>
		`;

		this.shadowRoot?.querySelector('#bench-local')?.addEventListener('click', () => this.runBenchmark('local'));
		this.shadowRoot?.querySelector('#bench-cloud')?.addEventListener('click', () => this.runBenchmark('cloud'));
		this.shadowRoot?.querySelector('#bench-all')?.addEventListener('click', () => this.runAllBenchmarks());
		this.updateBenchPanel();
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
}

customElements.define('system-benchmark', SystemBenchmark);
