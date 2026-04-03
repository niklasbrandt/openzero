import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { GLASS_TOOLTIP_STYLES } from '../services/glassTooltipStyles';
import { STATUS_STYLES } from '../services/statusStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { GOO_STYLES, initGoo } from '../services/gooStyles';


export class DiagnosticsWidget extends HTMLElement {
	private cpuData: Record<string, any> | null = null;
	private serverData: Record<string, any> | null = null;
	private systemData: Record<string, any> | null = null;
	private llmConfig: Record<string, any> | null = null;
	private benchResults: any[] = [];
	private isBenchRunning: boolean = false;
	private _activeInference: Record<string, boolean> = { local: false, cloud: false };
	private t: Record<string, string> = {};
	private _refreshTimer: ReturnType<typeof setInterval> | null = null;
	private _activeTimer: ReturnType<typeof setInterval> | null = null;
	private _observer: IntersectionObserver | null = null;
	private _visible = false;
	private _onVisChange = () => this._handleVisibilityChange();

	private static readonly EXPECTATIONS: Record<string, { model: string; fast: number; good: number; ok: number }> = {
		local: { model: '~0.6B', fast: 20, good: 14, ok: 7 },
		cloud: { model: 'cloud', fast: 40, good: 20, ok: 8 },
	};

	private static readonly HDD_SEG_TIPS: Record<string, string> = {
		// Legacy aggregated key (kept for backward compat with older API responses)
		'docker images': 'Base filesystem layers for all container images pulled from Docker Hub.',
		// Named volume segments
		'models': 'GGUF model files served by the LLM inference servers.',
		'database': 'PostgreSQL data — conversations, email rules, and calendar events.',
		'memory': 'Qdrant vector embeddings for long-term semantic memory retrieval.',
		'project files': 'Planka task board attachments and uploaded files.',
		'build cache': 'Docker build layer cache — safe to prune with docker builder prune.',
		'orphan volumes': 'Docker volumes no longer referenced by any active service.',
		'container layers': 'Files written by running containers (logs, temp files, runtime state) on top of their base images.',
		'tts models': 'Text-to-speech synthesis model files used by the voice service.',
		'redis cache': 'Redis in-memory store snapshot persisted to disk.',
		// Per-image segments (group: docker_image)
		'backend': 'openZero backend image — FastAPI application server and all Python dependencies.',
		'postgres': 'PostgreSQL database server image (data is in the separate Database segment).',
		'qdrant': 'Qdrant vector search engine image (vectors are in the separate Memory segment).',
		'planka': 'Planka kanban board image (attachments are in the separate Project Files segment).',
		'traefik': 'Traefik reverse proxy image — routes all incoming HTTP traffic.',
		'redis': 'Redis in-memory cache image (data is in the separate Redis Cache segment).',
		'whisper': 'Whisper automatic speech recognition image for voice input.',
		'tts': 'Text-to-speech inference image for voice output.',
		'openedai-speech': 'Text-to-speech inference image for voice output.',
		'openai-whisper-asr-webservice': 'Whisper speech-to-text webservice image.',
		'pihole': 'Pi-hole DNS-level ad and tracker blocking server image.',
		'nginx': 'Nginx HTTP server image (used for error pages).',
		'llama.cpp': 'llama.cpp inference server image — used by the local LLM tier.',
		'other images': 'Smaller Docker images not shown individually (each under 70 MB).',
		'untagged': 'Untagged or dangling image layers with no associated tag.',
		// Catch-all
		'other': 'Host OS packages, system logs, user files, and all data outside Docker\'s managed storage. Requires direct host filesystem access to sub-divide further.',
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
		this._refreshTimer = setInterval(() => this.fetchAll(), 8000);
		if (!this._activeTimer) {
			this._activeTimer = setInterval(() => this._fetchActiveInference(), 2000);
		}
	}

	private _stopPolling() {
		if (this._refreshTimer) {
			clearInterval(this._refreshTimer);
			this._refreshTimer = null;
		}
		if (this._activeTimer) {
			clearInterval(this._activeTimer);
			this._activeTimer = null;
		}
	}

	private async _fetchActiveInference() {
		try {
			const r = await fetch('/api/dashboard/llm-active');
			if (!r.ok) return;
			const data = await r.json();
			const changed =
				this._activeInference.local !== !!data.local ||
				this._activeInference.cloud !== !!data.cloud;
			this._activeInference = { local: !!data.local, cloud: !!data.cloud };
			if (changed) this._updateInferringState();
		} catch { /* silent */ }
	}

	private _updateInferringState() {
		const root = this.shadowRoot;
		if (!root) return;
		for (const tier of ['local', 'cloud'] as const) {
			root.querySelectorAll<HTMLElement>(`.llm-tier-card[data-tier="${tier}"]`).forEach(card => {
				card.classList.toggle('inferring', this._activeInference[tier]);
			});
		}
	}

