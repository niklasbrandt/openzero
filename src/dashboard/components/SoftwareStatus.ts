export class SoftwareStatus extends HTMLElement {
	private data: any = null;
	private t: Record<string, string> = {};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
		this.loadTranslations().then(() => this.fetchStatus());
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

	async fetchStatus() {
		try {
			const [sysRes, infoRes] = await Promise.all([
				fetch('/api/dashboard/system'),
				fetch('/api/dashboard/server-info'),
			]);
			const sys = sysRes.ok ? await sysRes.json() : {};
			const info = infoRes.ok ? await infoRes.json() : {};
			this.data = { ...sys, ...info };
			this.updatePanel();
		} catch (e) {
			console.error('Failed to fetch software status:', e);
			const el = this.shadowRoot?.querySelector('#sw-panel');
			if (el) el.innerHTML = '<div class="empty">Could not reach backend.</div>';
		}
	}

	updatePanel() {
		const el = this.shadowRoot?.querySelector('#sw-panel');
		if (!el || !this.data) return;
		const d = this.data;
		const tiers = d.tiers || {};

		// Service health grid
		const services = [
			{
				name: 'Backend',
				status: d.status === 'online' ? 'online' : 'offline',
				detail: `Provider: ${d.llm_provider || 'local'}`,
				tip: 'FastAPI backend serving dashboard, Telegram bot, scheduled tasks, and LLM routing.',
			},
			{
				name: 'LLM Instant',
				status: (tiers.instant || {}).status === 'ok' || (tiers.instant || {}).status === 'online' || (tiers.instant || {}).status === 'no slot available' ? 'online' : 'offline',
				detail: d.llm_provider === 'local' ? `${(tiers.instant || {}).threads || '?'}T` : 'cloud',
				tip: 'llama-server instance for fast, trivial queries (phi-4-mini). Used for greetings, confirmations, memory distillation.',
			},
			{
				name: 'LLM Standard',
				status: (tiers.standard || {}).status === 'ok' || (tiers.standard || {}).status === 'online' || (tiers.standard || {}).status === 'no slot available' ? 'online' : 'offline',
				detail: d.llm_provider === 'local' ? `${(tiers.standard || {}).threads || '?'}T` : 'cloud',
				tip: 'llama-server instance for normal conversation and tool-intent (llama3.1:8b). The workhorse tier.',
			},
			{
				name: 'LLM Deep',
				status: (tiers.deep || {}).status === 'ok' || (tiers.deep || {}).status === 'online' || (tiers.deep || {}).status === 'no slot available' ? 'online' : 'offline',
				detail: d.llm_provider === 'local' ? `${(tiers.deep || {}).threads || '?'}T` : 'cloud',
				tip: 'llama-server instance for complex reasoning (qwen2.5:14b). Used for briefings, planning, analysis.',
			},
			{
				name: 'Memory',
				status: (d.memory_points || 0) >= 0 ? 'online' : 'offline',
				detail: `${d.memory_points || 0} pts`,
				tip: 'Qdrant vector database storing semantic long-term memory. Each "point" is an embedded memory fragment.',
			},
			{
				name: 'Identity',
				status: d.identity_active ? 'online' : 'warning',
				detail: d.identity_active ? 'Active' : 'Not set',
				tip: 'Whether a Subject Zero identity profile has been configured. Required for personalized responses.',
			},
		];

		const serviceGrid = services.map(s => `
			<div class="svc-item has-tip" data-tip="${s.tip}" tabindex="0">
				<span class="svc-dot ${s.status}"></span>
				<span class="svc-name">${s.name}</span>
				<span class="svc-detail">${s.detail}</span>
			</div>
		`).join('');

		// Stack summary
		const stackItems = [
			{ label: 'LLM Engine', value: 'llama.cpp', tip: 'Local inference engine running GGUF-quantized models via llama-server.' },
			{ label: 'Model Active', value: d.llm_model || 'unknown', tip: 'The model used for the most recent LLM request.' },
			{ label: 'Memory DB', value: 'Qdrant', tip: 'Vector similarity search for semantic long-term memory.' },
			{ label: 'Task Board', value: 'Planka', tip: 'Kanban project management board for task tracking.' },
		];

		const stackHtml = stackItems.map(s => `
			<div class="stack-item has-tip" data-tip="${s.tip}">
				<span class="stack-label">${s.label}</span>
				<span class="stack-value">${s.value}</span>
			</div>
		`).join('');

		el.innerHTML = `
			<div class="svc-grid">${serviceGrid}</div>
			<div class="stack-section">
				<span class="section-label">${this.tr('stack', 'Stack')}</span>
				<div class="stack-grid">${stackHtml}</div>
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
					background: linear-gradient(135deg, #8b5cf6 0%, #0066FF 100%);
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

				/* ── Tooltip ── */
				.has-tip { position: relative; }
				.has-tip::after {
					content: attr(data-tip);
					position: absolute;
					bottom: calc(100% + 8px);
					left: 50%;
					transform: translateX(-50%);
					background: rgba(10, 12, 28, 0.95);
					color: rgba(255, 255, 255, 0.85);
					font-size: 0.68rem;
					line-height: 1.4;
					padding: 0.5rem 0.65rem;
					border-radius: 0.4rem;
					border: 1px solid rgba(255, 255, 255, 0.1);
					white-space: normal;
					width: max-content;
					max-width: 260px;
					pointer-events: none;
					opacity: 0;
					transition: opacity 0.15s ease;
					z-index: 100;
					box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
				}
				.has-tip:hover::after,
				.has-tip:focus-visible::after { opacity: 1; }

				/* ── Service Grid ── */
				.svc-grid {
					display: grid;
					grid-template-columns: repeat(3, 1fr);
					gap: 0.5rem;
					margin-bottom: 1.25rem;
				}
				.svc-item {
					display: flex;
					align-items: center;
					gap: 0.4rem;
					padding: 0.5rem 0.65rem;
					background: rgba(255, 255, 255, 0.02);
					border: 1px solid rgba(255, 255, 255, 0.04);
					border-radius: 0.4rem;
					cursor: help;
				}
				.svc-dot {
					width: 7px;
					height: 7px;
					border-radius: 50%;
					flex-shrink: 0;
				}
				.svc-dot.online { background: #14B8A6; box-shadow: 0 0 6px rgba(20, 184, 166, 0.4); }
				.svc-dot.offline { background: #ef4444; box-shadow: 0 0 6px rgba(239, 68, 68, 0.4); }
				.svc-dot.warning { background: #eab308; box-shadow: 0 0 6px rgba(234, 179, 8, 0.4); }
				.svc-name {
					font-size: 0.7rem;
					font-weight: 600;
					color: rgba(255, 255, 255, 0.8);
					white-space: nowrap;
				}
				.svc-detail {
					font-size: 0.65rem;
					color: rgba(255, 255, 255, 0.35);
					font-family: 'Fira Code', monospace;
					margin-left: auto;
					white-space: nowrap;
				}

				/* ── Stack Section ── */
				.section-label {
					font-size: 0.65rem;
					text-transform: uppercase;
					letter-spacing: 0.1em;
					color: rgba(255, 255, 255, 0.3);
					font-weight: 600;
					display: block;
					margin-bottom: 0.5rem;
				}
				.stack-grid {
					display: grid;
					grid-template-columns: repeat(2, 1fr);
					gap: 0.5rem;
				}
				.stack-item {
					display: flex;
					flex-direction: column;
					gap: 0.15rem;
					cursor: help;
				}
				.stack-label {
					font-size: 0.6rem;
					text-transform: uppercase;
					letter-spacing: 0.08em;
					color: rgba(255, 255, 255, 0.25);
					font-weight: 600;
				}
				.stack-value {
					font-size: 0.82rem;
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
						<polyline points="16 18 22 12 16 6"></polyline>
						<polyline points="8 6 2 12 8 18"></polyline>
					</svg>
				</span>
				${this.tr('software', 'Software')}
				<span class="subtitle">${this.tr('sw_subtitle', 'Services &amp; Stack')}</span>
			</h2>

			<div id="sw-panel">
				<div class="empty">${this.tr('loading_sw', 'Loading services...')}</div>
			</div>
		`;
	}
}

customElements.define('software-status', SoftwareStatus);
