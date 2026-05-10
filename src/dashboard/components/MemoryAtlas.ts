import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { BUTTON_STYLES } from '../services/buttonStyles';
import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';

interface AtlasNode {
	id: string;
	type: string;
	label: string;
	confidence: number;
	last_mentioned_at?: string | null;
}

interface AtlasSpine {
	id: string;
	label: string;
	confidence: number;
}

interface SimNode extends AtlasNode {
	x: number;
	y: number;
	vx: number;
	vy: number;
}

type Lens = 'list' | 'graph' | 'spines';

export class MemoryAtlas extends HTMLElement {
	private t: Record<string, string> = {};
	private currentLens: Lens = 'list';
	private nodes: AtlasNode[] = [];
	private spines: AtlasSpine[] = [];
	private simNodes: SimNode[] = [];
	private animFrameId: number | null = null;
	private dragNode: SimNode | null = null;
	private prefersReducedMotion = false;
	private spineLoaded: Set<string> = new Set();

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
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

	connectedCallback() {
		this.prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		this.loadTranslations().then(() => this.render());
	}

	disconnectedCallback() {
		if (this.animFrameId !== null) {
			cancelAnimationFrame(this.animFrameId);
			this.animFrameId = null;
		}
	}

	private render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
			<style>
				${ACCESSIBILITY_STYLES}
				${SECTION_HEADER_STYLES}
				${BUTTON_STYLES}
				${SCROLLBAR_STYLES}

				:host {
					display: block;
					position: relative;
				}