	private async loadTranslations() {
		if (window.__z_translations) { this.t = window.__z_translations; return; }
		try {
			const r = await fetch('/api/dashboard/translations');
			if (r.ok) this.t = await r.json();
		} catch (e) { console.error('Failed to load translations', e); }
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] || fallback;
	}

	async fetchAll() {
		const safeFetch = (url: string) =>
			fetch(url)
				.then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); })
				.catch((e: Error) => { console.warn(`DiagnosticsWidget: ${url} failed (${e.message})`); return null; });

		const [cpu, srv, sys, cfg] = await Promise.all([
			safeFetch('/api/dashboard/benchmark/cpu'),
			safeFetch('/api/dashboard/server-info'),
			safeFetch('/api/dashboard/system'),
			safeFetch('/api/dashboard/llm-config'),
		]);
		if (cpu !== null) this.cpuData = cpu;
		if (srv !== null) this.serverData = srv;
		if (sys !== null) this.systemData = sys;
		if (cfg !== null) this.llmConfig = cfg;
		this.updatePanel();
	}

	private async _runBenchmarkCore(tier: string) {
		const r = await fetch(`/api/dashboard/benchmark/llm?tier=${encodeURIComponent(tier)}`, {
			method: 'POST',
		});
		let res: any;
		if (!r.ok) {
			res = { tier, error: `HTTP ${r.status}` };
		} else {
			res = await r.json();
		}
		const idx = this.benchResults.findIndex(b => b.tier === tier);
		if (idx > -1) this.benchResults[idx] = res;
		else this.benchResults.push(res);
	}

	async runBenchmark(tier: string) {
		if (this.isBenchRunning) return;
		this.isBenchRunning = true;
		this.updatePanel();
		try {
			await this._runBenchmarkCore(tier);
		} catch (e) {
			console.error('Benchmark failed:', e);
		} finally {
			this.isBenchRunning = false;
			this.updatePanel();
		}
	}

	async runAllBenchmarks() {
		if (this.isBenchRunning) return;
		this.isBenchRunning = true;
		this.updatePanel();
		try {
			for (const tier of ['local', 'cloud']) {
				await this._runBenchmarkCore(tier);
				this.updatePanel();
			}
		} catch (e) {
			console.error('All benchmarks failed:', e);
		} finally {
			this.isBenchRunning = false;
			this.updatePanel();
		}
	}

	private displayTier(tier: string): string {
		return tier === 'local' ? 'Local' : 'Cloud';
	}

	private getRating(tps: number, tier: string): { cls: string; icon: string; label: string; hint: string } {
		const exp = DiagnosticsWidget.EXPECTATIONS[tier] || DiagnosticsWidget.EXPECTATIONS['local'];
		if (tps >= exp.fast) return { cls: 'excellent', icon: '++', label: this.tr('excellent', 'Excellent'), hint: `${tps.toFixed(1)} tok/s — well above target for ${exp.model}. Responses feel instant.` };
		if (tps >= exp.good) return { cls: 'good', icon: 'ok', label: this.tr('good', 'Good'), hint: `${tps.toFixed(1)} tok/s — comfortable for interactive use with ${exp.model}.` };
		if (tps >= exp.ok) return { cls: 'moderate', icon: '!', label: this.tr('moderate', 'Moderate'), hint: `${tps.toFixed(1)} tok/s — noticeable latency. Check thread count and CPU load.` };
		return { cls: 'slow', icon: '--', label: this.tr('slow', 'Slow'), hint: `${tps.toFixed(1)} tok/s — below minimum for ${exp.model}. Possible CPU contention or wrong thread count.` };
	}

	private _svcColor(name: string): string {
		const colors: Record<string, string> = {
			'llm-local': 'var(--accent-primary)',
			'llm-cloud': 'hsl(260,70%,65%)',
			'postgres': 'hsl(140,55%,55%)',
			'qdrant': 'hsl(30,80%,60%)',
			'redis': 'hsl(0,75%,60%)',
			'pihole': 'hsl(10,80%,55%)',
			'dashboard': 'hsl(200,80%,55%)',
			'traefik': 'hsl(190,70%,50%)',
			'planka': 'hsl(210,80%,55%)',
		};
		return colors[name] || 'hsl(220,15%,50%)';
	}

	private _sysProcColor(name: string): string {
		let h = 0;
		for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff;
		const hue = 195 + (h % 55); // 195-250: indigo-blue family, distinct from service colors
		return `hsl(${hue},22%,${42 + (h % 10)}%)`;
	}

	private _ramBarSegments(srv: any): { name: string; label: string; gb: number; pct: number; color: string; orphan?: boolean }[] {
		const total = srv.ram_total_gb || 1;
		const appsGb: number = srv.ram_apps_gb || 0;
		const containerRam: { name: string; gb: number; orphan?: boolean }[] = srv.container_ram || [];

		// Build named segments from live container data
		const segs: { name: string; label: string; gb: number; pct: number; color: string; orphan?: boolean }[] = [];
		let accounted = 0;
		for (const c of containerRam) {
			const isOrphan = c.orphan === true;
			segs.push({
				name: c.name,
				label: c.name,
				gb: c.gb,
				pct: Math.min((c.gb / total) * 100, 100),
				color: isOrphan ? 'hsl(35,90%,58%)' : this._svcColor(c.name),
				orphan: isOrphan,
			});
			accounted += c.gb;
		}

		// Split "other" = apps not in containers into: kernel overhead + system procs
		const otherGb = Math.max(appsGb - accounted, 0);
		const kernelGb: number = parseFloat((srv.ram_kernel_gb || 0).toFixed(2));
		const sysProcGb = Math.max(otherGb - kernelGb, 0);
		if (kernelGb > 0.01) {
			segs.push({
				name: 'kernel',
				label: this.tr('ram_kernel', 'kernel (slab+stacks+ptbl)'),
				gb: kernelGb,
				pct: (kernelGb / total) * 100,
				color: 'hsl(215,30%,48%)'
			});
		}
		const sysprocBreakdown: { name: string; mb: number }[] = srv.ram_sysproc_breakdown || [];
		if (sysprocBreakdown.length > 0) {
			for (const sp of sysprocBreakdown) {
				const spGb = parseFloat((sp.mb / 1024).toFixed(2));
				if (spGb > 0.01) {
					segs.push({
						name: `sys_${sp.name}`,
						label: sp.name,
						gb: spGb,
						pct: (spGb / total) * 100,
						color: this._sysProcColor(sp.name),
					});
				}
			}
		} else if (sysProcGb > 0.05) {
			segs.push({
				name: 'system',
				label: this.tr('ram_sysproc', 'system procs'),
				gb: parseFloat(sysProcGb.toFixed(2)),
				pct: (sysProcGb / total) * 100,
				color: 'hsl(220,18%,42%)'
			});
		}

		// Reclaimable cache (page cache, slab cache, buffers) is intentionally NOT shown as
		// separate segments. The per-container cgroup v2 measurement already includes
		// active_file (mmap'd model weights) which is the same physical pages the kernel
		// counts in its Cached/SReclaimable figures. Adding cache segments on top would
		// double-count ~7-9 GB and make the bar overflow.
		// Instead, the residual "available" segment absorbs all reclaimable pages, so its
		// value equals MemAvailable and aligns with the header's "used = total − MemAvailable".
		const usedBySegs = segs.reduce((sum, s) => sum + s.gb, 0);
		const availGb = parseFloat(Math.max(total - usedBySegs, 0).toFixed(1));
		if (availGb > 0.05) {
			segs.push({ name: 'free', label: this.tr('ram_available', 'available'), gb: availGb, pct: (availGb / total) * 100, color: 'hsla(0,0%,100%,0.04)' });
		}

		// Sort non-available segments by size descending; available always last
		const ramFree = segs.filter(s => s.name === 'free');
		const ramNonFree = segs.filter(s => s.name !== 'free').sort((a, b) => b.gb - a.gb);
		return [...ramNonFree, ...ramFree];
	}

	private _hddBarSegments(srv: any): { name: string; label: string; gb: number; pct: number; color: string; desc?: string }[] {
		const total = srv.disk_total_gb || 1;
		const used = srv.disk_used_gb || 0;
		const free = srv.disk_free_gb || 0;
		// Sort breakdown by gb descending so largest segments appear first
		const breakdown = [...(srv.disk_breakdown || [])].sort((a: any, b: any) => (b.gb || 0) - (a.gb || 0));

		const segs: { name: string; label: string; gb: number; pct: number; color: string; desc?: string }[] = [];
		let accounted = 0;

		for (const item of breakdown) {
			const itemName = item.name.toLowerCase();
			const specificTip = DiagnosticsWidget.HDD_SEG_TIPS[itemName];
			const desc = specificTip
				|| (item.group === 'docker_image' ? `Docker container image for ${item.name}.` : '');
			segs.push({
				name: itemName,
				label: item.name,
				gb: item.gb,
				pct: (item.gb / total) * 100,
				color: item.color || this._svcColor(itemName),
				desc,
			});
			accounted += item.gb;
		}

		const otherGb = Math.max(used - accounted, 0);
		if (otherGb > 0.1) {
			segs.push({
				name: 'other',
				label: this.tr('diag_hdd_other', 'OS & Host Files'),
				gb: parseFloat(otherGb.toFixed(1)),
				pct: (otherGb / total) * 100,
				color: 'hsl(210,40%,62%)',
				desc: DiagnosticsWidget.HDD_SEG_TIPS['other'] || '',
			});
		}

		if (free > 0.1) {
			segs.push({
				name: 'free',
				label: this.tr('diag_hdd_free', 'Free Space'),
				gb: parseFloat(free.toFixed(1)),
				pct: (free / total) * 100,
				color: 'hsla(0,0%,100%,0.04)',
			});
		}

		// Sort non-free segments by size descending; free always last
		const hddFree = segs.filter(s => s.name === 'free');
		const hddNonFree = segs.filter(s => s.name !== 'free').sort((a, b) => b.gb - a.gb);
		return [...hddNonFree, ...hddFree];
	}

	private _ramAlertHtml(srv: any): string {
		const appsPct = srv.ram_apps_pct || 0;
		const usedPct = srv.ram_used_pct || 0;
		const isCritical = appsPct > 85 || usedPct > 92;
		const isWarning = !isCritical && (appsPct > 70 || usedPct > 85);

		// Orphan container warning (separate from pressure alerts)
		const orphans: { name: string; gb: number }[] = (srv.container_ram || []).filter((c: any) => c.orphan);
		const orphanHtml = orphans.length > 0 ? `
			<div class="ram-alert warning" role="alert" aria-live="polite">
				<div class="ram-alert-header">
					<span class="ram-alert-headline">Orphan container${orphans.length > 1 ? 's' : ''} consuming RAM — not in current compose config</span>
				</div>
				<details class="ram-alert-details">
					<summary class="ram-alert-summary"><span class="summary-arrow" aria-hidden="true">&#x25BA;</span> ${orphans.length} orphan${orphans.length > 1 ? 's' : ''}: ${orphans.map(o => `${this.esc(o.name)} (${o.gb}G)`).join(', ')}</summary>
					<ul class="ram-alert-list">
						<li><strong>Stop orphans</strong><span class="ram-alert-detail">SSH to VPS and run: <code>docker compose down --remove-orphans &amp;&amp; docker compose up -d</code></span></li>
						<li><strong>Or remove individually</strong><span class="ram-alert-detail"><code>docker rm -f ${orphans.map(o => `openzero-${this.esc(o.name)}-1`).join(' ')}</code></span></li>
					</ul>
				</details>
			</div>
		` : '';

		if (!isCritical && !isWarning) return orphanHtml;
		const level = isCritical ? 'critical' : 'warning';
		const headline = isCritical
			? `RAM critically full — ${srv.ram_used_gb || usedPct + '%'} GB used of ${srv.ram_total_gb || '?'} GB`
			: `RAM pressure high — ${srv.ram_used_gb || usedPct + '%'} GB used of ${srv.ram_total_gb || '?'} GB`;
		const mitigations = [
			{ key: 'LLM_LOCAL_CTX', action: 'Reduce context window', detail: 'Lower <code>LLM_LOCAL_CTX</code> in <code>.env</code> (e.g. 4096 or 2048). Each halving frees ~1–2 GB KV cache.' },
			{ key: 'LLM_LOCAL_PREDICT', action: 'Reduce max prediction', detail: 'Lower <code>LLM_LOCAL_PREDICT</code> in <code>.env</code> (e.g. 1024). Less output buffer.' },
			{ key: 'Profile A', action: 'Switch to Profile A (Q2_K local model)', detail: 'Use the low-RAM profile in <code>.env.example</code>. Saves ~2 GB at the cost of some quality.' },
			{ key: 'LLM_LOCAL_BATCH', action: 'Reduce batch size', detail: 'Lower <code>LLM_LOCAL_BATCH</code> to 128 or 64. Less RAM per inference pass.' },
		];
		return `${orphanHtml}
			<div class="ram-alert ${level}" role="alert" aria-live="assertive">
				<div class="ram-alert-header">
					<span class="ram-alert-headline">${this.esc(headline)}</span>
				</div>
				<details class="ram-alert-details">
					<summary class="ram-alert-summary"><span class="summary-arrow" aria-hidden="true">▶</span> Mitigation options</summary>
					<ul class="ram-alert-list">
						${mitigations.map(m => `
							<li>
								<strong>${this.esc(m.action)}</strong>
								<span class="ram-alert-detail">${m.detail}</span>
							</li>
						`).join('')}
					</ul>
				</details>
			</div>
		`;
	}

	private _volumeInventoryHtml(srv: any): string {
		const vols: any[] = srv.docker_volume_inventory || [];
		const bcGb: number = srv.docker_buildcache_gb || 0;
		if (vols.length === 0 && bcGb < 0.05) return '';

		const orphans = vols.filter(v => v.orphan && v.gb > 0);
		const active = vols.filter(v => !v.orphan);
		const totalOrphanGb = orphans.reduce((s: number, v: any) => s + (v.gb > 0 ? v.gb : 0), 0);

		const volRow = (v: any): string => {
			const gbLabel = v.gb >= 0 ? `${v.gb} GB` : '?';
			const chip = v.orphan
				? `<span class="vi-chip vi-chip--orphan">orphan</span>`
				: `<span class="vi-chip vi-chip--active">active</span>`;
			const cmd = v.orphan
				? `<details class="vi-cmd"><summary>${this.tr('vi_cleanup', 'cleanup')}</summary><code>docker volume rm openzero_${this.esc(v.name)}</code></details>`
				: '';
			return `
				<div class="vi-row${v.orphan ? ' vi-row--orphan' : ''}">
					<span class="vi-name">${this.esc(v.name)}</span>
					${chip}
					<span class="vi-size">${gbLabel}</span>
					${cmd}
				</div>
			`;
		};

		const bcRow = bcGb > 0.05 ? `
			<div class="vi-row vi-row--cache">
				<span class="vi-name">build cache</span>
				<span class="vi-chip vi-chip--cache">${this.tr('vi_reclaimable', 'reclaimable')}</span>
				<span class="vi-size">${bcGb} GB</span>
				<details class="vi-cmd"><summary>${this.tr('vi_cleanup', 'cleanup')}</summary><code>docker builder prune -a</code></details>
			</div>
		` : '';

		const warnBadge = (orphans.length > 0 || bcGb > 0.5)
			? `<span class="vol-inv-warn">${orphans.length > 0 ? `${orphans.length} orphan${orphans.length > 1 ? 's' : ''} · ${totalOrphanGb.toFixed(1)} GB` : ''}${orphans.length > 0 && bcGb > 0.5 ? ' · ' : ''}${bcGb > 0.5 ? `cache ${bcGb} GB` : ''}</span>`
			: '';

		return `
			<details class="vol-inventory" aria-label="${this.tr('aria_vol_inventory', 'Volume Inventory')}">
				<summary class="vol-inv-summary">
					<span class="vol-inv-title">${this.tr('diag_vol_title', 'Volume Inventory')}</span>
					<span class="vol-inv-meta">${vols.length} ${this.tr('vi_volumes', 'volumes')} ${warnBadge}</span>
				</summary>
				<div class="vi-table" role="list">
					${bcRow}
					${orphans.map(v => volRow(v)).join('')}
					${active.map(v => volRow(v)).join('')}
				</div>
			</details>
		`;
	}

	updatePanel() {
		const el = this.shadowRoot?.querySelector('#diag-panel');
		if (!el) return;

		// Preserve open state of the mitigation details panel across re-renders
		const alertDetailsOpen = (el.querySelector('.ram-alert-details') as HTMLDetailsElement | null)?.open ?? false;

		const cpu = this.cpuData || { cpu_model: '...', cores_physical: '?', cores_logical: '?', architecture: '?' };
		const srv = this.serverData || {};
		const sys = this.systemData || {};
		const tiers = srv.tiers || {};

		const cpuFeats = [
			{ id: 'avx2', label: 'AVX2' },
			{ id: 'avx512', label: 'AVX512' },
			{ id: 'sse4_2', label: 'SSE4.2' },
		];
		const featGrid = cpuFeats.map(f => `
			<div class="hw-feat has-tip ${cpu[f.id] ? 'active' : 'inactive'}" ${!cpu[f.id] ? 'aria-disabled="true"' : ''}>
				<span class="feat-dot"></span>
				<span class="feat-label">${f.label}</span>
				<span class="glass-tooltip">${f.label} hardware instruction set extension ${cpu[f.id] ? 'is available' : 'is not detected'}.</span>
			</div>
		`).join('');

		const swServices = [
			{ name: 'Memory', status: (sys.memory_points || 0) >= 0 ? 'online' : 'offline', detail: `${sys.memory_points || 0} pts` },
			{ name: 'Database', status: sys.db_size ? 'online' : 'warning', detail: sys.db_size || '0 MB' },
			{ name: 'Cache', status: sys.redis_stats ? 'online' : 'warning', detail: sys.redis_stats || 'offline' },
			{ name: 'DNS', status: sys.dns_ok === true ? 'online' : 'warning', detail: sys.dns_detail || 'online' },
			{ name: 'Crews', status: sys.native_ok === true ? 'online' : 'warning', detail: sys.native_detail || 'offline' },
		];

		const swGrid = swServices.map(s => {
			const tips: Record<string, string> = {
				'Memory': 'Status of the semantic memory vector store (Qdrant).',
				'Database': 'Relational data storage (Postgres) health and size.',
				'Cache': 'Fast transient storage (Redis) for sessions and coordination.',
				'DNS': 'Local privacy-focused DNS resolver (Pi-hole) status.',
				'Crews': 'Native multi-agent orchestration engine status.'
			};
			return `
				<div class="svc-item has-tip">
					<div class="svc-main">
						<span class="svc-dot ${s.status}"></span>
						<span class="svc-name">${s.name}</span>
					</div>
					<span class="svc-detail">${this.esc(s.detail)}</span>
					<span class="glass-tooltip">${tips[s.name] || ''}</span>
				</div>
			`;
		}).join('');

		const cfgTiers: any[] = (this.llmConfig || {}).tiers || [];
		const ramEstFor = (name: string): number => {
			const t = cfgTiers.find((x: any) => x.tier === name);
			return t?.ram_est_gb || 0;
		};

		const tierNames = ['cloud', 'local'];
		const tierColors = ['hsl(260,70%,65%)', 'var(--accent-primary)'];
		const ctxFor = (name: string): number => { const t = cfgTiers.find((x: any) => x.tier === name); return t?.ctx || 0; };
		const threadsFor = (name: string): number => { const t = cfgTiers.find((x: any) => x.tier === name); return t?.threads || 0; };

		const benchHtml = this.benchResults.length === 0 ? `` :
			this.benchResults.map(r => {
				if (r.error || !r.tokens_per_second) {
					const msg = r.error || 'No tokens received — model may be loading or unavailable';
					return `
						<div class="bench-res-item error has-tip">
							<span class="bench-tier">${this.displayTier(r.tier)}</span>
							<span class="bench-error">${this.esc(msg)}</span>
							<span class="glass-tooltip">Click a test button to retry.</span>
						</div>
					`;
				}
				const rtg = this.getRating(r.tokens_per_second, r.tier);
				return `
					<div class="bench-res-item has-tip">
						<span class="bench-tier">${this.displayTier(r.tier)}</span>
						<span class="bench-val ${rtg.cls}">${r.tokens_per_second} <small>tok/s</small></span>
						<span class="bench-label ${rtg.cls}">${rtg.label}</span>
						<span class="bench-rtg">${rtg.icon}</span>
						<span class="glass-tooltip">${rtg.hint}</span>
					</div>
				`;
			}).join('');

		el.innerHTML = `
			<div class="diag-layout">
				<button id="btn-force-reload" class="reload-btn has-tip" 
					aria-label="${this.tr('aria_refresh_diagnostics', 'Force refresh of all diagnostic metrics')}">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
						<path d="M21 2v6h-6"></path><path d="M3 12a9 9 0 0 1 15-6.7L21 8"></path><path d="M3 22v-6h6"></path><path d="M21 12a9 9 0 0 1-15 6.7L3 16"></path>
					</svg>
					<span class="glass-tooltip">${this.tr('aria_refresh_diagnostics', 'Force refresh of all diagnostic metrics')}</span>
				</button>

				${this._ramAlertHtml(srv)}

				${cfgTiers.length > 0 ? `
				<div class="llm-ram-breakdown">
					${tierNames.map((name, idx) => {
						const td = tiers[name] || {};
						const color = tierColors[idx];
						const ramGb = ramEstFor(name);

						// Model identification: Prefer live reporter from /props, then env config, then hardcoded fallback
						let model = td.model_file || '';
						if (!model) {
							const t = cfgTiers.find((x: any) => x.tier === name);
							if (t && t.model) {
								const parts = t.model.split('/');
								model = parts[parts.length - 1].replace('.gguf', '');
							}
						}
						if (!model) {
							const cfgTier = cfgTiers.find((x: any) => x.tier === name);
							if (name === 'local') {
								model = cfgTier?.model || 'Qwen3-0.6B';
							} else {
								model = cfgTier?.cloud_configured ? (cfgTier?.model || 'Connected') : 'Not configured';
							}
						}

						const ctx = ctxFor(name);
						const threads = threadsFor(name);
						const liveRamGb = ((srv.container_ram || []).find((c: any) => c.name === 'llm-' + name) || {}).gb || 0;
						
						// Enhanced metadata from tier data (td)
						const fileSizeGb = td.model_size_gb || 0;
						const cacheRamMb = td.cache_ram_mb || 0;
						const kvUsage = td.kv_usage_pct || 0;

						// Mitigation: Detect hidden large models
						// Accounting for the configured prompt cache to avoid false positives.
						// Mismatch if live RAM > (Estimated Weights + Cache RAM + 1GB buffer) * 1.5
						const cacheGb = cacheRamMb / 1024;
						const isMismatch = (liveRamGb > 0 && ramGb > 0 && (liveRamGb / (ramGb + cacheGb + 1.0)) > 1.3);
						
						const mismatchDesc = this.tr('diag_llm_mismatch_desc', 'CRITICAL: Live RAM usage ({live} GB) is significantly higher than expected ({est} GB + {cache} GB cache). This suggests a larger model is hiding under a smaller filename.').replace('{live}', liveRamGb.toFixed(1)).replace('{est}', ramGb.toFixed(1)).replace('{cache}', cacheGb.toFixed(1));
						
						return `<div class="llm-tier-card" style="--tier-color:${color}" data-tier="${name}">
							<div class="ltc-header">
								<span class="ltc-name" style="color:${color}">${this.displayTier(name)}</span>
								${isMismatch ? `<span class="ltc-badge mismatch has-tip">${this.tr('diag_llm_mismatch', 'MISMATCH')}
									<span class="glass-tooltip">${mismatchDesc}</span>
								</span>` : ''}
							</div>
							<div class="ltc-model ${isMismatch ? 'mismatch has-tip' : ''}">
								${isMismatch ? '<span class="ltc-mismatch-icon" aria-hidden="true">⚠️</span>' : ''}
								${this.esc(model)}
								${isMismatch ? `<span class="glass-tooltip">${mismatchDesc}</span>` : ''}
							</div>
							<div class="ltc-specs">
								${fileSizeGb ? `<div class="ltc-spec has-tip"><span>${this.tr('diag_llm_file', 'File')}</span><strong>${fileSizeGb.toFixed(1)} GB</strong><span class="glass-tooltip">${this.tr('diag_llm_file_tip', 'Physical size of the model file on disk.')}</span></div>` : ''}
								${ctx ? `<div class="ltc-spec has-tip"><span>${this.tr('diag_llm_ctx', 'CTX')}</span><strong>${ctx.toLocaleString()}</strong><span class="glass-tooltip">${this.tr('diag_llm_ctx_tip', 'Context window — max tokens held in memory per request')}</span></div>` : ''}
								${cacheRamMb ? `<div class="ltc-spec has-tip"><span>${this.tr('diag_llm_prompt_cache', 'Prompt Cache')}</span><strong>${cacheRamMb} MiB <small style="font-weight:400; opacity:0.6; margin-left:0.3rem;">(used ${kvUsage.toFixed(0)}%)</small></strong><span class="glass-tooltip">${this.tr('diag_llm_cache_tip', 'Allocated memory for reuse of earlier prompt parts. Limits RAM growth.')}</span></div>` : ''}
								${threads ? `<div class="ltc-spec has-tip"><span>${this.tr('threads', 'Threads')}</span><strong>${threads}</strong><span class="glass-tooltip">${this.tr('diag_llm_threads_tip', 'CPU threads allocated to this tier')}</span></div>` : ''}
								${(liveRamGb && cacheGb) ? `<div class="ltc-spec has-tip"><span>${this.tr('diag_ram_weights_label', 'RAM weights')}</span><strong>${(liveRamGb - cacheGb).toFixed(1)} GB</strong><span class="glass-tooltip">${this.tr('diag_ram_weights_tip', 'Model weights and compute buffers in RAM, excluding KV cache.')}</span></div>` : ''}
								${liveRamGb ? `<div class="ltc-spec has-tip"><span>${this.tr('diag_ram_live_label', 'RAM live')}</span><strong style="color:${isMismatch ? 'var(--color-danger)' : color}">${liveRamGb.toFixed(1)} GB</strong><span class="glass-tooltip">${this.tr('diag_ram_live_tip', 'Live RAM from Docker stats: Model weights + KV cache + compute buffers')}</span></div>` : ''}
							</div>
						</div>`;
					}).join('')}
				</div>` : ''}

				<!-- Top Row: Prominent RAM -->
				<div class="ram-strip">
					<div class="ram-strip-header">
						<span class="ram-title">${this.tr('diag_ram_title', 'System Memory (RAM)')}</span>
					${(() => {
						const _segs = this._ramBarSegments(srv);
						const _avail = _segs.find(s => s.name === 'free')?.gb || 0;
						const _used = parseFloat(Math.max((srv.ram_total_gb || 0) - _avail, 0).toFixed(1));
						return `<span class="ram-value">${_used}GB / ${srv.ram_total_gb}GB</span>`;
					})()}
					</div>
					<div class="ram-strip-bar" id="ram-seg-bar">
						${this._ramBarSegments(srv).map(s => `
							<div class="ram-seg-svc" style="width:${Math.max(s.pct, 0).toFixed(2)}%;background:${s.color}" data-seg-tip="${this.esc(s.label)}: ${s.gb} GB (${s.pct.toFixed(1)}%)"></div>
						`).join('')}
					</div>
					${(() => {
						return `
							<div class="ram-bar-hover-tip" id="ram-bar-htip" aria-hidden="true" role="tooltip"></div>
							<div class="ram-strip-legend">
								${this._ramBarSegments(srv).filter(s => s.name !== 'free').map(s => `
								<div class="leg-item${s.orphan ? ' leg-item--orphan' : ''}${s.gb >= 0.15 ? ' leg-item--large' : ''}">
										<span class="leg-dot" style="background:${s.color};border-color:${s.color}"></span>
										<span class="leg-name">${this.esc(s.label)}</span>
										<span class="leg-gb">${s.gb}G</span>
										${s.orphan ? `<span class="leg-orphan-chip" title="${this.tr('tip_orphan_container', 'Not in docker-compose.yml — orphaned container')}">orphan</span>` : ''}
									</div>
								`).join('')}
							</div>
						`;
					})()}
				</div>

				<!-- HDD Row: System Storage -->
				<div class="ram-strip hdd-strip">
					<div class="ram-strip-header">
						<span class="ram-title">${this.tr('diag_hdd_title', 'System Storage (HDD)')}</span>
						<span class="ram-value">${srv.disk_used_gb || '0'}GB / ${srv.disk_total_gb || '0'}GB</span>
					</div>
					<div class="ram-strip-bar hdd-strip-bar" id="hdd-seg-bar">
						${this._hddBarSegments(srv).map(s => `
							<div class="ram-seg-svc" style="width:${Math.max(s.pct, 0).toFixed(2)}%;background:${s.color}" data-seg-tip="${this.esc(s.label)}: ${s.gb} GB (${s.pct.toFixed(1)}%)${s.desc ? ' — ' + this.esc(s.desc) : ''}"></div>
						`).join('')}
					</div>
					<div class="ram-bar-hover-tip hdd-bar-hover-tip" id="hdd-bar-htip" aria-hidden="true" role="tooltip"></div>
					${(() => {
						const activeGb = tierNames.reduce((s, n) => s + ramEstFor(n), 0);
						return `
							<div class="ram-strip-legend">
								${this._hddBarSegments(srv).filter(s => s.name !== 'free').map(s => {
									const isModels = s.name === 'models';
									const bloated = isModels && activeGb > 0 && s.gb > activeGb * 1.5;
								const bloatTip = bloated
									? `Models volume is ${s.gb} GB but current tiers only need ~${activeGb.toFixed(1)} GB. Stale files from previous downloads are taking up space.`
									: '';
								const tip = bloatTip || s.desc || '';
								
								return `
								<div class="leg-item${tip ? ' has-tip' : ''}${bloated ? ' leg-item--bloat' : ''}${s.gb >= 0.15 ? ' leg-item--large' : ''}">
											<span class="leg-dot" style="background:${s.color};border-color:${s.color}"></span>
											<span class="leg-name">${this.esc(s.label)}</span>
											<span class="leg-gb">${s.gb}G</span>
											${bloated ? `<span class="leg-bloat-chip">stale</span>` : ''}
											${tip ? `<span class="glass-tooltip">${this.esc(tip)}</span>` : ''}
										</div>
									`;
								}).join('')}
							</div>
						`;
					})()}
				</div>

				${this._volumeInventoryHtml(srv)}

				<!-- Left Column: Hardware -->
				<div class="diag-col hardware">
					<div class="diag-section-label">${this.tr('diag_processor_info', 'Processor Info')}</div>
					<div class="cpu-info">${cpu.cpu_model}</div>
					<div class="hw-specs">
						<div class="hw-spec has-tip"><span>${this.tr('cores', 'Cores')}</span><strong>${cpu.cores_physical}P/${cpu.cores_logical}L</strong><span class="glass-tooltip">${cpu.cores_physical} ${this.tr('tip_cores_physical', 'physical cores')} / ${cpu.cores_logical} ${this.tr('tip_cores_logical', 'logical threads')}.</span></div>
						<div class="hw-spec has-tip"><span>${this.tr('arch', 'Arch')}</span><strong>${cpu.architecture}</strong><span class="glass-tooltip">${this.tr('tip_arch', 'System instruction set architecture.')}</span></div>
						<div class="hw-spec has-tip"><span>${this.tr('uptime', 'Uptime')}</span><strong>${srv.uptime_human || '?'}</strong><span class="glass-tooltip">${this.tr('tip_uptime', 'Time since the last system boot.')}</span></div>
					</div>
					<div class="diag-section-label" style="margin-top: 0.5rem">${this.tr('diag_cpu_features', 'CPU Features')}</div>
					<div class="hw-feat-grid">${featGrid}</div>
				</div>

				<!-- Middle Column: Integration -->
				<div class="diag-col software">
					<div class="diag-section-label">${this.tr('diag_integration', 'Integration')}</div>
					<div class="svc-grid">${swGrid}</div>
				</div>

				<!-- Right Column: Benchmark -->
				<div class="diag-col benchmarks">
					<div class="diag-section-label">${this.tr('llm_benchmark', 'Benchmark')}</div>
					<div class="bench-actions" style="margin-top: 0">
						<button class="b-btn main has-tip ${this.isBenchRunning ? 'running' : ''}" ${this.isBenchRunning ? 'disabled' : ''} data-tier="all">
							${this.isBenchRunning ? this.tr('diag_benchmarking', 'Benchmarking...') : this.tr('diag_bench_all', 'Benchmark all LLMs')}
							<span class="glass-tooltip">${this.tr('diag_bench_run_all_tip', 'Run performance tests across all active tiers.')}</span>
						</button>
						<div class="b-row">
							<button class="b-btn sm tier-local has-tip ${this.isBenchRunning ? 'running' : ''}" ${this.isBenchRunning ? 'disabled' : ''} data-tier="local">
								Local
								<span class="glass-tooltip">Test latency of the local tier.</span>
							</button>
							<button class="b-btn sm tier-cloud has-tip ${this.isBenchRunning ? 'running' : ''}" ${this.isBenchRunning ? 'disabled' : ''} data-tier="cloud">
								Cloud
								<span class="glass-tooltip">Test throughput of the cloud tier.</span>
							</button>
						</div>
					</div>
					<div class="bench-results-list" style="margin-top: 0.5rem">${benchHtml}</div>
				</div>
			</div>
		`;

		// Restore details open state after innerHTML replacement
		const alertDetails = el.querySelector('.ram-alert-details') as HTMLDetailsElement | null;
		if (alertDetails && alertDetailsOpen) alertDetails.open = true;

		this.shadowRoot?.querySelector('#btn-force-reload')?.addEventListener('click', (e) => {
			const btn = e.currentTarget as HTMLButtonElement;
			if (btn.classList.contains('spinning')) return;
			btn.classList.add('spinning');
			this.fetchAll().finally(() => setTimeout(() => btn.classList.remove('spinning'), 600));
		});

		this.shadowRoot?.querySelector('button[data-tier="all"]')?.addEventListener('click', () => this.runAllBenchmarks());
		this.shadowRoot?.querySelectorAll('button.sm').forEach(b => {
			b.addEventListener('click', () => this.runBenchmark(b.getAttribute('data-tier')!));
		});

		// Tooltip positioning helper
		const setupBarTooltips = (barId: string, tipId: string, stripSelector: string) => {
			const _bar = el.querySelector(barId) as HTMLElement | null;
			const _htip = el.querySelector(tipId) as HTMLElement | null;
			if (_bar && _htip) {
				_bar.querySelectorAll('.ram-seg-svc').forEach(_seg => {
					_seg.addEventListener('mouseenter', () => {
						const label = _seg.getAttribute('data-seg-tip') || '';
						if (!label) return;
						_htip.textContent = label;
						_htip.classList.add('visible');
					});
					_seg.addEventListener('mouseleave', () => _htip.classList.remove('visible'));
				});
				_bar.addEventListener('mousemove', (e: Event) => {
					const me = e as MouseEvent;
					const stripEl = _bar.closest(stripSelector) as HTMLElement | null;
					if (!stripEl) return;
					const stripRect = stripEl.getBoundingClientRect();
					const barRect = _bar.getBoundingClientRect();
					const x = Math.max(40, Math.min(me.clientX - stripRect.left, stripRect.width - 40));
					const y = barRect.top - stripRect.top - 6;
					_htip.style.left = `${x}px`;
					_htip.style.top = `${y}px`;
				});
				_bar.addEventListener('mouseleave', () => _htip.classList.remove('visible'));
			}
		};

		setupBarTooltips('#ram-seg-bar', '#ram-bar-htip', '.ram-strip:not(.hdd-strip)');
		setupBarTooltips('#hdd-seg-bar', '#hdd-bar-htip', '.hdd-strip');
	}

	private esc(str: any): string {
		if (!str) return '';
		return String(str)
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#x27;');
	}


	render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
			<style>
				:host { display: block; color-scheme: light dark; }
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
					position: relative;
				}

				.reload-btn { position: absolute; top: -38px; right: 0; background: hsla(0,0%,100%,0.05); border: 1px solid hsla(0,0%,100%,0.1); color: var(--text-muted); width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); z-index: 10; padding: 0; }
				.reload-btn:hover { background: hsla(0,0%,100%,0.1); border-color: var(--accent-primary); color: var(--accent-primary); transform: scale(1.1) rotate(15deg); box-shadow: 0 0 15px hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.2); }
				.reload-btn:active { transform: scale(0.9); }
				.reload-btn.spinning svg { animation: diag-rotate 0.8s infinite linear; }
				@keyframes diag-rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

				.diag-col {
					display: flex;
					flex-direction: column;
					gap: 1rem;
				}

				.diag-section-label { font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-muted); margin-bottom: -0.25rem; }

				.cpu-info { font-size: 0.9rem; font-weight: 800; color: var(--text-primary); line-height: 1.2; letter-spacing: -0.01em; }
				.hw-specs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin-top: 0.2rem; }
				.hw-spec { display: flex; flex-direction: column; gap: 2px; }
				.hw-spec span { font-size: 0.55rem; text-transform: uppercase; font-weight: 700; color: var(--text-muted); letter-spacing: 0.05em; }
				.hw-spec strong { font-size: 0.75rem; font-family: var(--font-mono); color: var(--text-secondary); }

				.hw-feat-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.3rem; }
				.hw-feat { display: flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0.6rem; background: hsla(0, 0%, 100%, 0.03); border-radius: 2rem; border: 1px solid hsla(0, 0%, 100%, 0.05); transition: all 0.3s; }
				.hw-feat.inactive { opacity: 0.4; filter: grayscale(1); }
				.hw-feat.active { border-color: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.3); background: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.05); }
				.feat-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--text-muted); }
				.hw-feat.active .feat-dot { background: var(--accent-primary); box-shadow: 0 0 8px var(--accent-primary); }
				.feat-label { font-size: 0.55rem; font-weight: 800; color: var(--text-secondary); }

				.ram-strip { grid-column: 1 / -1; background: hsla(0, 0%, 100%, 0.03); padding: 1rem; border-radius: 0.6rem; border: 1px solid hsla(0, 0%, 100%, 0.06); margin-bottom: 0.5rem; position: relative; }
				.ram-bar-hover-tip { position: absolute; pointer-events: none; opacity: 0; visibility: hidden; transition: opacity 0.12s ease, transform 0.12s ease; background: var(--tooltip-bg, rgba(18,18,28,0.82)); backdrop-filter: blur(28px) saturate(1.5); -webkit-backdrop-filter: blur(28px) saturate(1.5); color: var(--tooltip-text, rgba(255,255,255,0.92)); font-size: 0.7rem; font-weight: 600; letter-spacing: 0.01em; padding: 0.32rem 0.65rem; border-radius: 0.45rem; border: 1px solid var(--tooltip-border, rgba(255,255,255,0.14)); white-space: nowrap; z-index: 200; transform: translateX(-50%) translateY(0); box-shadow: 0 6px 24px rgba(0,0,0,0.45); }
				.ram-bar-hover-tip.visible { opacity: 1; visibility: visible; transform: translateX(-50%) translateY(-4px); }
				.ram-strip-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 0.6rem; }
				.ram-title { font-size: 0.75rem; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; }
				.ram-value { font-size: 0.9rem; font-weight: 800; font-family: var(--font-mono); color: var(--accent-text, var(--accent-primary)); }
				.ram-strip-bar { height: 10px; background: hsla(0, 0%, 100%, 0.05); border-radius: 5px; overflow: hidden; display: flex; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); }
				.ram-seg-svc { height: 100%; transition: width 0.7s cubic-bezier(0.4, 0, 0.2, 1); flex-shrink: 0; }
				.ram-strip-legend { display: flex; flex-wrap: wrap; gap: 0.35rem 1rem; margin-top: 0.6rem; }
				.leg-item { display: flex; align-items: center; gap: 0.35rem; font-size: 0.62rem; color: var(--text-muted); font-weight: 500; }
				.leg-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; border: 1px solid transparent; }
				.leg-name { color: var(--text-muted); }
				.leg-gb { font-family: var(--font-mono); font-size: 0.6rem; color: var(--text-muted); }
				.leg-item--large { font-weight: 600; }
				.leg-item--large .leg-name { color: var(--text-primary, #e2e8f0); font-weight: 700; }
				.leg-item--large .leg-gb { color: var(--text-secondary, #94a3b8); font-weight: 700; }
				.leg-orphan-chip { font-size: 0.52rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: hsl(35,90%,58%); background: hsla(35,90%,58%,0.12); border: 1px solid hsla(35,90%,58%,0.35); border-radius: 3px; padding: 0 0.3rem; line-height: 1.5; }
				.leg-bloat-chip { font-size: 0.52rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: hsl(35,90%,58%); background: hsla(35,90%,58%,0.12); border: 1px solid hsla(35,90%,58%,0.35); border-radius: 3px; padding: 0 0.3rem; line-height: 1.5; margin-left: 0.2rem; }

				.ram-alert { grid-column: 1 / -1; padding: 0.75rem 1rem; border-radius: 0.5rem; border-left: 3px solid; margin-bottom: 0.25rem; }
				.ram-alert.warning { background: hsla(40, 90%, 50%, 0.07); border-color: hsla(40, 90%, 55%, 0.7); }
				.ram-alert.critical { background: hsla(0, 85%, 55%, 0.09); border-color: hsla(0, 85%, 55%, 0.8); }
				.ram-alert-header { display: flex; align-items: center; gap: 0.5rem; }
				.ram-alert-icon { font-size: 0.85rem; }
				.ram-alert.warning .ram-alert-icon { color: hsl(40, 90%, 60%); }
				.ram-alert.critical .ram-alert-icon { color: hsl(0, 85%, 65%); }
				.ram-alert-headline { font-size: 0.75rem; font-weight: 700; }
				.ram-alert.warning .ram-alert-headline { color: hsl(40, 90%, 70%); }
				.ram-alert.critical .ram-alert-headline { color: hsl(0, 85%, 72%); }
				.ram-alert-details { margin-top: 0.4rem; }
				.ram-alert-summary { font-size: 0.65rem; color: var(--text-muted); cursor: pointer; user-select: none; padding: 0.1rem 0; list-style: none; }
				.ram-alert-summary::-webkit-details-marker { display: none; }
				.ram-alert-summary::marker { display: none; }
				.ram-alert-summary .summary-arrow { font-size: 0.5rem; display: inline-block; transition: transform 0.2s; }
				details[open] .ram-alert-summary .summary-arrow { transform: rotate(90deg); }
				.ram-alert-list { margin: 0.5rem 0 0 0.5rem; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 0.5rem; }
				.ram-alert-list li { font-size: 0.65rem; }
				.ram-alert-list li strong { color: var(--text-secondary); display: block; margin-bottom: 0.1rem; }
				.ram-alert-detail { color: var(--text-muted); line-height: 1.5; }
				.ram-alert-detail code { font-family: var(--font-mono); font-size: 0.6rem; background: hsla(0,0%,100%,0.08); padding: 0.05rem 0.3rem; border-radius: 3px; }

				.svc-grid { display: grid; grid-template-columns: 1fr; gap: 0.5rem; }
				.svc-item { display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.75rem; background: hsla(0, 0%, 100%, 0.02); border-radius: 0.4rem; border: 1px solid hsla(0, 0%, 100%, 0.04); transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
				.svc-item:hover { background: hsla(0, 0%, 100%, 0.05); transform: translateX(4px); }
				.svc-main { display: flex; align-items: center; gap: 0.6rem; }
				.svc-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
				.svc-dot.online { background: var(--color-success); box-shadow: 0 0 8px var(--color-success); }
				.svc-dot.warning { background: var(--color-warning); }
				.svc-dot.offline { background: var(--color-danger); }
				.svc-name { font-size: 0.7rem; font-weight: 600; color: var(--text-secondary); }
				.svc-detail { font-size: 0.65rem; font-family: var(--font-mono); color: var(--text-muted); text-align: right; }

				.svc-dot.processing { background: var(--accent-primary); box-shadow: 0 0 10px var(--accent-primary); animation: diag-pulse 1s infinite; }

				.llm-ram-breakdown { margin-bottom: 0.75rem; display: flex; flex-wrap: wrap; gap: 0.6rem; }
				.llm-ram-bd-label { font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); font-weight: 700; margin-bottom: 0.1rem; }
				.llm-tier-card { flex: 1; min-width: 200px; background: hsla(0,0%,100%,0.025); border: 1px solid hsla(0,0%,100%,0.05); border-left: 2px solid var(--tier-color, var(--accent-primary)); border-radius: 0.4rem; padding: 0.45rem 0.6rem; display: flex; flex-direction: column; gap: 0.25rem; }

				@property --llm-spin-angle { syntax: '<angle>'; inherits: false; initial-value: 0deg; }
				@keyframes llm-border-spin { to { --llm-spin-angle: 360deg; } }
				.llm-tier-card.inferring {
					border: 1.5px solid transparent !important;
					background:
						linear-gradient(hsla(0,0%,100%,0.025), hsla(0,0%,100%,0.025)) padding-box,
						conic-gradient(from var(--llm-spin-angle), transparent 78%, var(--tier-color, var(--accent-primary)) 90%, transparent 100%) border-box;
					animation: llm-border-spin 2s linear infinite;
				}
				@media (prefers-reduced-motion: reduce) { .llm-tier-card.inferring { animation: none; border-color: var(--tier-color, var(--accent-primary)) !important; } }
				.ltc-header { display: flex; align-items: center; gap: 0.4rem; }
				.ltc-name { font-size: 0.6rem; font-weight: 900; text-transform: uppercase; letter-spacing: 0.07em; }
				.ltc-status { font-size: 0.5rem; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; margin-left: auto; }
				.ltc-status.online { color: var(--accent-primary); }
				.ltc-status.processing { color: var(--accent-primary); animation: diag-pulse 1s infinite; }
				.ltc-status.offline { color: var(--color-danger); }
				.ltc-badge { font-size: 0.5rem; font-weight: 900; letter-spacing: 0.05em; text-transform: uppercase; border-radius: 3px; padding: 0.1rem 0.35rem; margin-left: auto; position: relative; }
				.ltc-badge.mismatch { color: #fff; background: var(--color-danger); box-shadow: 0 0 10px hsla(0, 85%, 55%, 0.4); animation: diag-pulse 2s infinite; cursor: help; }
				.ltc-badge .glass-tooltip { right: 0; left: auto; transform: translateY(2px); margin-bottom: 2px; }
				.has-tip:hover > .ltc-badge .glass-tooltip { transform: translateY(-4px); }
				
				.ltc-model { font-size: 0.78rem; font-family: var(--font-mono); color: var(--text-secondary); font-weight: 600; display: flex; align-items: center; gap: 0.4rem; padding: 0.1rem 0; position: relative; width: fit-content; }
				.ltc-model.mismatch { color: var(--color-danger); cursor: help; }
				.ltc-mismatch-icon { color: var(--color-danger); font-size: 0.8rem; animation: diag-pulse 1s infinite; }
				.ltc-specs { display: flex; flex-wrap: wrap; gap: 0.3rem 0.7rem; margin-top: 0.1rem; }
				.ltc-spec { display: flex; align-items: baseline; gap: 0.25rem; }
				.ltc-spec span { font-size: 0.52rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted); }
				.ltc-spec strong { font-size: 0.65rem; font-family: var(--font-mono); font-weight: 800; color: var(--text-secondary); }
				.llm-models-disk { display: flex; justify-content: space-between; align-items: center; font-size: 0.6rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding-top: 0.3rem; border-top: 1px solid hsla(0,0%,100%,0.04); margin-top: 0.1rem; }

				.bench-results-list { display: flex; flex-direction: column; gap: 0.5rem; }
				.bench-res-item { display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.75rem; background: hsla(0, 0%, 100%, 0.02); border-radius: 0.4rem; border: 1px solid hsla(0, 0%, 100%, 0.04); }
				.bench-tier { font-size: 0.6rem; text-transform: uppercase; font-weight: 700; color: var(--accent-secondary-text, hsl(216, 100%, 65%)); font-family: var(--font-mono); width: 60px; }
				.bench-val { font-size: 0.9rem; font-weight: 800; font-family: var(--font-mono); text-align: right; margin-right: 0.5rem; }
				.bench-val small { font-size: 0.6rem; opacity: 0.5; font-weight: 400; }
				.bench-label { font-size: 0.65rem; font-weight: 600; flex: 1; text-align: left; }
				.bench-val.excellent, .bench-label.excellent { color: var(--accent-text, var(--accent-color)); }
				.bench-val.good, .bench-label.good { color: var(--color-success); }
				.bench-val.moderate, .bench-label.moderate { color: var(--color-warning); }
				.bench-val.slow, .bench-label.slow { color: var(--color-danger); }
				.bench-rtg { font-size: 1rem; margin-left: 0.5rem; }
				.bench-res-item.error { background: hsla(0, 90%, 60%, 0.05); border-color: hsla(0, 90%, 60%, 0.1); }
				.bench-error { font-size: 0.65rem; color: var(--color-danger); font-family: var(--font-mono); flex: 1; text-align: right; }

				.bench-actions { display: flex; flex-direction: column; gap: 0.5rem; margin-top: auto; }
				.b-btn { background: var(--surface-card, hsla(0, 0%, 100%, 0.04)); color: var(--text-primary); border: 1px solid var(--border-medium, hsla(0, 0%, 100%, 0.08)); padding: 0.5rem; border-radius: 0.5rem; font-size: 0.65rem; font-weight: 700; cursor: pointer; transition: all 0.2s; text-transform: uppercase; letter-spacing: 0.05em; }
				.b-btn:hover:not(:disabled) { background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.08)); border-color: var(--accent-color); color: var(--accent-text, var(--accent-color)); }
				.b-btn.main { background: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.15); border-color: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.3); color: var(--text-primary); }
				.b-btn.running { opacity: 0.6; animation: diag-pulse 1.5s infinite; pointer-events: none; }
				.b-btn:disabled { opacity: 0.5; cursor: not-allowed; filter: grayscale(100%); }
				.b-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; }
				.b-btn.sm { font-size: 0.55rem; padding: 0.4rem 0.2rem; flex: 1; }
				.b-btn.tier-local { border-color: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.4); color: var(--accent-primary); }
				.b-btn.tier-local:hover:not(:disabled) { background: hsla(var(--accent-primary-h), var(--accent-primary-s), var(--accent-primary-l), 0.12); border-color: var(--accent-primary); color: var(--accent-primary); }
				.b-btn.tier-cloud { border-color: hsla(260,70%,65%,0.4); color: hsl(260,70%,70%); }
				.b-btn.tier-cloud:hover:not(:disabled) { background: hsla(260,70%,65%,0.12); border-color: hsl(260,70%,65%); color: hsl(260,70%,75%); }
			/* Light-theme contrast override: hsl(260,65%,35%) gives ≥8:1 on --surface-bg-light */
			:host-context([data-theme="light"]) .b-btn.tier-cloud { color: hsl(260,65%,35%); border-color: hsla(260,65%,35%,0.5); }
			:host-context([data-theme="light"]) .b-btn.tier-cloud:hover:not(:disabled) { background: hsla(260,65%,35%,0.1); border-color: hsl(260,65%,35%); color: hsl(260,65%,28%); }

				.vol-inventory { grid-column: 1 / -1; background: hsla(0,0%,100%,0.02); border: 1px solid hsla(0,0%,100%,0.06); border-radius: 0.6rem; overflow: hidden; }
				.vol-inv-summary { display: flex; align-items: center; gap: 0.75rem; padding: 0.65rem 1rem; cursor: pointer; user-select: none; list-style: none; }
				.vol-inv-summary::-webkit-details-marker { display: none; }
				.vol-inv-summary::marker { display: none; }
				.vol-inv-summary:hover { background: hsla(0,0%,100%,0.03); }
				.vol-inv-title { font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-secondary); }
				.vol-inv-meta { font-size: 0.6rem; color: var(--text-muted); margin-left: auto; display: flex; align-items: center; gap: 0.4rem; }
				.vol-inv-warn { font-size: 0.58rem; font-weight: 700; color: hsl(35,90%,60%); background: hsla(35,90%,58%,0.12); border: 1px solid hsla(35,90%,58%,0.3); border-radius: 3px; padding: 0.05rem 0.35rem; }
				.vi-table { padding: 0 0.75rem 0.75rem; display: flex; flex-direction: column; gap: 0.25rem; }
				.vi-row { display: grid; grid-template-columns: 1fr auto auto auto; align-items: center; gap: 0.5rem; padding: 0.35rem 0.5rem; border-radius: 0.3rem; background: hsla(0,0%,100%,0.015); border: 1px solid hsla(0,0%,100%,0.03); }
				.vi-row--orphan { background: hsla(35,90%,58%,0.05); border-color: hsla(35,90%,58%,0.15); }
				.vi-row--cache { background: hsla(45,80%,50%,0.05); border-color: hsla(45,80%,50%,0.15); }
				.vi-name { font-size: 0.65rem; font-family: var(--font-mono); color: var(--text-secondary); font-weight: 600; }
				.vi-size { font-size: 0.62rem; font-family: var(--font-mono); color: var(--text-muted); font-weight: 700; text-align: right; min-width: 3.5rem; }
				.vi-chip { font-size: 0.5rem; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase; border-radius: 3px; padding: 0.08rem 0.35rem; }
				.vi-chip--active { color: var(--color-success); background: hsla(140,55%,55%,0.1); border: 1px solid hsla(140,55%,55%,0.25); }
				.vi-chip--orphan { color: hsl(35,90%,60%); background: hsla(35,90%,58%,0.12); border: 1px solid hsla(35,90%,58%,0.35); }
				.vi-chip--cache { color: hsl(45,80%,60%); background: hsla(45,80%,50%,0.12); border: 1px solid hsla(45,80%,50%,0.3); }
				.vi-cmd { grid-column: 1 / -1; }
				.vi-cmd summary { font-size: 0.58rem; color: var(--text-muted); cursor: pointer; padding: 0.2rem 0; }
				.vi-cmd summary:hover { color: var(--text-secondary); }
				.vi-cmd code { display: block; font-size: 0.58rem; font-family: var(--font-mono); background: hsla(0,0%,100%,0.06); padding: 0.3rem 0.5rem; border-radius: 4px; margin-top: 0.2rem; color: var(--text-secondary); word-break: break-all; }

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
