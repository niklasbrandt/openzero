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
    private llmConfig: any = null;
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
            const [cpuRes, serverRes, sysRes, llmRes] = await Promise.all([
                fetch('/api/dashboard/benchmark/cpu'),
                fetch('/api/dashboard/server-info'),
                fetch('/api/dashboard/system'),
                fetch('/api/dashboard/llm-config'),
            ]);
            if (cpuRes.ok) this.cpuData = await cpuRes.json();
            if (serverRes.ok) this.serverData = await serverRes.json();
            if (sysRes.ok) this.systemData = await sysRes.json();
            if (llmRes.ok) this.llmConfig = await llmRes.json();
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
        const hasRamBreakdown = srv.ram_apps_gb !== undefined && srv.ram_bufcache_gb !== undefined;
        const appsPct = hasRamBreakdown ? Math.min(srv.ram_apps_pct || 0, 100) : ramPct;
        const cachePct = hasRamBreakdown ? Math.min((srv.ram_bufcache_gb / Math.max(srv.ram_total_gb, 0.1)) * 100, 100 - appsPct) : 0;

        // 2. Software Section
        const swServices = [
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
				<span class="svc-detail">${this.esc(s.detail)}</span>
			</div>
		`).join('');

        const cfgTiers: any[] = (this.llmConfig || {}).tiers || [];
        const modelFor = (name: string) => {
            const t = cfgTiers.find((x: any) => x.tier === name);
            if (t && t.model) {
                const parts = t.model.split('/');
                return parts[parts.length - 1].replace('.gguf', '');
            }
            return name === 'instant' ? 'Qwen3-0.6B' : name === 'standard' ? 'Qwen3-8B' : 'Qwen3-14B';
        };

        const tierNames = ['instant', 'standard', 'deep'];
        const llmStatusHtml = tierNames.map(name => {
            const td = tiers[name] || {};
            const isOnline = td.status === 'online';
            const isBusy = td.activity === 'processing';
            const model = modelFor(name);
            const dotClass = !isOnline ? 'offline' : isBusy ? 'processing' : 'online';
            return `
                <div class="llm-tier-status ${isBusy ? 'busy' : ''}">
                    <div class="llm-tier-main">
                        <span class="svc-dot ${dotClass}"></span>
                        <span class="llm-tier-label">${name}</span>
                    </div>
                    <span class="llm-tier-info">${this.esc(model)}</span>
                </div>
            `;
        }).join('');

        // 3. Benchmarks Section
        const benchHtml = this.benchResults.length === 0 ? `<div class="empty-state">No benchmark data. Run a test below.</div>` :
            this.benchResults.map(r => {
                if (r.error) {
                    return `
                        <div class="bench-res-item error">
                            <span class="bench-tier">${r.tier}</span>
                            <span class="bench-error">${this.esc(r.error)}</span>
                        </div>
                    `;
                }
                const rtg = this.getRating(r.tokens_per_second, r.tier);
                return `
					<div class="bench-res-item">
						<span class="bench-tier">${r.tier}</span>
						<span class="bench-val ${rtg.cls}">${r.tokens_per_second} <small>tok/s</small></span>
						<span class="bench-label ${rtg.cls}">${rtg.label}</span>
						<span class="bench-rtg">${rtg.icon}</span>
					</div>
				`;
            }).join('');

        el.innerHTML = `
			<div class="diag-layout">
                <!-- Top Row: Prominent RAM -->
                <div class="ram-strip">
                    <div class="ram-strip-header">
                        <span class="ram-title">System Memory (RAM)</span>
                        <span class="ram-value">${srv.ram_used_gb || (ramPct * srv.ram_total_gb / 100).toFixed(1)}GB / ${srv.ram_total_gb}GB</span>
                    </div>
                    <div class="ram-strip-bar">
                        <div class="ram-segment apps" style="width:${appsPct}%" title="Applications & LLMs"></div>
                        <div class="ram-segment cache" style="width:${cachePct}%" title="System Cache & Buffers"></div>
                        <div class="ram-segment free" style="width:${100 - appsPct - cachePct}%" title="Free Memory"></div>
                    </div>
                    <div class="ram-strip-legend">
                        <div class="leg-item"><span class="leg-dot apps"></span> Apps: ${srv.ram_apps_gb || 0}G</div>
                        <div class="leg-item"><span class="leg-dot cache"></span> Cache: ${srv.ram_bufcache_gb || 0}G</div>
                        <div class="leg-item"><span class="leg-dot free"></span> Free: ${(srv.ram_free_gb || 0).toFixed(1)}G</div>
                    </div>
                </div>

				<!-- Left Column: Hardware -->
				<div class="diag-col hardware">
					<div class="diag-section-label">Processor Info</div>
					<div class="cpu-info">${cpu.cpu_model}</div>
					<div class="hw-specs">
						<div class="hw-spec"><span>Cores</span><strong>${cpu.cores_physical}P/${cpu.cores_logical}L</strong></div>
						<div class="hw-spec"><span>Arch</span><strong>${cpu.architecture}</strong></div>
						<div class="hw-spec"><span>Uptime</span><strong>${srv.uptime_human || '?'}</strong></div>
					</div>
				</div>

				<!-- Middle Column: LLM Tiers & Health -->
				<div class="diag-col software">
                    <div class="diag-section-label">LLM Tiers</div>
					<div class="llm-status-list">${llmStatusHtml}</div>

					<div class="diag-section-label" style="margin-top: 0.8rem">Integration Health</div>
					<div class="svc-grid">${swGrid}</div>
				</div>

				<!-- Right Column: Benchmarks -->
				<div class="diag-col benchmarks">
					<div class="diag-section-label">Performance Ratings</div>
					<div class="bench-results-list">${benchHtml}</div>
					<div class="bench-actions">
						<button class="b-btn main ${this.isBenchRunning ? 'running' : ''}" data-tier="all">Full Suite Test</button>
						<div class="b-row">
							<button class="b-btn sm" data-tier="instant">Instant</button>
							<button class="b-btn sm" data-tier="standard">Standard</button>
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

    private esc(str: any): string {
        if (!str) return '';
        const s = String(str);
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
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

				.ram-strip { grid-column: 1 / -1; background: hsla(0, 0%, 100%, 0.03); padding: 1rem; border-radius: 0.6rem; border: 1px solid hsla(0, 0%, 100%, 0.06); margin-bottom: 0.5rem; }
                .ram-strip-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 0.6rem; }
                .ram-title { font-size: 0.75rem; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; }
                .ram-value { font-size: 0.9rem; font-weight: 800; font-family: var(--font-mono); color: var(--accent-primary); }
                .ram-strip-bar { height: 10px; background: hsla(0, 0%, 100%, 0.05); border-radius: 5px; overflow: hidden; display: flex; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); }
                .ram-segment { height: 100%; transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1); }
                .ram-segment.apps { background: linear-gradient(90deg, var(--accent-primary) 0%, var(--accent-secondary) 100%); box-shadow: 0 0 10px hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.3); }
                .ram-segment.cache { background: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.25); }
                .ram-segment.free { background: transparent; }
                .ram-strip-legend { display: flex; gap: 1.5rem; margin-top: 0.6rem; }
                .leg-item { display: flex; align-items: center; gap: 0.4rem; font-size: 0.65rem; color: var(--text-muted); font-weight: 600; }
                .leg-dot { width: 8px; height: 8px; border-radius: 2px; }
                .leg-dot.apps { background: var(--accent-primary); }
                .leg-dot.cache { background: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.4); border: 1px solid hsla(0, 0%, 100%, 0.1); }
                .leg-dot.free { background: transparent; border: 1px solid hsla(0, 0%, 100%, 0.2); }

				/* Hardware Styles */
				.cpu-info { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); font-family: var(--font-mono); margin-bottom: 0.4rem; }
				.hw-specs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; background: hsla(0, 0%, 100%, 0.02); padding: 0.75rem; border-radius: 0.4rem; border: 1px solid hsla(0, 0%, 100%, 0.04); }
				.hw-spec { display: flex; flex-direction: column; font-size: 0.7rem; }
				.hw-spec span { color: var(--text-muted); font-size: 0.6rem; text-transform: uppercase; }
				.hw-spec strong { color: var(--text-secondary); font-family: var(--font-mono); }

				/* Removed old .ram-box, .ram-header, .ram-bar, .ram-fill, .ram-footer styles */

				/* Software Styles */
				.svc-grid { display: flex; flex-direction: column; gap: 0.4rem; }
				.svc-item { display: flex; justify-content: space-between; align-items: center; padding: 0.4rem 0.6rem; background: hsla(0, 0%, 100%, 0.02); border-radius: 0.4rem; border: 1px solid hsla(0, 0%, 100%, 0.04); }
				.svc-main { display: flex; align-items: center; gap: 0.5rem; }
				.svc-dot { width: 8px; height: 8px; border-radius: 50%; }
				.svc-dot.online { background: var(--accent-primary); box-shadow: 0 0 6px var(--accent-primary); }
				.svc-dot.warning { background: var(--status-warning); }
				.svc-dot.offline { background: var(--status-danger); }
				.svc-name { font-size: 0.7rem; font-weight: 600; color: var(--text-secondary); }
				.svc-detail { font-size: 0.65rem; font-family: var(--font-mono); color: var(--text-muted); text-align: right; }

                .llm-status-list { display: flex; flex-direction: column; gap: 0.4rem; }
                .llm-tier-status { display: flex; justify-content: space-between; align-items: center; padding: 0.4rem 0.6rem; background: hsla(0, 0%, 100%, 0.02); border-radius: 0.4rem; border: 1px solid hsla(0, 0%, 100%, 0.04); transition: all 0.3s; }
                .llm-tier-status.busy { background: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.05); border-color: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.2); animation: diag-pulse 2s infinite; }
                .llm-tier-main { display: flex; align-items: center; gap: 0.5rem; }
                .llm-tier-label { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; color: var(--text-secondary); }
                .llm-tier-info { font-size: 0.65rem; font-family: var(--font-mono); color: var(--text-muted); }
                .svc-dot.processing { background: var(--accent-primary); box-shadow: 0 0 10px var(--accent-primary); animation: diag-pulse 1s infinite; }

				/* Benchmark Styles */
				.bench-results-list { display: flex; flex-direction: column; gap: 0.5rem; }
				.bench-res-item { display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.75rem; background: hsla(0, 0%, 100%, 0.02); border-radius: 0.4rem; border: 1px solid hsla(0, 0%, 100%, 0.04); }
				.bench-tier { font-size: 0.6rem; text-transform: uppercase; font-weight: 700; color: var(--accent-secondary-text, hsl(216, 100%, 65%)); font-family: var(--font-mono); width: 60px; }
				.bench-val { font-size: 0.9rem; font-weight: 800; font-family: var(--font-mono); text-align: right; margin-right: 0.5rem; }
				.bench-val small { font-size: 0.6rem; opacity: 0.5; font-weight: 400; }
                .bench-label { font-size: 0.65rem; font-weight: 600; flex: 1; text-align: left; }
				.bench-val.excellent, .bench-label.excellent { color: var(--accent-color); }
				.bench-val.good, .bench-label.good { color: var(--status-success); }
				.bench-val.moderate, .bench-label.moderate { color: var(--status-warning); }
				.bench-val.slow, .bench-label.slow { color: var(--status-danger); }
				.bench-rtg { font-size: 1rem; margin-left: 0.5rem; }
                .bench-res-item.error { background: hsla(0, 90%, 60%, 0.05); border-color: hsla(0, 90%, 60%, 0.1); }
                .bench-error { font-size: 0.65rem; color: var(--status-danger); font-family: var(--font-mono); flex: 1; text-align: right; }

				.bench-actions { display: flex; flex-direction: column; gap: 0.5rem; margin-top: auto; }
				.b-btn { background: hsla(0, 0%, 100%, 0.04); color: var(--text-primary); border: 1px solid hsla(0, 0%, 100%, 0.08); padding: 0.5rem; border-radius: 0.5rem; font-size: 0.65rem; font-weight: 700; cursor: pointer; transition: all 0.2s; text-transform: uppercase; letter-spacing: 0.05em; }
				.b-btn:hover { background: hsla(0, 0%, 100%, 0.08); border-color: var(--accent-color); color: var(--accent-color); }
                .b-btn.main { background: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.1); border-color: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.2); }
				.b-btn.running { opacity: 0.6; animation: diag-pulse 1.5s infinite; pointer-events: none; }
				.b-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.4rem; }
				.b-btn.sm { font-size: 0.55rem; padding: 0.4rem 0.2rem; }

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