				#atlas-root {
					display: flex;
					flex-direction: column;
					gap: 1rem;
				}

				/* ── Lens switcher ── */
				#lens-switcher {
					display: flex;
					gap: 0.5rem;
					flex-wrap: wrap;
				}

				#lens-switcher button {
					min-height: 44px;
					min-width: 44px;
					padding: 0.5rem 1.25rem;
					font-size: 0.85rem;
					font-weight: 600;
					border-radius: var(--radius-md, 0.5rem);
					cursor: pointer;
					transition:
						background var(--duration-base, 0.25s),
						border-color var(--duration-base, 0.25s),
						color var(--duration-base, 0.25s);
				}

				#lens-switcher button[aria-selected="true"] {
					background: var(--accent-primary, hsla(173, 80%, 40%, 1));
					color: hsla(0, 0%, 100%, 1);
					border-color: var(--accent-primary, hsla(173, 80%, 40%, 1));
				}

				/* ── Lens panels ── */
				.lens-panel { display: none; }
				.lens-panel.active { display: block; }

				/* ── List lens ── */
				.node-list {
					list-style: none;
					margin: 0;
					padding: 0;
					max-height: 60vh;
					overflow-y: auto;
				}

				.node-item {
					display: flex;
					align-items: center;
					gap: 0.75rem;
					padding: 0.75rem 1rem;
					border-radius: var(--radius-md, 0.5rem);
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
					margin-bottom: 0.5rem;
					cursor: pointer;
					min-height: 44px;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.04));
					transition: background var(--duration-fast, 0.15s);
				}

				.node-item:hover {
					background: var(--surface-hover, hsla(0, 0%, 100%, 0.08));
				}

				.node-item:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
					background: var(--surface-hover, hsla(0, 0%, 100%, 0.08));
				}

				.node-label {
					flex: 1;
					font-size: 0.9rem;
					font-weight: 500;
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}

				.type-badge {
					font-size: 0.7rem;
					font-weight: 600;
					padding: 0.2rem 0.5rem;
					border-radius: 999px;
					background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.12));
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					text-transform: uppercase;
					letter-spacing: 0.05em;
					flex-shrink: 0;
				}

				.confidence-bar-wrap {
					width: 3.5rem;
					flex-shrink: 0;
				}

				.confidence-bar {
					height: 4px;
					border-radius: 2px;
					background: var(--border-subtle, hsla(0, 0%, 100%, 0.12));
					overflow: hidden;
				}

				.confidence-fill {
					height: 100%;
					background: var(--accent-primary, hsla(173, 80%, 40%, 1));
					border-radius: 2px;
					transition: width 0.3s ease;
				}

				.node-meta {
					font-size: 0.7rem;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
					flex-shrink: 0;
				}

				/* ── Graph lens ── */
				.graph-container {
					position: relative;
					width: 100%;
					border-radius: var(--radius-lg, 1rem);
					background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
					overflow: hidden;
				}

				.graph-svg {
					width: 100%;
					height: 420px;
					display: block;
					touch-action: none;
				}

				.graph-node-info {
					padding: 0.75rem 1rem;
					font-size: 0.85rem;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.7));
					border-top: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
					min-height: 44px;
					display: flex;
					align-items: center;
					gap: 0.75rem;
					flex-wrap: wrap;
				}

				/* SVG graph elements */
				.graph-circle {
					cursor: grab;
					stroke: hsla(0, 0%, 100%, 0.15);
					stroke-width: 1.5;
				}

				.graph-circle.selected {
					stroke: var(--accent-primary, hsla(173, 80%, 40%, 1));
					stroke-width: 2.5;
				}

				.graph-circle:focus {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				.graph-label {
					font-size: 11px;
					fill: var(--text-secondary, rgba(255, 255, 255, 0.7));
					pointer-events: none;
					user-select: none;
					text-anchor: middle;
					dominant-baseline: hanging;
				}

				/* ── Spines lens ── */
				.spine-list {
					display: flex;
					flex-direction: column;
					gap: 0.5rem;
				}

				details.spine-item {
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
					border-radius: var(--radius-md, 0.5rem);
					background: var(--surface-card, hsla(0, 0%, 100%, 0.04));
					overflow: hidden;
				}

				details.spine-item summary {
					display: flex;
					align-items: center;
					gap: 0.75rem;
					padding: 0.75rem 1rem;
					cursor: pointer;
					min-height: 44px;
					font-weight: 500;
					font-size: 0.9rem;
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					list-style: none;
					user-select: none;
				}

				details.spine-item summary::-webkit-details-marker { display: none; }

				details.spine-item summary:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: -2px;
				}

				.spine-chevron {
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
					transition: transform var(--duration-fast, 0.15s);
					flex-shrink: 0;
				}

				details.spine-item[open] .spine-chevron {
					transform: rotate(90deg);
				}

				.spine-confidence-chip {
					font-size: 0.7rem;
					font-weight: 600;
					padding: 0.15rem 0.45rem;
					border-radius: 999px;
					background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.12));
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					margin-left: auto;
					flex-shrink: 0;
				}

				.spine-body {
					padding: 0.75rem 1rem 1rem;
					border-top: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.06));
				}

				.spine-summary-text {
					font-size: 0.875rem;
					line-height: 1.6;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.75));
					white-space: pre-wrap;
					margin: 0;
				}

				.spine-loading {
					font-size: 0.8rem;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
					font-style: italic;
					margin: 0;
				}

				/* ── Empty state ── */
				.empty-state {
					padding: 2.5rem 1rem;
					text-align: center;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
					font-size: 0.9rem;
					line-height: 1.5;
				}

				/* ── Loading skeleton ── */
				.loading-line {
					height: 2.75rem;
					border-radius: var(--radius-md, 0.5rem);
					background: var(--surface-card, hsla(0, 0%, 100%, 0.06));
					margin-bottom: 0.5rem;
					animation: shimmer 1.4s ease-in-out infinite;
				}

				@keyframes shimmer {
					0%, 100% { opacity: 0.6; }
					50% { opacity: 1; }
				}

				/* ── ChatPrompt bottom bar ── */
				#chat-prompt-bar {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					padding: 0.75rem 0;
					border-top: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.1));
					margin-top: 1rem;
				}

				#chat-input {
					flex: 1;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.05));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.12));
					border-radius: var(--radius-md, 0.5rem);
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					font-family: inherit;
					font-size: 0.9rem;
					min-height: 44px;
					padding: 0.6rem 1rem;
					outline: none;
					transition: border-color var(--duration-fast, 0.15s);
					box-sizing: border-box;
				}

				#chat-input:focus-visible {
					border-color: var(--accent-primary, hsla(173, 80%, 40%, 1));
				}

				#chat-input::placeholder {
					color: var(--text-faint, hsla(0, 0%, 100%, 0.35));
				}

				#chat-send {
					min-height: 44px;
					min-width: 44px;
					padding: 0.5rem 1rem;
					border-radius: var(--radius-md, 0.5rem);
					font-size: 0.85rem;
					font-weight: 700;
					flex-shrink: 0;
					background: var(--accent-primary, hsla(173, 80%, 40%, 1));
					color: hsla(0, 0%, 100%, 1);
					border: none;
					cursor: pointer;
					transition: opacity var(--duration-fast, 0.15s), transform var(--duration-instant, 0.1s);
				}

				#chat-send:hover { opacity: 0.88; }
				#chat-send:active { transform: scale(0.97); }
				#chat-send:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				/* ── Responsive ── */
				@media (max-width: 768px) {
					.graph-svg { height: 280px; }
				}

				/* ── Reduced motion ── */
				@media (prefers-reduced-motion: reduce) {
					.spine-chevron { transition: none; }
					.confidence-fill { transition: none; }
					#chat-send { transition: none; }
					.loading-line { animation: none; opacity: 0.7; }
					#lens-switcher button { transition: none; }
				}

				/* ── Forced colors ── */
				@media (forced-colors: active) {
					.type-badge {
						forced-color-adjust: none;
						border: 1px solid ButtonText;
					}
					.spine-confidence-chip {
						forced-color-adjust: none;
						border: 1px solid ButtonText;
					}
					.node-item { border-color: ButtonText; }
					details.spine-item { border-color: ButtonText; }
					#chat-input { border-color: ButtonText; }
					#chat-send {
						forced-color-adjust: none;
						background: ButtonText;
						color: ButtonFace;
					}
					.confidence-fill { forced-color-adjust: none; background: ButtonText; }
				}
			</style>

			<div id="atlas-root">
				<h2>
					<span class="h-icon" aria-hidden="true">
						<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3"></circle><line x1="12" y1="3" x2="12" y2="5"></line><line x1="12" y1="19" x2="12" y2="21"></line><line x1="3" y1="12" x2="5" y2="12"></line><line x1="19" y1="12" x2="21" y2="12"></line><line x1="5.64" y1="5.64" x2="7.05" y2="7.05"></line><line x1="16.95" y1="16.95" x2="18.36" y2="18.36"></line><line x1="5.64" y1="18.36" x2="7.05" y2="16.95"></line><line x1="16.95" y1="7.05" x2="18.36" y2="5.64"></line></svg>
					</span>
					${this.tr('atlas_title', 'Memory Atlas')}
				</h2>

				<div
					id="lens-switcher"
					role="tablist"
					aria-label="${this.tr('lens_switcher_label', 'Memory lenses')}"
				>
					<button
						role="tab"
						data-lens="list"
						aria-selected="true"
						aria-controls="lens-list"
						aria-label="${this.tr('aria_lens_list', 'Switch to List lens')}"
					>${this.tr('lens_list', 'List')}</button>
					<button
						role="tab"
						data-lens="graph"
						aria-selected="false"
						aria-controls="lens-graph"
						aria-label="${this.tr('aria_lens_graph', 'Switch to Graph lens')}"
					>${this.tr('lens_graph', 'Graph')}</button>
					<button
						role="tab"
						data-lens="spines"
						aria-selected="false"
						aria-controls="lens-spines"
						aria-label="${this.tr('aria_lens_spines', 'Switch to Spines lens')}"
					>${this.tr('lens_spines', 'Spines')}</button>
				</div>

				<div
					id="lens-list"
					role="tabpanel"
					aria-label="${this.tr('lens_list', 'List')}"
					class="lens-panel active"
				>
					<div class="loading-line"></div>
					<div class="loading-line" style="width:78%;"></div>
					<div class="loading-line" style="width:62%;"></div>
				</div>

				<div
					id="lens-graph"
					role="tabpanel"
					aria-label="${this.tr('lens_graph', 'Graph')}"
					class="lens-panel"
					hidden
				>
					<div class="graph-container">
						<svg
							class="graph-svg"
							aria-label="${this.tr('aria_atlas_graph', 'Memory graph visualization')}"
							role="img"
						></svg>
						<div
							class="graph-node-info"
							aria-live="polite"
							role="status"
							id="graph-node-info"
						><span class="sr-only">&nbsp;</span></div>
					</div>
				</div>

				<div
					id="lens-spines"
					role="tabpanel"
					aria-label="${this.tr('lens_spines', 'Spines')}"
					class="lens-panel"
					hidden
				>
					<div class="loading-line"></div>
					<div class="loading-line" style="width:73%;"></div>
				</div>

				<div id="chat-prompt-bar">
					<input
						type="text"
						id="chat-input"
						placeholder="${this.tr('atlas_chat_placeholder', 'Ask about your memory, or say anything...')}"
						aria-label="${this.tr('aria_chat_input', 'Chat input')}"
						autocomplete="off"
						spellcheck="false"
					/>
					<button
						id="chat-send"
						aria-label="${this.tr('aria_chat_send', 'Send message')}"
					>${this.tr('atlas_chat_send', 'Send')}</button>
				</div>
			</div>
		`;

		this.bindEvents();
		this.loadListLens();
	}

	// ── Event wiring ────────────────────────────────────────────────────────

	private bindEvents() {
		const root = this.shadowRoot!;

		// Lens tab keyboard (ARIA tablist pattern: arrow keys)
		root.querySelectorAll<HTMLButtonElement>('#lens-switcher button').forEach(btn => {
			btn.addEventListener('click', () => {
				this.switchLens(btn.dataset.lens as Lens);
			});
			btn.addEventListener('keydown', (e: KeyboardEvent) => {
				if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
				const btns = Array.from(root.querySelectorAll<HTMLButtonElement>('#lens-switcher button'));
				const idx = btns.indexOf(btn);
				const next = e.key === 'ArrowRight'
					? (idx + 1) % btns.length
					: (idx - 1 + btns.length) % btns.length;
				btns[next].focus();
				btns[next].click();
			});
		});

		// Chat bar
		const chatInput = root.querySelector<HTMLInputElement>('#chat-input');
		const chatSend = root.querySelector<HTMLButtonElement>('#chat-send');
		chatSend?.addEventListener('click', () => this.sendChat());
		chatInput?.addEventListener('keydown', (e: KeyboardEvent) => {
			if (e.key === 'Enter' && !e.shiftKey) {
				e.preventDefault();
				this.sendChat();
			}
		});
	}

	// ── Lens switching ──────────────────────────────────────────────────────

	private async switchLens(lens: Lens) {
		if (this.currentLens === lens) return;
		const root = this.shadowRoot!;

		// Stop any running graph simulation
		if (this.animFrameId !== null) {
			cancelAnimationFrame(this.animFrameId);
			this.animFrameId = null;
		}

		// Update ARIA tabs
		root.querySelectorAll<HTMLButtonElement>('#lens-switcher button').forEach(btn => {
			btn.setAttribute('aria-selected', btn.dataset.lens === lens ? 'true' : 'false');
		});

		// Show/hide panels
		const panelIds: Record<Lens, string> = {
			list: 'lens-list',
			graph: 'lens-graph',
			spines: 'lens-spines',
		};
		(Object.entries(panelIds) as [Lens, string][]).forEach(([l, id]) => {
			const panel = root.getElementById(id);
			if (!panel) return;
			if (l === lens) {
				panel.classList.add('active');
				panel.removeAttribute('hidden');
			} else {
				panel.classList.remove('active');
				panel.setAttribute('hidden', '');
			}
		});

		this.currentLens = lens;

		if (lens === 'list') await this.loadListLens();
		if (lens === 'graph') await this.loadGraphLens();
		if (lens === 'spines') await this.loadSpinesLens();
	}

	// ── List lens ──────────────────────────────────────────────────────────

	private async loadListLens() {
		const panel = this.shadowRoot?.getElementById('lens-list');
		if (!panel) return;

		try {
			const res = await fetch('/api/atlas/nodes?limit=50');
			if (!res.ok) throw new Error('fetch failed');
			this.nodes = await res.json();
		} catch (_) {
			this.nodes = [];
		}

		this.renderListLens(panel);
	}

	private renderListLens(panel: HTMLElement) {
		if (this.nodes.length === 0) {
			panel.innerHTML = `<div class="empty-state" role="status">${this.tr('atlas_no_nodes', 'No memory nodes yet. Start a conversation to grow your Atlas.')}</div>`;
			return;
		}

		const items = this.nodes.map(n => {
			const conf = Math.round((n.confidence || 0) * 100);
			const meta = n.last_mentioned_at ? this.formatDate(n.last_mentioned_at) : '';
			return `<li
				role="listitem"
				class="node-item"
				tabindex="0"
				data-id="${this.esc(n.id)}"
				aria-label="${this.tr('aria_node_item', 'Memory node')}: ${this.esc(n.label)}"
			>
				<span class="node-label">${this.esc(n.label)}</span>
				<span
					class="type-badge"
					aria-label="${this.tr('atlas_node_type', 'Type')}: ${this.esc(n.type)}"
				>${this.esc(n.type)}</span>
				<div
					class="confidence-bar-wrap"
					role="progressbar"
					aria-label="${this.tr('atlas_confidence', 'Confidence')}: ${conf}%"
					aria-valuenow="${conf}"
					aria-valuemin="0"
					aria-valuemax="100"
				>
					<div class="confidence-bar">
						<div class="confidence-fill" style="width:${conf}%"></div>
					</div>
				</div>
				${meta ? `<span class="node-meta">${this.esc(meta)}</span>` : ''}
			</li>`;
		}).join('');

		panel.innerHTML = `<ul
			role="list"
			class="node-list"
			aria-label="${this.tr('atlas_title', 'Memory Atlas')}"
		>${items}</ul>`;

		this.bindListKeys(panel);
	}

	private bindListKeys(panel: HTMLElement) {
		const list = panel.querySelector<HTMLUListElement>('.node-list');
		if (!list) return;

		list.addEventListener('keydown', (e: KeyboardEvent) => {
			const items = Array.from(list.querySelectorAll<HTMLLIElement>('.node-item'));
			const idx = items.indexOf(e.target as HTMLLIElement);
			if (idx < 0) return;

			if (e.key === 'ArrowDown') {
				e.preventDefault();
				items[Math.min(idx + 1, items.length - 1)]?.focus();
			} else if (e.key === 'ArrowUp') {
				e.preventDefault();
				items[Math.max(idx - 1, 0)]?.focus();
			}
		});
	}

	// ── Graph lens ──────────────────────────────────────────────────────────

	private async loadGraphLens() {
		const panel = this.shadowRoot?.getElementById('lens-graph');
		if (!panel) return;

		try {
			const res = await fetch('/api/atlas/nodes?limit=100');
			if (!res.ok) throw new Error('fetch failed');
			this.nodes = await res.json();
		} catch (_) {
			this.nodes = [];
		}

		const svgEl = panel.querySelector<SVGSVGElement>('.graph-svg');
		if (!svgEl) return;

		if (this.nodes.length === 0) {
			const container = panel.querySelector('.graph-container');
			if (container) {
				container.innerHTML = `<div class="empty-state" role="status">${this.tr('atlas_no_nodes', 'No memory nodes yet. Start a conversation to grow your Atlas.')}</div>`;
			}
			return;
		}

		// Derive width: use host width with fallback
		const w = (this.clientWidth || 600);
		const h = this.prefersReducedMotion ? 280 : 420;
		svgEl.style.height = `${h}px`;

		// Initialise simulation nodes
		this.simNodes = this.nodes.map((n, i) => ({
			...n,
			x: this.prefersReducedMotion
				? 30 + (i % 7) * Math.max((w - 60) / 7, 60)
				: w / 2 + (Math.random() - 0.5) * Math.min(w * 0.6, 300),
			y: this.prefersReducedMotion
				? 40 + Math.floor(i / 7) * 70
				: h / 2 + (Math.random() - 0.5) * Math.min(h * 0.6, 200),
			vx: 0,
			vy: 0,
		}));

		this.renderGraphFrame(svgEl, w, h);
		this.bindGraphDrag(svgEl, w, h);
		this.bindGraphKeyboard(svgEl);

		if (!this.prefersReducedMotion) {
			this.startSimulation(svgEl, w, h);
		}
	}

	private renderGraphFrame(svgEl: SVGSVGElement, _w: number, _h: number) {
		const NS = 'http://www.w3.org/2000/svg';
		svgEl.innerHTML = '';

		// Edge group (empty in MA1 — full edges arrive in MA2)
		const edgeGroup = document.createElementNS(NS, 'g');
		svgEl.appendChild(edgeGroup);

		// Node group
		const nodeGroup = document.createElementNS(NS, 'g');
		svgEl.appendChild(nodeGroup);

		this.simNodes.forEach(n => {
			const circle = document.createElementNS(NS, 'circle');
			circle.setAttribute('r', '10');
			circle.setAttribute('cx', String(Math.round(n.x)));
			circle.setAttribute('cy', String(Math.round(n.y)));
			circle.setAttribute('fill', this.nodeColor(n.type));
			circle.setAttribute('class', 'graph-circle');
			circle.setAttribute('role', 'img');
			circle.setAttribute('aria-label', `${n.label} (${n.type})`);
			circle.setAttribute('tabindex', '0');
			circle.setAttribute('data-id', n.id);
			nodeGroup.appendChild(circle);

			const text = document.createElementNS(NS, 'text');
			text.setAttribute('x', String(Math.round(n.x)));
			text.setAttribute('y', String(Math.round(n.y + 15)));
			text.setAttribute('class', 'graph-label');
			text.setAttribute('aria-hidden', 'true');
			text.textContent = n.label.length > 12 ? n.label.slice(0, 11) + '\u2026' : n.label;
			nodeGroup.appendChild(text);
		});
	}

	private startSimulation(svgEl: SVGSVGElement, w: number, h: number) {
		const REPULSION = 900;
		const CENTER_PULL = 0.006;
		const DAMPING = 0.82;
		const MAX_STEPS = 280;
		let step = 0;

		const tick = () => {
			if (step >= MAX_STEPS) {
				this.animFrameId = null;
				return;
			}
			step++;

			// Coulomb repulsion between every node pair
			for (let i = 0; i < this.simNodes.length; i++) {
				for (let j = i + 1; j < this.simNodes.length; j++) {
					const a = this.simNodes[i];
					const b = this.simNodes[j];
					if (a === this.dragNode || b === this.dragNode) continue;
					const dx = b.x - a.x;
					const dy = b.y - a.y;
					const distSq = dx * dx + dy * dy || 1;
					const dist = Math.sqrt(distSq);
					const force = REPULSION / distSq;
					const fx = (dx / dist) * force;
					const fy = (dy / dist) * force;
					a.vx -= fx; a.vy -= fy;
					b.vx += fx; b.vy += fy;
				}
			}

			// Gentle center attraction + damping + integrate
			this.simNodes.forEach(n => {
				if (n === this.dragNode) return;
				n.vx += (w / 2 - n.x) * CENTER_PULL;
				n.vy += (h / 2 - n.y) * CENTER_PULL;
				n.vx *= DAMPING;
				n.vy *= DAMPING;
				n.x += n.vx;
				n.y += n.vy;
				// Clamp inside SVG bounds with 14px padding for the circle radius
				n.x = Math.max(14, Math.min(w - 14, n.x));
				n.y = Math.max(14, Math.min(h - 14, n.y));
			});

			// Update DOM positions
			const circles = svgEl.querySelectorAll<SVGCircleElement>('.graph-circle');
			const labels = svgEl.querySelectorAll<SVGTextElement>('.graph-label');
			this.simNodes.forEach((n, i) => {
				circles[i]?.setAttribute('cx', String(Math.round(n.x)));
				circles[i]?.setAttribute('cy', String(Math.round(n.y)));
				labels[i]?.setAttribute('x', String(Math.round(n.x)));
				labels[i]?.setAttribute('y', String(Math.round(n.y + 15)));
			});

			this.animFrameId = requestAnimationFrame(tick);
		};

		this.animFrameId = requestAnimationFrame(tick);
	}

	private bindGraphDrag(svgEl: SVGSVGElement, w: number, h: number) {
		let isDragging = false;

		svgEl.addEventListener('pointerdown', (e: PointerEvent) => {
			const target = e.target as SVGElement;
			if (!target.classList.contains('graph-circle')) return;
			const id = target.getAttribute('data-id');
			const node = this.simNodes.find(n => n.id === id);
			if (!node) return;
			isDragging = true;
			this.dragNode = node;
			svgEl.setPointerCapture(e.pointerId);
			e.preventDefault();
		});

		svgEl.addEventListener('pointermove', (e: PointerEvent) => {
			if (!isDragging || !this.dragNode) return;
			const rect = svgEl.getBoundingClientRect();
			this.dragNode.x = Math.max(14, Math.min(w - 14, e.clientX - rect.left));
			this.dragNode.y = Math.max(14, Math.min(h - 14, e.clientY - rect.top));
			this.dragNode.vx = 0;
			this.dragNode.vy = 0;

			// Immediate DOM update during drag
			const circles = svgEl.querySelectorAll<SVGCircleElement>('.graph-circle');
			const labels = svgEl.querySelectorAll<SVGTextElement>('.graph-label');
			const idx = this.simNodes.indexOf(this.dragNode);
			if (idx >= 0) {
				circles[idx]?.setAttribute('cx', String(Math.round(this.dragNode.x)));
				circles[idx]?.setAttribute('cy', String(Math.round(this.dragNode.y)));
				labels[idx]?.setAttribute('x', String(Math.round(this.dragNode.x)));
				labels[idx]?.setAttribute('y', String(Math.round(this.dragNode.y + 15)));
			}
		});

		const endDrag = () => {
			isDragging = false;
			this.dragNode = null;
		};
		svgEl.addEventListener('pointerup', endDrag);
		svgEl.addEventListener('pointercancel', endDrag);

		// Click to select node
		svgEl.addEventListener('click', (e: MouseEvent) => {
			const target = e.target as SVGElement;
			if (!target.classList.contains('graph-circle')) return;
			const id = target.getAttribute('data-id');
			const node = this.simNodes.find(n => n.id === id);
			if (node) this.selectGraphNode(node, svgEl);
		});
	}

	private bindGraphKeyboard(svgEl: SVGSVGElement) {
		svgEl.addEventListener('keydown', (e: KeyboardEvent) => {
			const target = e.target as SVGElement;
			if (!target.classList.contains('graph-circle')) return;
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				const id = target.getAttribute('data-id');
				const node = this.simNodes.find(n => n.id === id);
				if (node) this.selectGraphNode(node, svgEl);
			}
		});
	}

	private selectGraphNode(node: SimNode, svgEl: SVGSVGElement) {
		// Highlight selection
		svgEl.querySelectorAll<SVGCircleElement>('.graph-circle').forEach(c => {
			c.classList.toggle('selected', c.getAttribute('data-id') === node.id);
		});

		const info = this.shadowRoot?.getElementById('graph-node-info');
		if (info) {
			const conf = Math.round((node.confidence || 0) * 100);
			info.innerHTML = `
				<span class="type-badge">${this.esc(node.type)}</span>
				<span style="font-weight:600;color:var(--text-primary,hsla(0,0%,100%,1))">${this.esc(node.label)}</span>
				<span style="color:var(--text-faint,hsla(0,0%,100%,0.4));font-size:0.8rem">${conf}% ${this.tr('atlas_confidence', 'Confidence')}</span>
			`;
		}
	}

	private nodeColor(type: string): string {
		const map: Record<string, string> = {
			memory: 'hsla(173, 80%, 40%, 0.85)',
			decision: 'hsla(216, 80%, 60%, 0.85)',
			contradiction: 'hsla(0, 80%, 60%, 0.85)',
			source: 'hsla(270, 60%, 60%, 0.85)',
			instance: 'hsla(45, 80%, 50%, 0.85)',
			person: 'hsla(330, 70%, 60%, 0.85)',
			project: 'hsla(200, 70%, 55%, 0.85)',
		};
		return map[type] ?? 'hsla(173, 40%, 50%, 0.7)';
	}

	// ── Spines lens ────────────────────────────────────────────────────────

	private async loadSpinesLens() {
		const panel = this.shadowRoot?.getElementById('lens-spines');
		if (!panel) return;

		try {
			const res = await fetch('/api/atlas/spines');
			if (!res.ok) throw new Error('fetch failed');
			this.spines = await res.json();
		} catch (_) {
			this.spines = [];
		}

		this.renderSpinesLens(panel);
	}

	private renderSpinesLens(panel: HTMLElement) {
		if (this.spines.length === 0) {
			panel.innerHTML = `<div class="empty-state" role="status">${this.tr('atlas_no_spines', 'No topic spines yet. The substrate will generate them as memory grows.')}</div>`;
			return;
		}

		const items = this.spines.map(s => {
			const conf = Math.round((s.confidence || 0) * 100);
			return `<details
				class="spine-item"
				data-id="${this.esc(s.id)}"
				aria-label="${this.tr('aria_spine_section', 'Topic spine')}: ${this.esc(s.label)}"
			>
				<summary>
					<svg class="spine-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><polyline points="9 18 15 12 9 6"></polyline></svg>
					<span>${this.esc(s.label)}</span>
					<span class="spine-confidence-chip" aria-label="${this.tr('atlas_confidence', 'Confidence')}: ${conf}%">${conf}%</span>
				</summary>
				<div class="spine-body">
					<p class="spine-loading" id="spine-body-${this.esc(s.id)}">${this.tr('spine_no_summary', 'Summary being generated...')}</p>
				</div>
			</details>`;
		}).join('');

		panel.innerHTML = `<div class="spine-list" role="list">${items}</div>`;

		// Lazy-load summaries on expand
		panel.querySelectorAll<HTMLDetailsElement>('details.spine-item').forEach(det => {
			det.addEventListener('toggle', () => {
				if (det.open) {
					const id = det.dataset.id;
					if (id && !this.spineLoaded.has(id)) {
						this.loadSpineSummary(id);
					}
				}
			});
		});
	}

	private async loadSpineSummary(spineId: string) {
		const el = this.shadowRoot?.getElementById(`spine-body-${spineId}`);
		if (!el) return;
		this.spineLoaded.add(spineId);

		try {
			const res = await fetch(`/api/atlas/spines/${encodeURIComponent(spineId)}/summary`);
			if (!res.ok) throw new Error('not found');
			const data = await res.json();
			if (data.summary_text) {
				el.className = 'spine-summary-text';
				el.textContent = data.summary_text;
			} else {
				el.textContent = this.tr('spine_no_summary', 'Summary being generated...');
			}
		} catch (_) {
			el.textContent = this.tr('spine_no_summary', 'Summary being generated...');
		}
	}

	// ── Chat bar ───────────────────────────────────────────────────────────

	private sendChat() {
		const input = this.shadowRoot?.querySelector<HTMLInputElement>('#chat-input');
		if (!input) return;
		const value = input.value.trim();
		if (!value) return;
		input.value = '';
		this.dispatchEvent(new CustomEvent('atlas-chat-send', {
			bubbles: true,
			composed: true,
			detail: { message: value },
		}));
	}

	// ── Utilities ──────────────────────────────────────────────────────────

	private esc(str: string): string {
		return str
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#39;');
	}

	private formatDate(iso: string): string {
		try {
			return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
		} catch (_) {
			return '';
		}
	}
}

if (!customElements.get('memory-atlas')) {
	customElements.define('memory-atlas', MemoryAtlas);
}
