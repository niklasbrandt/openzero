import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';
import { BUTTON_STYLES } from '../services/buttonStyles';

interface AtlasNode {
	id: string;
	label: string;
	type: string;
	confidence: number;
	x?: number;
	y?: number;
	vx?: number;
	vy?: number;
}

interface AtlasEdge {
	source: string;
	target: string;
	weight: number;
}

interface AtlasGraph {
	nodes: AtlasNode[];
	edges: AtlasEdge[];
}

export class MemoryAtlas extends HTMLElement {
	private t: Record<string, string> = {};
	private canvas: HTMLCanvasElement | null = null;
	private ctx: CanvasRenderingContext2D | null = null;
	private nodes: AtlasNode[] = [];
	private edges: AtlasEdge[] = [];
	private animFrame: number | null = null;
	private hoveredNode: AtlasNode | null = null;
	private selectedNode: AtlasNode | null = null;
	private dragging: AtlasNode | null = null;
	private dragOffsetX = 0;
	private dragOffsetY = 0;
	private simRunning = false;
	private simTick = 0;
	private ro: ResizeObserver | null = null;

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
		this.render();
		this.loadTranslations().then(() => {
			this.render();
			this.fetchGraph();
		});
	}

	disconnectedCallback() {
		if (this.animFrame !== null) cancelAnimationFrame(this.animFrame);
		this.ro?.disconnect();
	}

	private async fetchGraph() {
		try {
			const res = await fetch('/api/dashboard/atlas/graph?limit=80');
			if (!res.ok) throw new Error('not ok');
			const data: AtlasGraph = await res.json();
			this.nodes = data.nodes;
			this.edges = data.edges;
		} catch (_) {
			// Backend not yet available — leave nodes empty, show empty state
			this.nodes = [];
			this.edges = [];
		}
		this.updateListLens();
		if (this.nodes.length > 0) {
			this.initPositions();
			this.startSim();
		} else {
			this.showGraphEmptyState();
		}
	}

	// ── Empty state for graph canvas ─────────────────────────────────────────

	private showGraphEmptyState() {
		const canvas = this.canvas;
		const ctx = this.ctx;
		if (!canvas || !ctx) return;
		const dpr = window.devicePixelRatio || 1;
		const W = canvas.offsetWidth || 600;
		const H = canvas.offsetHeight || 360;
		canvas.width = Math.round(W * dpr);
		canvas.height = Math.round(H * dpr);
		ctx.scale(dpr, dpr);
		ctx.clearRect(0, 0, W, H);
		// Subtle centre icon
		ctx.strokeStyle = 'rgba(255,255,255,0.08)';
		ctx.lineWidth = 1;
		for (let i = 0; i < 6; i++) {
			const angle = (i / 6) * Math.PI * 2;
			const r = 48;
			ctx.beginPath();
			ctx.arc(W / 2 + r * Math.cos(angle), H / 2 + r * Math.sin(angle), 5, 0, Math.PI * 2);
			ctx.stroke();
			ctx.beginPath();
			ctx.moveTo(W / 2, H / 2);
			ctx.lineTo(W / 2 + r * Math.cos(angle), H / 2 + r * Math.sin(angle));
			ctx.stroke();
		}
		ctx.beginPath();
		ctx.arc(W / 2, H / 2, 7, 0, Math.PI * 2);
		ctx.strokeStyle = 'rgba(20,184,166,0.3)';
		ctx.lineWidth = 1.5;
		ctx.stroke();
		// Label
		ctx.font = '400 13px Inter, sans-serif';
		ctx.fillStyle = 'rgba(255,255,255,0.25)';
		ctx.textAlign = 'center';
		ctx.fillText(this.tr('atlas_empty_graph', 'The Atlas will populate as Z learns from your conversations and crews.'), W / 2, H / 2 + 52);
	}

	// ── Force-directed layout ─────────────────────────────────────────────────

	private initPositions() {
		if (!this.canvas) return;
		const W = this.canvas.offsetWidth || 600;
		const H = this.canvas.offsetHeight || 400;
		const cx = W / 2, cy = H / 2;
		this.nodes.forEach((n, i) => {
			const angle = (i / this.nodes.length) * Math.PI * 2;
			const r = Math.min(W, H) * 0.3;
			n.x = cx + r * Math.cos(angle);
			n.y = cy + r * Math.sin(angle);
			n.vx = 0;
			n.vy = 0;
		});
	}

	private nodeMap(): Map<string, AtlasNode> {
		const m = new Map<string, AtlasNode>();
		this.nodes.forEach(n => m.set(n.id, n));
		return m;
	}

	private tickSim() {
		if (!this.canvas) return;
		const W = this.canvas.offsetWidth || 600;
		const H = this.canvas.offsetHeight || 400;
		const alpha = Math.max(0.01, 1 - this.simTick / 300);
		const repulsion = 3200;
		const attraction = 0.06;
		const damping = 0.82;
		const nodeMap = this.nodeMap();

		// Repulsion
		for (let i = 0; i < this.nodes.length; i++) {
			for (let j = i + 1; j < this.nodes.length; j++) {
				const a = this.nodes[i], b = this.nodes[j];
				const dx = (b.x ?? 0) - (a.x ?? 0);
				const dy = (b.y ?? 0) - (a.y ?? 0);
				const dist = Math.sqrt(dx * dx + dy * dy) || 1;
				const force = (repulsion / (dist * dist)) * alpha;
				const fx = (dx / dist) * force;
				const fy = (dy / dist) * force;
				a.vx = (a.vx ?? 0) - fx;
				a.vy = (a.vy ?? 0) - fy;
				b.vx = (b.vx ?? 0) + fx;
				b.vy = (b.vy ?? 0) + fy;
			}
		}

		// Attraction (edges)
		this.edges.forEach(e => {
			const a = nodeMap.get(e.source), b = nodeMap.get(e.target);
			if (!a || !b) return;
			const dx = (b.x ?? 0) - (a.x ?? 0);
			const dy = (b.y ?? 0) - (a.y ?? 0);
			const dist = Math.sqrt(dx * dx + dy * dy) || 1;
			const idealDist = 100 + (1 - e.weight) * 80;
			const force = (dist - idealDist) * attraction * alpha;
			const fx = (dx / dist) * force;
			const fy = (dy / dist) * force;
			a.vx = (a.vx ?? 0) + fx;
			a.vy = (a.vy ?? 0) + fy;
			b.vx = (b.vx ?? 0) - fx;
			b.vy = (b.vy ?? 0) - fy;
		});

		// Gravity toward centre
		this.nodes.forEach(n => {
			n.vx = (n.vx ?? 0) + ((W / 2) - (n.x ?? 0)) * 0.01 * alpha;
			n.vy = (n.vy ?? 0) + ((H / 2) - (n.y ?? 0)) * 0.01 * alpha;
		});

		// Integrate + clamp
		const pad = 32;
		this.nodes.forEach(n => {
			if (n === this.dragging) return;
			n.vx = (n.vx ?? 0) * damping;
			n.vy = (n.vy ?? 0) * damping;
			n.x = Math.max(pad, Math.min(W - pad, (n.x ?? W / 2) + (n.vx ?? 0)));
			n.y = Math.max(pad, Math.min(H - pad, (n.y ?? H / 2) + (n.vy ?? 0)));
		});

		this.simTick++;
	}

	private startSim() {
		if (this.simRunning) return;
		this.simRunning = true;
		this.simTick = 0;
		const loop = () => {
			if (this.simTick < 400 || this.dragging) {
				this.tickSim();
			}
			this.drawGraph();
			this.animFrame = requestAnimationFrame(loop);
		};
		loop();
	}

	// ── Canvas rendering ──────────────────────────────────────────────────────

	private nodeRadius(n: AtlasNode): number {
		return 6 + n.confidence * 8;
	}

	private nodeColor(n: AtlasNode): string {
		const typeColors: Record<string, string> = {
			project:    'hsla(173, 80%, 42%, 1)',
			decision:   'hsla(38, 90%, 58%, 1)',
			memory:     'hsla(220, 70%, 60%, 1)',
			source:     'hsla(280, 65%, 62%, 1)',
			instance:   'hsla(0, 70%, 58%, 1)',
		};
		return typeColors[n.type] ?? 'hsla(173, 60%, 50%, 1)';
	}

	private drawGraph() {
		const canvas = this.canvas;
		const ctx = this.ctx;
		if (!canvas || !ctx) return;

		const dpr = window.devicePixelRatio || 1;
		const W = canvas.offsetWidth;
		const H = canvas.offsetHeight;
		if (canvas.width !== Math.round(W * dpr) || canvas.height !== Math.round(H * dpr)) {
			canvas.width = Math.round(W * dpr);
			canvas.height = Math.round(H * dpr);
			ctx.scale(dpr, dpr);
		}

		ctx.clearRect(0, 0, W, H);

		const nodeMap = this.nodeMap();

		// Draw edges
		this.edges.forEach(e => {
			const a = nodeMap.get(e.source);
			const b = nodeMap.get(e.target);
			if (!a || !b) return;
			const isRelated = (this.hoveredNode?.id === a.id || this.hoveredNode?.id === b.id ||
				this.selectedNode?.id === a.id || this.selectedNode?.id === b.id);
			ctx.beginPath();
			ctx.strokeStyle = isRelated
				? `rgba(20, 184, 166, ${0.15 + e.weight * 0.35})`
				: `rgba(255, 255, 255, ${0.03 + e.weight * 0.06})`;
			ctx.lineWidth = isRelated ? 1.5 : 0.8;
			ctx.moveTo(a.x ?? 0, a.y ?? 0);
			ctx.lineTo(b.x ?? 0, b.y ?? 0);
			ctx.stroke();
		});

		// Draw nodes
		this.nodes.forEach(n => {
			const x = n.x ?? 0, y = n.y ?? 0;
			const r = this.nodeRadius(n);
			const color = this.nodeColor(n);
			const isHovered = this.hoveredNode?.id === n.id;
			const isSelected = this.selectedNode?.id === n.id;
			const highlight = isHovered || isSelected;

			// Glow
			if (highlight) {
				const grd = ctx.createRadialGradient(x, y, 0, x, y, r * 3.5);
				grd.addColorStop(0, color.replace('1)', '0.35)'));
				grd.addColorStop(1, color.replace('1)', '0)'));
				ctx.beginPath();
				ctx.arc(x, y, r * 3.5, 0, Math.PI * 2);
				ctx.fillStyle = grd;
				ctx.fill();
			}

			// Fill
			ctx.beginPath();
			ctx.arc(x, y, r, 0, Math.PI * 2);
			ctx.fillStyle = highlight ? color : color.replace(', 1)', ', 0.65)');
			ctx.fill();

			// Stroke
			ctx.beginPath();
			ctx.arc(x, y, r, 0, Math.PI * 2);
			ctx.strokeStyle = highlight ? color : color.replace(', 1)', ', 0.3)');
			ctx.lineWidth = highlight ? 2 : 1;
			ctx.stroke();

			// Label
			if (highlight || this.nodes.length <= 20) {
				ctx.font = `${highlight ? 600 : 400} ${highlight ? 12 : 11}px Inter, sans-serif`;
				ctx.fillStyle = highlight ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.6)';
				ctx.textAlign = 'center';
				ctx.fillText(n.label, x, y - r - 5);
			}

			// Type badge dot (selected)
			if (isSelected) {
				ctx.beginPath();
				ctx.arc(x + r * 0.7, y - r * 0.7, 4, 0, Math.PI * 2);
				ctx.fillStyle = '#fff';
				ctx.fill();
			}
		});
	}

	// ── Pointer events ────────────────────────────────────────────────────────

	private canvasNodeAt(ex: number, ey: number): AtlasNode | null {
		const canvas = this.canvas;
		if (!canvas) return null;
		const rect = canvas.getBoundingClientRect();
		const x = ex - rect.left;
		const y = ey - rect.top;
		for (const n of [...this.nodes].reverse()) {
			const dx = (n.x ?? 0) - x;
			const dy = (n.y ?? 0) - y;
			if (Math.sqrt(dx * dx + dy * dy) <= this.nodeRadius(n) + 4) return n;
		}
		return null;
	}

	private bindCanvasEvents() {
		const canvas = this.canvas;
		if (!canvas) return;

		canvas.addEventListener('mousemove', (e: MouseEvent) => {
			const hit = this.canvasNodeAt(e.clientX, e.clientY);
			if (this.dragging) {
				const rect = canvas.getBoundingClientRect();
				this.dragging.x = e.clientX - rect.left + this.dragOffsetX;
				this.dragging.y = e.clientY - rect.top + this.dragOffsetY;
				this.dragging.vx = 0;
				this.dragging.vy = 0;
			} else {
				this.hoveredNode = hit;
				canvas.style.cursor = hit ? 'pointer' : 'default';
			}
		});

		canvas.addEventListener('mousedown', (e: MouseEvent) => {
			const hit = this.canvasNodeAt(e.clientX, e.clientY);
			if (hit) {
				const rect = canvas.getBoundingClientRect();
				this.dragging = hit;
				this.dragOffsetX = (hit.x ?? 0) - (e.clientX - rect.left);
				this.dragOffsetY = (hit.y ?? 0) - (e.clientY - rect.top);
				this.simTick = 0; // re-energise sim after drag
			}
		});

		canvas.addEventListener('mouseup', () => {
			if (this.dragging) {
				this.selectedNode = this.dragging === this.selectedNode ? null : this.dragging;
				this.dragging = null;
				this.updateDetailPanel();
			}
		});

		canvas.addEventListener('click', (e: MouseEvent) => {
			const hit = this.canvasNodeAt(e.clientX, e.clientY);
			if (!hit) {
				this.selectedNode = null;
				this.updateDetailPanel();
			}
		});

		canvas.addEventListener('mouseleave', () => {
			this.hoveredNode = null;
			this.dragging = null;
			canvas.style.cursor = 'default';
		});

		// Touch support
		canvas.addEventListener('touchmove', (e: TouchEvent) => {
			e.preventDefault();
			const t = e.touches[0];
			if (this.dragging) {
				const rect = canvas.getBoundingClientRect();
				this.dragging.x = t.clientX - rect.left;
				this.dragging.y = t.clientY - rect.top;
				this.dragging.vx = 0;
				this.dragging.vy = 0;
				this.simTick = 0;
			}
		}, { passive: false });
	}

	// ── Detail panel ──────────────────────────────────────────────────────────

	private updateDetailPanel() {
		const panel = this.shadowRoot?.querySelector<HTMLElement>('#detail-panel');
		if (!panel) return;
		if (!this.selectedNode) {
			panel.hidden = true;
			return;
		}
		const n = this.selectedNode;
		const connectedEdges = this.edges.filter(e => e.source === n.id || e.target === n.id);
		const nodeMap = this.nodeMap();
		const neighbours = connectedEdges.map(e => {
			const otherId = e.source === n.id ? e.target : e.source;
			return nodeMap.get(otherId)?.label ?? otherId;
		});

		panel.hidden = false;
		panel.innerHTML = `
			<div class="detail-header">
				<span class="detail-type-badge" style="background:${this.nodeColor(n).replace(', 1)', ', 0.15)')}; color:${this.nodeColor(n)};">${n.type}</span>
				<span class="detail-label">${n.label}</span>
				<button class="detail-close" aria-label="${this.tr('aria_close_detail', 'Close detail panel')}">
					<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12"/></svg>
				</button>
			</div>
			<div class="detail-row">
				<span class="detail-key">${this.tr('atlas_confidence', 'Confidence')}</span>
				<span class="detail-val">${Math.round(n.confidence * 100)}%</span>
			</div>
			<div class="detail-row">
				<span class="detail-key">${this.tr('atlas_connections', 'Connections')}</span>
				<span class="detail-val">${connectedEdges.length}</span>
			</div>
			${neighbours.length ? `<div class="detail-neighbours">${neighbours.map(l => `<span class="neighbour-chip">${l}</span>`).join('')}</div>` : ''}
		`;
		panel.querySelector('.detail-close')?.addEventListener('click', () => {
			this.selectedNode = null;
			this.updateDetailPanel();
		});
	}

	// ── List lens ─────────────────────────────────────────────────────────────

	private updateListLens() {
		const list = this.shadowRoot?.querySelector<HTMLElement>('#list-lens');
		if (!list) return;
		if (this.nodes.length === 0) {
			list.innerHTML = `<p class="empty-state">${this.tr('atlas_empty', 'No memory nodes yet. Z will populate the Atlas as you talk and crews run.')}</p>`;
			return;
		}
		const sorted = [...this.nodes].sort((a, b) => b.confidence - a.confidence);
		list.innerHTML = `<ul role="list" aria-label="${this.tr('aria_atlas_list', 'Memory nodes list')}">
			${sorted.map(n => `
				<li class="list-node" role="listitem">
					<span class="list-dot" style="background:${this.nodeColor(n)}" aria-hidden="true"></span>
					<span class="list-label">${n.label}</span>
					<span class="list-type">${n.type}</span>
					<span class="list-conf" aria-label="${this.tr('aria_atlas_confidence', 'Confidence')} ${Math.round(n.confidence * 100)}%">${Math.round(n.confidence * 100)}%</span>
				</li>
			`).join('')}
		</ul>`;
	}

	// ── Lens switch ───────────────────────────────────────────────────────────

	private switchLens(lens: 'graph' | 'list') {
		const graphWrap = this.shadowRoot?.querySelector<HTMLElement>('#graph-wrap');
		const listWrap = this.shadowRoot?.querySelector<HTMLElement>('#list-wrap');
		const btnGraph = this.shadowRoot?.querySelector<HTMLButtonElement>('#btn-graph');
		const btnList = this.shadowRoot?.querySelector<HTMLButtonElement>('#btn-list');
		if (graphWrap) graphWrap.hidden = lens !== 'graph';
		if (listWrap) listWrap.hidden = lens !== 'list';
		if (btnGraph) { btnGraph.classList.toggle('active', lens === 'graph'); btnGraph.setAttribute('aria-pressed', String(lens === 'graph')); }
		if (btnList) { btnList.classList.toggle('active', lens === 'list'); btnList.setAttribute('aria-pressed', String(lens === 'list')); }
	}

	// ── Render ────────────────────────────────────────────────────────────────

	render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
			<style>
				${ACCESSIBILITY_STYLES}
				${SECTION_HEADER_STYLES}
				${BUTTON_STYLES}

				:host { display: block; }

				h2 .h-icon {
					background: linear-gradient(135deg, hsla(280, 70%, 55%, 1) 0%, var(--accent-color, hsla(173, 80%, 40%, 1)) 100%);
				}

				.card {
					display: flex;
					flex-direction: column;
					position: relative;
					height: 100%;
					min-height: 480px;
				}

				.bg-glow {
					position: absolute;
					top: -10px; right: -10px;
					width: 120px; height: 120px;
					background: radial-gradient(circle at center, var(--accent-glow, rgba(20,184,166,0.3)) 0%, transparent 70%);
					opacity: 0.12;
					pointer-events: none;
					z-index: 0;
				}

				.toolbar {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					margin-bottom: 1rem;
					flex-wrap: wrap;
					z-index: 1;
					position: relative;
				}

				.lens-btn {
					display: inline-flex;
					align-items: center;
					gap: 0.35rem;
					padding: 0.35rem 0.85rem;
					font-family: inherit;
					font-size: 0.75rem;
					font-weight: 500;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.55));
					background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
					border-radius: 6px;
					cursor: pointer;
					transition: color 0.2s, background 0.2s, border-color 0.2s;
				}
				.lens-btn:hover {
					color: var(--text-primary, #fff);
					background: hsla(0, 0%, 100%, 0.07);
				}
				.lens-btn.active {
					color: var(--accent-color, hsla(173, 80%, 40%, 1));
					background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.1);
					border-color: rgba(var(--accent-color-rgb, 20, 184, 166), 0.3);
				}
				.lens-btn:focus-visible {
					outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				.node-count {
					margin-left: auto;
					font-size: 0.72rem;
					color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
				}

				/* ── Graph lens ── */
				#graph-wrap {
					flex: 1;
					position: relative;
					border-radius: 0.75rem;
					overflow: hidden;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.02));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.06));
					min-height: 360px;
				}

				#atlas-canvas {
					display: block;
					width: 100%;
					height: 100%;
					cursor: default;
				}

				/* ── Detail panel ── */
				#detail-panel {
					position: absolute;
					top: 0.75rem;
					left: 0.75rem;
					background: var(--surface-overlay, hsla(220, 20%, 10%, 0.88));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.1));
					border-radius: 0.6rem;
					padding: 0.75rem 1rem;
					min-width: 200px;
					max-width: 260px;
					backdrop-filter: blur(12px);
					-webkit-backdrop-filter: blur(12px);
					z-index: 10;
					box-shadow: 0 4px 24px rgba(0,0,0,0.4);
				}
				.detail-header {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					margin-bottom: 0.6rem;
				}
				.detail-type-badge {
					font-size: 0.6rem;
					font-weight: 700;
					letter-spacing: 0.06em;
					text-transform: uppercase;
					padding: 0.15rem 0.5rem;
					border-radius: 999px;
					border: 1px solid currentColor;
					opacity: 0.85;
				}
				.detail-label {
					flex: 1;
					font-size: 0.9rem;
					font-weight: 600;
					color: var(--text-primary, #fff);
					white-space: nowrap;
					overflow: hidden;
					text-overflow: ellipsis;
				}
				.detail-close {
					background: none;
					border: none;
					cursor: pointer;
					color: var(--text-muted, hsla(0,0%,100%,0.4));
					padding: 0.15rem;
					display: flex;
					border-radius: 4px;
					transition: color 0.15s;
				}
				.detail-close:hover { color: var(--text-primary, #fff); }
				.detail-close:focus-visible { outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1)); outline-offset: 2px; }
				.detail-row {
					display: flex;
					justify-content: space-between;
					align-items: center;
					font-size: 0.78rem;
					margin-bottom: 0.3rem;
				}
				.detail-key { color: var(--text-muted, hsla(0,0%,100%,0.45)); }
				.detail-val { color: var(--text-primary, #fff); font-weight: 500; }
				.detail-neighbours {
					display: flex;
					flex-wrap: wrap;
					gap: 0.35rem;
					margin-top: 0.5rem;
				}
				.neighbour-chip {
					font-size: 0.67rem;
					background: hsla(0, 0%, 100%, 0.07);
					border: 1px solid hsla(0, 0%, 100%, 0.1);
					border-radius: 999px;
					padding: 0.15rem 0.5rem;
					color: var(--text-muted, hsla(0,0%,100%,0.5));
					white-space: nowrap;
				}

				/* ── List lens ── */
				#list-wrap {
					flex: 1;
					overflow-y: auto;
					${SCROLLBAR_STYLES ? '' : 'scrollbar-width: thin;'}
				}
				#list-lens ul {
					list-style: none;
					padding: 0;
					margin: 0;
					display: flex;
					flex-direction: column;
					gap: 0.4rem;
				}
				.list-node {
					display: flex;
					align-items: center;
					gap: 0.6rem;
					padding: 0.6rem 0.8rem;
					border-radius: 0.5rem;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.02));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.06));
					transition: background 0.18s;
				}
				.list-node:hover {
					background: hsla(0, 0%, 100%, 0.05);
				}
				.list-dot {
					width: 8px;
					height: 8px;
					border-radius: 50%;
					flex-shrink: 0;
				}
				.list-label {
					flex: 1;
					font-size: 0.875rem;
					color: var(--text-primary, #fff);
					white-space: nowrap;
					overflow: hidden;
					text-overflow: ellipsis;
				}
				.list-type {
					font-size: 0.67rem;
					color: var(--text-muted, hsla(0,0%,100%,0.35));
					text-transform: uppercase;
					letter-spacing: 0.06em;
				}
				.list-conf {
					font-size: 0.75rem;
					font-weight: 500;
					color: var(--text-muted, hsla(0,0%,100%,0.45));
					min-width: 2.5rem;
					text-align: right;
				}

				.empty-state {
					color: var(--text-muted, hsla(0,0%,100%,0.4));
					font-size: 0.9rem;
					text-align: center;
					padding: 3rem 1rem;
					line-height: 1.6;
				}

				@media (prefers-reduced-motion: reduce) {
					.lens-btn, .list-node, #detail-panel { transition: none !important; }
				}
				@media (forced-colors: active) {
					.h-icon { background: ButtonFace; border: 1px solid ButtonText; }
					.lens-btn.active { border: 2px solid Highlight; }
					#graph-wrap { border: 1px solid ButtonText; }
				}
			</style>

			<div class="card">
				<div class="bg-glow" aria-hidden="true"></div>

				<h2>
					<span class="h-icon" aria-hidden="true">
						<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
							<circle cx="12" cy="12" r="3"></circle>
							<line x1="12" y1="3" x2="12" y2="5"></line>
							<line x1="12" y1="19" x2="12" y2="21"></line>
							<line x1="3" y1="12" x2="5" y2="12"></line>
							<line x1="19" y1="12" x2="21" y2="12"></line>
							<line x1="5.64" y1="5.64" x2="7.05" y2="7.05"></line>
							<line x1="16.95" y1="16.95" x2="18.36" y2="18.36"></line>
							<line x1="5.64" y1="18.36" x2="7.05" y2="16.95"></line>
							<line x1="16.95" y1="7.05" x2="18.36" y2="5.64"></line>
						</svg>
					</span>
					${this.tr('atlas_title', 'Memory Atlas')}
					<span class="subtitle" aria-hidden="true">${this.tr('atlas_subtitle', 'Knowledge Graph')}</span>
				</h2>

				<div class="toolbar" role="toolbar" aria-label="${this.tr('aria_atlas_toolbar', 'Atlas lens selector')}">
					<button id="btn-graph" class="lens-btn active" aria-pressed="true" aria-label="${this.tr('aria_atlas_graph', 'Graph lens')}">
						<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><line x1="7" y1="11" x2="17" y2="6"/><line x1="7" y1="13" x2="17" y2="18"/></svg>
						${this.tr('atlas_lens_graph', 'Graph')}
					</button>
					<button id="btn-list" class="lens-btn" aria-pressed="false" aria-label="${this.tr('aria_atlas_list_btn', 'List lens')}">
						<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="3" cy="6" r="1" fill="currentColor"/><circle cx="3" cy="12" r="1" fill="currentColor"/><circle cx="3" cy="18" r="1" fill="currentColor"/></svg>
						${this.tr('atlas_lens_list', 'List')}
					</button>
					<span class="node-count" role="status" aria-live="polite" id="node-count"></span>
				</div>

				<div id="graph-wrap">
					<canvas id="atlas-canvas"
						role="img"
						aria-label="${this.tr('aria_atlas_canvas', 'Interactive memory graph. Click nodes to inspect. Switch to List lens for accessible navigation.')}">
					</canvas>
					<div id="detail-panel" hidden aria-live="polite" aria-label="${this.tr('aria_detail_panel', 'Node detail')}"></div>
				</div>

				<div id="list-wrap" hidden>
					<div id="list-lens" aria-label="${this.tr('aria_atlas_list', 'Memory nodes list')}">
						<p class="empty-state">${this.tr('loading', 'Loading...')}</p>
					</div>
				</div>
			</div>
		`;

		// Wire up canvas
		this.canvas = this.shadowRoot?.querySelector<HTMLCanvasElement>('#atlas-canvas') ?? null;
		this.ctx = this.canvas?.getContext('2d') ?? null;
		this.bindCanvasEvents();

		// Wire up lens buttons
		this.shadowRoot?.querySelector('#btn-graph')?.addEventListener('click', () => this.switchLens('graph'));
		this.shadowRoot?.querySelector('#btn-list')?.addEventListener('click', () => this.switchLens('list'));

		// ResizeObserver to keep canvas sharp on layout change
		this.ro?.disconnect();
		this.ro = new ResizeObserver(() => {
			if (this.simTick > 0) this.drawGraph();
		});
		if (this.canvas) this.ro.observe(this.canvas);
	}
}

customElements.define('memory-atlas', MemoryAtlas);
