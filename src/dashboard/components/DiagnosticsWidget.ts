import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { GLASS_TOOLTIP_STYLES } from '../services/glassTooltipStyles';
import { STATUS_STYLES } from '../services/statusStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { GOO_STYLES, initGoo } from '../services/gooStyles';


export class DiagnosticsWidget extends HTMLElement {
    private cpuData: any = null;
    private serverData: any = null;
    private systemData: any = null;
    private benchResults: any[] = [];
    private isBenchRunning: boolean = false;
    private t: Record<string, string> = {};
    private _refreshTimer: ReturnType<typeof setInterval> | null = null;
    private _observer: IntersectionObserver | null = null;
    private _visible = false;
    private _onVisChange = () => this._handleVisibilityChange();

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
        this._refreshTimer = setInterval(() => this.fetchAll(), 5_000);
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
            const [cpuRes, serverRes, sysRes] = await Promise.all([
                fetch('/api/dashboard/benchmark/cpu'),
                fetch('/api/dashboard/server-info'),
                fetch('/api/dashboard/system'),
            ]);
            if (cpuRes.ok) this.cpuData = await cpuRes.json();
            if (serverRes.ok) this.serverData = await serverRes.json();
            if (sysRes.ok) this.systemData = await sysRes.json();
            this.updatePanel();
        } catch (e) {
            console.error('Failed to fetch diagnostics info:', e);
        }
    }

    async runBenchmark(tier: string) {
        if (this.isBenchRunning) return;
        this.isBenchRunning = true;
        this.updatePanel(); // Refresh to show running state

        try {
            const res = await fetch(`/api/dashboard/benchmark/llm?tier=${tier}`, { method: 'POST' });
            if (!res.ok) throw new Error('API error');
            const data = await res.json();
            this.benchResults = this.benchResults.filter(r => r.tier !== tier);
            this.benchResults.push(data);
        } catch (e) {
            console.error('Benchmark failed:', e);
        } finally {
            this.isBenchRunning = false;
            this.updatePanel();
        }
    }

    async runAllBenchmarks() {
        const tiers = ['instant', 'standard', 'deep'];
        for (const tier of tiers) {
            await this.runBenchmark(tier);
        }
    }

    private getRating(tps: number, tier: string): { cls: string; icon: string; label: string; hint: string } {
        const exp = DiagnosticsWidget.EXPECTATIONS[tier] || DiagnosticsWidget.EXPECTATIONS['standard'];
        if (tps >= exp.fast) return { cls: 'excellent', icon: '🚀', label: this.tr('excellent', 'Excellent'), hint: `Fast. ${exp.model} running well.` };
        if (tps >= exp.good) return { cls: 'good', icon: '✅', label: this.tr('good', 'Good'), hint: `Interactive. Typical for ${exp.model}.` };
        if (tps >= exp.ok) return { cls: 'moderate', icon: '⚠️', label: this.tr('moderate', 'Moderate'), hint: `Noticeable latency.` };
        return { cls: 'slow', icon: '🐌', label: this.tr('slow', 'Slow'), hint: `Below expected for ${exp.model}.` };
    }

    updatePanel() {
        const el = this.shadowRoot?.querySelector('#diag-panel');
        if (!el) return;

        const cpu = this.cpuData || { cpu_model: '...', cores_physical: '?', cores_logical: '?', architecture: '?' };
        const srv = this.serverData || {};
        const sys = this.systemData || {};
        const tiers = srv.tiers || {};

        // 1. Hardware Section
        const ramPct = srv.ram_used_pct || 0;
        const ramBarClass = ramPct > 90 ? 'critical' : ramPct > 75 ? 'warning' : 'healthy';

        // 2. Software Section
        const swServices = [
            { name: 'Intelligence', status: (tiers.instant || {}).status === 'online' || sys.status === 'online' ? 'online' : 'offline', detail: sys.llm_model_short || 'Standard' },
            { name: 'Memory', status: (sys.memory_points || 0) >= 0 ? 'online' : 'offline', detail: `${sys.memory_points || 0} pts` },
            { name: 'Database', status: sys.db_size ? 'online' : 'warning', detail: sys.db_size || '0 MB' },
            { name: 'Cache', status: sys.redis_stats ? 'online' : 'warning', detail: sys.redis_stats || 'offline' },
            { name: 'DNS', status: sys.dns_ok === true ? 'online' : 'warning', detail: sys.dns_detail || 'online' },
        ];

        const swGrid = swServices.map(s => `
			<div class="svc-item">
				<div class="svc-main">
					<span class="svc-dot ${s.status}"></span>
					<span class="svc-name">${s.name}</span>
				</div>
				<span class="svc-detail">${s.detail}</span>
			</div>
		`).join('');

        // 3. Benchmarks Section
        const benchHtml = this.benchResults.length === 0 ? `<div class="empty-state">No benchmark data. Run a test below.</div>` :
            this.benchResults.map(r => {
                const rtg = this.getRating(r.tokens_per_second, r.tier);
                return `
					<div class="bench-res-item">
						<span class="bench-tier">${r.tier}</span>
						<span class="bench-val ${rtg.cls}">${r.tokens_per_second} <small>tok/s</small></span>
						<span class="bench-rtg">${rtg.icon}</span>
					</div>
				`;
            }).join('');

        el.innerHTML = `
			<div class="diag-layout">
				<!-- Left Column: Hardware -->
				<div class="diag-col hardware">
					<div class="diag-section-label">Hardware</div>
					<div class="cpu-info">${cpu.cpu_model}</div>
					<div class="hw-specs">
						<div class="hw-spec"><span>Cores</span><strong>${cpu.cores_physical}P/${cpu.cores_logical}L</strong></div>
						<div class="hw-spec"><span>Arch</span><strong>${cpu.architecture}</strong></div>
						<div class="hw-spec"><span>Uptime</span><strong>${srv.uptime_human || '?'}</strong></div>
					</div>
					<div class="ram-box">
						<div class="ram-header"><span>RAM Usage</span><span>${srv.ram_total_gb}GB</span></div>
						<div class="ram-bar"><div class="ram-fill ${ramBarClass}" style="width:${ramPct}%"></div></div>
						<div class="ram-footer"><span>${ramPct}% used</span></div>
					</div>
				</div>

				<!-- Middle Column: Software -->
				<div class="diag-col software">
					<div class="diag-section-label">Software Services</div>
					<div class="svc-grid">${swGrid}</div>
					<div class="intel-summary">
						<div class="itl-item"><span>Inst</span><strong>0.6B</strong></div>
						<div class="itl-item"><span>Std</span><strong>8B-Q2</strong></div>
						<div class="itl-item"><span>Deep</span><strong>8B-Q4</strong></div>
					</div>
				</div>

				<!-- Right Column: Benchmarks -->
				<div class="diag-col benchmarks">
					<div class="diag-section-label">LLM Performance</div>
					<div class="bench-results-list">${benchHtml}</div>
					<div class="bench-actions">
						<button class="b-btn ${this.isBenchRunning ? 'running' : ''}" data-tier="all">Benchmark All</button>
						<div class="b-row">
							<button class="b-btn sm" data-tier="instant">Inst</button>
							<button class="b-btn sm" data-tier="standard">Std</button>
							<button class="b-btn sm" data-tier="deep">Deep</button>
						</div>
					</div>
				</div>
			</div>
		`;

        this.shadowRoot?.querySelector('button[data-tier="all"]')?.addEventListener('click', () => this.runAllBenchmarks());
        this.shadowRoot?.querySelectorAll('button.sm').forEach(b => {
            b.addEventListener('click', () => this.runBenchmark(b.getAttribute('data-tier')!));
        });
        this.injectTooltips();
    }

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

				.h-icon { background: linear-gradient(135deg, var(--accent-color) 0%, var(--accent-secondary) 100%); }

				.diag-layout {
					display: grid;
					grid-template-columns: 1.2fr 1fr 1fr;
					gap: 1.5rem;
					min-height: 280px;
				}

				.diag-col {
					display: flex;
					flex-direction: column;
					gap: 1rem;
				}

				.diag-section-label {
					font-size: 0.65rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
					font-weight: 700;
					margin-bottom: 0.25rem;
				}

				/* Hardware Styles */
				.cpu-info { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); font-family: var(--font-mono); }
				.hw-specs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; }
				.hw-spec { display: flex; flex-direction: column; font-size: 0.7rem; }
				.hw-spec span { color: var(--text-muted); font-size: 0.6rem; text-transform: uppercase; }
				.hw-spec strong { color: var(--text-secondary); font-family: var(--font-mono); }

				.ram-box { background: hsla(0, 0%, 100%, 0.02); padding: 0.75rem; border-radius: 0.5rem; border: 1px solid hsla(0, 0%, 100%, 0.05); }
				.ram-header { display: flex; justify-content: space-between; font-size: 0.7rem; margin-bottom: 0.4rem; color: var(--text-secondary); }
				.ram-bar { height: 6px; background: hsla(0, 0%, 100%, 0.05); border-radius: 3px; overflow: hidden; }
				.ram-fill { height: 100%; transition: width 0.5s; }
				.ram-fill.healthy { background: var(--accent-primary); }
				.ram-fill.warning { background: var(--status-warning); }
				.ram-fill.critical { background: var(--status-danger); }
				.ram-footer { font-size: 0.6rem; color: var(--text-muted); margin-top: 0.3rem; }

				/* Software Styles */
				.svc-grid { display: flex; flex-direction: column; gap: 0.4rem; }
				.svc-item { display: flex; justify-content: space-between; align-items: center; padding: 0.4rem 0.6rem; background: hsla(0, 0%, 100%, 0.02); border-radius: 0.4rem; border: 1px solid hsla(0, 0%, 100%, 0.04); }
				.svc-main { display: flex; align-items: center; gap: 0.5rem; }
				.svc-dot { width: 8px; height: 8px; border-radius: 50%; }
				.svc-dot.online { background: var(--accent-primary); box-shadow: 0 0 6px var(--accent-primary); }
				.svc-dot.warning { background: var(--status-warning); }
				.svc-dot.offline { background: var(--status-danger); }
				.svc-name { font-size: 0.7rem; font-weight: 600; color: var(--text-secondary); }
				.svc-detail { font-size: 0.65rem; font-family: var(--font-mono); color: var(--text-muted); }

				.intel-summary { display: flex; justify-content: space-between; gap: 0.4rem; margin-top: auto; }
				.itl-item { flex: 1; display: flex; flex-direction: column; align-items: center; padding: 0.4rem; background: hsla(0, 0%, 100%, 0.01); border: 1px solid hsla(0, 0%, 100%, 0.03); border-radius: 0.3rem; }
				.itl-item span { font-size: 0.55rem; color: var(--text-muted); text-transform: uppercase; }
				.itl-item strong { font-size: 0.7rem; color: var(--text-muted); opacity: 0.8; }

				/* Benchmark Styles */
				.bench-results-list { display: flex; flex-direction: column; gap: 0.5rem; }
				.bench-res-item { display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.75rem; background: hsla(0, 0%, 100%, 0.02); border-radius: 0.4rem; border: 1px solid hsla(0, 0%, 100%, 0.04); }
				.bench-tier { font-size: 0.6rem; text-transform: uppercase; font-weight: 700; color: var(--accent-secondary-text, hsl(216, 100%, 65%)); font-family: var(--font-mono); width: 60px; }
				.bench-val { font-size: 1rem; font-weight: 800; font-family: var(--font-mono); flex: 1; text-align: right; margin-right: 0.75rem; }
				.bench-val small { font-size: 0.6rem; opacity: 0.5; font-weight: 400; }
				.bench-val.excellent { color: var(--accent-color); }
				.bench-val.good { color: var(--status-success); }
				.bench-val.moderate { color: var(--status-warning); }
				.bench-val.slow { color: var(--status-danger); }
				.bench-rtg { font-size: 1rem; }

				.bench-actions { display: flex; flex-direction: column; gap: 0.4rem; margin-top: auto; }
				.b-btn { background: hsla(0, 0%, 100%, 0.05); color: var(--text-primary); border: 1px solid hsla(0, 0%, 100%, 0.1); padding: 0.5rem; border-radius: 0.4rem; font-size: 0.7rem; font-weight: 700; cursor: pointer; transition: all 0.2s; text-transform: uppercase; }
				.b-btn:hover { background: hsla(0, 0%, 100%, 0.1); border-color: var(--accent-color); }
				.b-btn.running { opacity: 0.6; animation: diag-pulse 1.5s infinite; pointer-events: none; }
				.b-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.4rem; }
				.b-btn.sm { font-size: 0.6rem; padding: 0.35rem; }

				@keyframes diag-pulse { 0%, 100% { opacity: 0.5; } 50% { opacity: 1; } }

				@media (max-width: 1100px) {
					.diag-layout { grid-template-columns: 1fr; }
				}
			</style>

			<h2>
				<span class="h-icon" aria-hidden="true">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
					</svg>
				</span>
				Diagnostics
			</h2>

			<div id="diag-panel" aria-live="polite">
				<div class="empty-state">Loading diagnostics...</div>
			</div>
		`;
    }
}

customElements.define('diagnostics-widget', DiagnosticsWidget);
