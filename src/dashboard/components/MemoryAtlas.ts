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

interface TimelineNode {
	id: string;
	type: string;
	label: string;
	created_at: string;
}

interface Decision {
	id: string;
	rationale: string;
	status: string;
	revisit_when?: string | null;
}

interface Contradiction {
	id: string;
	primary_node_id: string;
	opposing_node_id: string;
	detected_at: string;
	status: string;
}

interface DiffEntry {
	id: string;
	kind: string;
	summary: string;
	created_at: string;
	node_id?: string | null;
	spine_id?: string | null;
}

type Lens = 'list' | 'graph' | 'spines' | 'timeline' | 'decisions' | 'contradictions' | 'diffs';

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
	private _mergeMode: boolean = false;
	private _mergeSelection: Set<number> = new Set();
	private _contradictionsShowAll: boolean = false;

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
					flex-direction: column;
					padding: 0.75rem 1rem;
					border-radius: var(--radius-md, 0.5rem);
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
					margin-bottom: 0.5rem;
					cursor: pointer;
					min-height: 44px;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.04));
					transition: background var(--duration-fast, 0.15s);
				}

				.node-row {
					display: flex;
					align-items: center;
					gap: 0.75rem;
					width: 100%;
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

				/* ── Node actions (steel-man / echo-finder) ── */
				.node-actions {
					display: flex;
					gap: 0.5rem;
					opacity: 0;
					transition: opacity 0.15s;
					flex-shrink: 0;
					margin-left: auto;
				}

				.spine-actions {
					opacity: 1;
					margin-left: 0;
				}

				.node-item:hover .node-actions,
				.node-item:focus-within .node-actions {
					opacity: 1;
				}

				.node-action-btn {
					min-height: 44px;
					min-width: 44px;
					padding: 0.25rem 0.75rem;
					border-radius: var(--radius-md, 0.5rem);
					font-size: 0.75rem;
					font-weight: 600;
					cursor: pointer;
					background: transparent;
					border: 1.5px solid var(--border-subtle, hsla(0, 0%, 100%, 0.2));
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.7));
					transition: background var(--duration-fast, 0.15s);
					white-space: nowrap;
				}

				.node-action-btn:hover {
					background: var(--surface-card, hsla(0, 0%, 100%, 0.08));
				}

				.node-action-btn:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				.node-action-btn:disabled {
					opacity: 0.4;
					cursor: not-allowed;
				}

				/* ── Steel-man result aside ── */
				.steel-man-result {
					border-left: 3px solid var(--accent-color, hsla(173, 80%, 40%, 1));
					padding-left: 0.75rem;
					margin-top: 0.5rem;
					font-size: 0.875rem;
					color: var(--text-secondary, hsla(0, 0%, 80%, 1));
				}

				.steel-man-result > summary {
					cursor: pointer;
					font-size: 0.8rem;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.5));
					font-weight: 600;
					padding: 0.2rem 0;
					min-height: 44px;
					display: flex;
					align-items: center;
					list-style: none;
					user-select: none;
				}

				.steel-man-result > summary::-webkit-details-marker { display: none; }

				.steel-man-result > summary:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				.steel-man-content {
					padding: 0.25rem 0 0.25rem;
					line-height: 1.6;
				}

				/* ── Echo-finder candidates ── */
				.echo-candidates-panel {
					margin-top: 0.5rem;
				}

				.echo-candidates-label {
					font-size: 0.75rem;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
					font-weight: 600;
					margin-bottom: 0.25rem;
					display: block;
				}

				ul.echo-candidates {
					list-style: none;
					margin: 0;
					padding: 0;
					display: flex;
					flex-direction: column;
					gap: 0.25rem;
				}

				ul.echo-candidates li {
					display: flex;
					justify-content: space-between;
					align-items: center;
					gap: 0.5rem;
					padding: 0.35rem 0.5rem;
					border-radius: var(--radius-sm, 0.25rem);
					background: var(--surface-card, hsla(0, 0%, 100%, 0.04));
					font-size: 0.8rem;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.7));
				}

				.echo-candidate-label {
					flex: 1;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}

				.echo-candidate-conf {
					font-size: 0.7rem;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
					flex-shrink: 0;
				}

				.echo-merge-btn {
					min-height: 44px;
					min-width: 44px;
					padding: 0.25rem 0.6rem;
					border-radius: var(--radius-sm, 0.25rem);
					font-size: 0.7rem;
					font-weight: 600;
					cursor: pointer;
					background: transparent;
					border: 1px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					transition: background var(--duration-fast, 0.15s);
					flex-shrink: 0;
					white-space: nowrap;
				}

				.echo-merge-btn:hover {
					background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.12));
				}

				.echo-merge-btn:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
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
					dialog { border: 2px solid ButtonText; }
					.merge-btn { border-color: ButtonText; color: ButtonText; }
					.node-actions button { border: 1px solid ButtonText; }
					.echo-merge-btn { border-color: ButtonText; color: ButtonText; }
				}

				/* ── Merge mode toolbar ── */
				.merge-toolbar {
					display: flex;
					align-items: center;
					gap: 0.75rem;
					flex-wrap: wrap;
					margin-bottom: 0.75rem;
				}

				.merge-btn {
					min-height: 44px;
					min-width: 44px;
					padding: 0.5rem 1.25rem;
					border-radius: var(--radius-md, 0.5rem);
					font-size: 0.85rem;
					font-weight: 600;
					cursor: pointer;
					background: transparent;
					border: 1.5px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					transition:
						background var(--duration-fast, 0.15s),
						color var(--duration-fast, 0.15s);
				}

				.merge-btn:hover {
					background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.12));
				}

				.merge-btn:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				.merge-btn:disabled {
					opacity: 0.4;
					cursor: not-allowed;
				}

				.merge-btn.active {
					background: var(--accent-primary, hsla(173, 80%, 40%, 1));
					color: hsla(0, 0%, 100%, 1);
				}

				.node-item input[type="checkbox"] {
					accent-color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					width: 1.1rem;
					height: 1.1rem;
					flex-shrink: 0;
					cursor: pointer;
				}

				/* ── Merge dialog ── */
				dialog {
					background: var(--bg-card, hsla(0, 0%, 10%, 0.95));
					border: 1px solid var(--border, hsla(0, 0%, 100%, 0.1));
					border-radius: 1rem;
					padding: 1.5rem;
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					min-width: 20rem;
					max-width: min(90vw, 32rem);
				}

				dialog::backdrop {
					background: rgba(0, 0, 0, 0.5);
				}

				.dialog-title {
					font-size: 1rem;
					font-weight: 700;
					margin: 0 0 1rem;
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
				}

				.dialog-field {
					margin-bottom: 0.75rem;
					font-size: 0.875rem;
				}

				.dialog-field-label {
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
					font-size: 0.75rem;
					margin-bottom: 0.2rem;
					display: block;
				}

				.dialog-field-value {
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					font-weight: 500;
				}

				.dialog-actions {
					display: flex;
					gap: 0.75rem;
					flex-wrap: wrap;
					margin-top: 1.25rem;
				}

				.dialog-cancel {
					min-height: 44px;
					min-width: 44px;
					padding: 0.5rem 1.25rem;
					border-radius: var(--radius-md, 0.5rem);
					font-size: 0.85rem;
					font-weight: 600;
					cursor: pointer;
					background: transparent;
					border: 1.5px solid var(--border-subtle, hsla(0, 0%, 100%, 0.2));
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.7));
					transition: background var(--duration-fast, 0.15s);
				}

				.dialog-cancel:hover {
					background: var(--surface-card, hsla(0, 0%, 100%, 0.06));
				}

				.dialog-cancel:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				/* ── Merge status message ── */
				.merge-status {
					font-size: 0.875rem;
					padding: 0.5rem 0;
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					min-height: 1.5rem;
				}

				.merge-status.error {
					color: var(--color-danger, hsla(0, 80%, 60%, 1));
				}

				/* ── Reduced motion (merge additions) ── */
				@media (prefers-reduced-motion: reduce) {
					.merge-btn { transition: none; }
					dialog { animation: none; }
					.node-actions { transition: none; }
					.node-action-btn { transition: none; }
					.echo-merge-btn { transition: none; }
				}

				/* ── Timeline lens ── */
				.timeline-list {
					position: relative;
					padding-left: 1.5rem;
					list-style: none;
					margin: 0;
					max-height: 60vh;
					overflow-y: auto;
				}

				.timeline-list::before {
					content: '';
					position: absolute;
					left: 0.5rem;
					top: 0;
					bottom: 0;
					width: 1px;
					background: var(--border, hsla(0, 0%, 100%, 0.1));
				}

				.timeline-entry {
					position: relative;
					padding: 0.5rem 0 0.75rem 0.5rem;
				}

				.timeline-entry::before {
					content: '';
					position: absolute;
					left: -0.75rem;
					top: 0.65rem;
					width: 0.6rem;
					height: 0.6rem;
					border-radius: 50%;
					background: var(--accent-color, hsla(173, 80%, 40%, 1));
				}

				.timeline-date {
					display: block;
					font-size: 0.7rem;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
					margin-bottom: 0.2rem;
				}

				.timeline-label {
					font-size: 0.875rem;
					font-weight: 500;
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					margin-right: 0.5rem;
				}

				/* ── Decisions lens ── */
				.decisions-columns {
					display: grid;
					grid-template-columns: repeat(3, 1fr);
					gap: 1rem;
				}

				@media (max-width: 768px) {
					.decisions-columns {
						grid-template-columns: 1fr;
					}
				}

				.decisions-column-header {
					font-size: 0.75rem;
					font-weight: 700;
					text-transform: uppercase;
					letter-spacing: 0.08em;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
					margin-bottom: 0.5rem;
				}

				.decision-card {
					display: flex;
					flex-direction: column;
					gap: 0.5rem;
					padding: 0.75rem 1rem;
					border-radius: var(--radius-md, 0.5rem);
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
					background: var(--surface-card, hsla(0, 0%, 100%, 0.04));
					margin-bottom: 0.5rem;
				}

				.decision-rationale {
					font-size: 0.875rem;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.75));
					line-height: 1.5;
				}

				.decision-revisit {
					font-size: 0.75rem;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
				}

				.decision-revisit-label {
					font-weight: 600;
				}

				/* ── Status badges (decisions / contradictions) ── */
				.status-badge {
					font-size: 0.7rem;
					font-weight: 600;
					padding: 0.2rem 0.5rem;
					border-radius: 999px;
					display: inline-block;
					align-self: flex-start;
				}

				.status-badge.open {
					background: hsla(216, 80%, 60%, 0.12);
					color: hsla(216, 80%, 60%, 1);
				}

				.status-badge.revisit_due {
					background: hsla(45, 80%, 50%, 0.12);
					color: hsla(45, 80%, 50%, 1);
				}

				.status-badge.resolved {
					background: hsla(120, 60%, 40%, 0.12);
					color: hsla(120, 60%, 40%, 1);
				}

				.status-badge.dismissed {
					background: var(--surface-card, hsla(0, 0%, 100%, 0.06));
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
				}

				/* ── Contradictions lens ── */
				.contradiction-filter {
					display: flex;
					gap: 0.5rem;
					margin-bottom: 0.75rem;
				}

				.contradiction-filter-btn {
					min-height: 44px;
					min-width: 44px;
					padding: 0.4rem 1rem;
					border-radius: var(--radius-md, 0.5rem);
					font-size: 0.8rem;
					font-weight: 600;
					cursor: pointer;
					background: transparent;
					border: 1.5px solid var(--border-subtle, hsla(0, 0%, 100%, 0.2));
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.7));
					transition:
						background var(--duration-fast, 0.15s),
						border-color var(--duration-fast, 0.15s);
				}

				.contradiction-filter-btn.active {
					background: var(--accent-primary, hsla(173, 80%, 40%, 1));
					color: hsla(0, 0%, 100%, 1);
					border-color: var(--accent-primary, hsla(173, 80%, 40%, 1));
				}

				.contradiction-filter-btn:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				.contradiction-card {
					display: flex;
					flex-direction: column;
					gap: 0.5rem;
					padding: 0.75rem 1rem;
					border-radius: var(--radius-md, 0.5rem);
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
					background: var(--surface-card, hsla(0, 0%, 100%, 0.04));
					margin-bottom: 0.5rem;
				}

				.contradiction-nodes {
					font-size: 0.8rem;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
					font-family: monospace;
					overflow-wrap: break-word;
				}

				.contradiction-date {
					font-size: 0.7rem;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.35));
				}

				.contradiction-actions {
					display: flex;
					gap: 0.5rem;
					flex-wrap: wrap;
				}

				/* ── Diffs lens ── */
				.diffs-feed {
					display: flex;
					flex-direction: column;
					gap: 0.5rem;
					max-height: 60vh;
					overflow-y: auto;
				}

				.diff-entry {
					display: flex;
					flex-direction: column;
					gap: 0.4rem;
					padding: 0.75rem 1rem;
					border-radius: var(--radius-md, 0.5rem);
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
					background: var(--surface-card, hsla(0, 0%, 100%, 0.04));
				}

				.diff-header {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					flex-wrap: wrap;
				}

				.diff-date-chip {
					font-size: 0.7rem;
					color: var(--text-faint, hsla(0, 0%, 100%, 0.4));
				}

				.diff-kind-badge {
					font-size: 0.7rem;
					font-weight: 600;
					padding: 0.2rem 0.5rem;
					border-radius: 999px;
					background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.12));
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					text-transform: uppercase;
					letter-spacing: 0.05em;
				}

				.diff-summary {
					font-size: 0.875rem;
					color: var(--text-secondary, hsla(0, 0%, 100%, 0.75));
					line-height: 1.5;
				}

				.diff-links {
					display: flex;
					gap: 0.5rem;
					flex-wrap: wrap;
				}

				.diff-link-btn {
					font-size: 0.75rem;
					font-weight: 600;
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					background: transparent;
					border: none;
					padding: 0.25rem 0;
					cursor: pointer;
					min-height: 44px;
					text-decoration: underline;
				}

				.diff-link-btn:focus-visible {
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				/* ── Forced colors (MA3 additions) ── */
				@media (forced-colors: active) {
					.timeline-entry::before {
						forced-color-adjust: none;
						background: ButtonText;
					}
					.status-badge {
						forced-color-adjust: none;
						background: ButtonFace;
						color: ButtonText;
						border: 1px solid ButtonText;
					}
					.contradiction-filter-btn { border-color: ButtonText; color: ButtonText; }
					.contradiction-filter-btn.active {
						forced-color-adjust: none;
						background: ButtonText;
						color: ButtonFace;
					}
					.diff-kind-badge {
						forced-color-adjust: none;
						border: 1px solid ButtonText;
					}
				}

				/* ── Reduced motion (MA3 additions) ── */
				@media (prefers-reduced-motion: reduce) {
					.contradiction-filter-btn { transition: none; }
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
					<button
						role="tab"
						data-lens="timeline"
						aria-selected="false"
						aria-controls="lens-timeline"
						aria-label="${this.tr('aria_lens_timeline', 'Switch to Timeline lens')}"
					>${this.tr('lens_timeline', 'Timeline')}</button>
					<button
						role="tab"
						data-lens="decisions"
						aria-selected="false"
						aria-controls="lens-decisions"
						aria-label="${this.tr('aria_lens_decisions', 'Switch to Decisions lens')}"
					>${this.tr('lens_decisions', 'Decisions')}</button>
					<button
						role="tab"
						data-lens="contradictions"
						aria-selected="false"
						aria-controls="lens-contradictions"
						aria-label="${this.tr('aria_lens_contradictions', 'Switch to Contradictions lens')}"
					>${this.tr('lens_contradictions', 'Contradictions')}</button>
					<button
						role="tab"
						data-lens="diffs"
						aria-selected="false"
						aria-controls="lens-diffs"
						aria-label="${this.tr('aria_lens_diffs', 'Switch to Changes lens')}"
					>${this.tr('lens_diffs', 'Changes')}</button>
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

				<div
					id="lens-timeline"
					role="tabpanel"
					aria-label="${this.tr('aria_timeline_lens', 'Memory timeline')}"
					class="lens-panel"
					hidden
				>
					<div class="loading-line"></div>
					<div class="loading-line" style="width:78%;"></div>
				</div>

				<div
					id="lens-decisions"
					role="tabpanel"
					aria-label="${this.tr('aria_decisions_lens', 'Decisions lens')}"
					class="lens-panel"
					hidden
				>
					<div class="loading-line"></div>
					<div class="loading-line" style="width:78%;"></div>
				</div>

				<div
					id="lens-contradictions"
					role="tabpanel"
					aria-label="${this.tr('aria_contradictions_lens', 'Contradictions lens')}"
					class="lens-panel"
					hidden
				>
					<div class="loading-line"></div>
					<div class="loading-line" style="width:78%;"></div>
				</div>

				<div
					id="lens-diffs"
					role="tabpanel"
					aria-label="${this.tr('aria_diffs_lens', 'Changes feed')}"
					class="lens-panel"
					hidden
				>
					<div class="loading-line"></div>
					<div class="loading-line" style="width:78%;"></div>
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
			timeline: 'lens-timeline',
			decisions: 'lens-decisions',
			contradictions: 'lens-contradictions',
			diffs: 'lens-diffs',
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
		if (lens === 'timeline') await this.loadTimelineLens();
		if (lens === 'decisions') await this.loadDecisionsLens();
		if (lens === 'contradictions') await this.loadContradictionsLens();
		if (lens === 'diffs') await this.loadDiffsLens();
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
			const nodeId = Number(n.id);
			const checkedAttr = this._mergeSelection.has(nodeId) ? ' checked' : '';
			const checkboxHtml = this._mergeMode
				? `<input
						type="checkbox"
						data-merge-id="${nodeId}"
						aria-label="${this.tr('aria_select_node_merge', 'Select node for merge')}: ${this.esc(n.label)}"
						${checkedAttr}
					/>`
				: '';
			return `<li
				role="listitem"
				class="node-item"
				tabindex="0"
				data-id="${this.esc(n.id)}"
				aria-label="${this.tr('aria_node_item', 'Memory node')}: ${this.esc(n.label)}"
			>
				<div class="node-row">
					${checkboxHtml}
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
					<div class="node-actions">
						<button
							class="node-action-btn steel-man-btn"
							data-node-id="${nodeId}"
							aria-label="${this.tr('aria_steel_man_btn', 'Generate strongest counter-argument for this item')}"
						>${this.tr('steel_man_btn', 'Steel-man')}</button>
						<button
							class="node-action-btn echo-finder-btn"
							data-node-id="${nodeId}"
							aria-label="${this.tr('aria_echo_finder_btn', 'Find similar memory nodes')}"
						>${this.tr('echo_finder_btn', 'Echo-finder')}</button>
					</div>
				</div>
				<div class="node-extras"></div>
			</li>`;
		}).join('');

		const previewDisabled = this._mergeSelection.size < 2 ? ' disabled' : '';

		panel.innerHTML = `
			<div class="merge-toolbar" role="toolbar" aria-label="${this.tr('select_to_merge', 'Select to merge')}">
				<button
					class="merge-btn${this._mergeMode ? ' active' : ''}"
					id="merge-mode-toggle"
					aria-pressed="${this._mergeMode}"
					title="${this.tr('select_to_merge', 'Select to merge')}"
				>${this.tr('select_to_merge', 'Select to merge')}</button>
				${this._mergeMode ? `<button
					class="merge-btn"
					id="preview-merge-btn"
					${previewDisabled}
					aria-disabled="${this._mergeSelection.size < 2}"
				>${this.tr('preview_merge', 'Preview merge')}</button>` : ''}
			</div>
			<div
				class="merge-status"
				id="merge-status"
				aria-live="polite"
				role="status"
			></div>
			<ul
				role="list"
				class="node-list"
				aria-label="${this.tr('atlas_title', 'Memory Atlas')}"
			>${items}</ul>
			<dialog
				id="merge-dialog"
				aria-label="${this.tr('aria_merge_dialog', 'Merge preview dialog')}"
				aria-modal="true"
			>
				<p class="dialog-title">${this.tr('preview_merge', 'Preview merge')}</p>
				<div id="merge-dialog-body"></div>
				<div class="dialog-actions">
					<button class="merge-btn" id="confirm-merge-btn">${this.tr('confirm_merge', 'Confirm merge')}</button>
					<button class="dialog-cancel" id="cancel-merge-btn">${this.tr('cancel', 'Cancel')}</button>
				</div>
			</dialog>
		`;

		this.bindListKeys(panel);
		this.bindMergeEvents(panel);
		this.bindNodeActionEvents(panel);
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

	private bindMergeEvents(panel: HTMLElement) {
		const toggleBtn = panel.querySelector<HTMLButtonElement>('#merge-mode-toggle');
		toggleBtn?.addEventListener('click', () => {
			this._mergeMode = !this._mergeMode;
			if (!this._mergeMode) this._mergeSelection.clear();
			this.renderListLens(panel);
		});

		const previewBtn = panel.querySelector<HTMLButtonElement>('#preview-merge-btn');
		previewBtn?.addEventListener('click', () => {
			if (this._mergeSelection.size < 2) return;
			this.openMergePreview(panel);
		});

		// Checkbox change events
		panel.querySelectorAll<HTMLInputElement>('input[data-merge-id]').forEach(cb => {
			cb.addEventListener('change', () => {
				const id = Number(cb.dataset.mergeId);
				if (cb.checked) {
					this._mergeSelection.add(id);
				} else {
					this._mergeSelection.delete(id);
				}
				// Re-render to update preview button state
				this.renderListLens(panel);
			});
		});

		// Dialog cancel
		const cancelBtn = panel.querySelector<HTMLButtonElement>('#cancel-merge-btn');
		const dialog = panel.querySelector<HTMLDialogElement>('#merge-dialog');
		cancelBtn?.addEventListener('click', () => { dialog?.close(); });
	}

	private async openMergePreview(panel: HTMLElement, nodeIds?: number[]) {
		const ids = nodeIds ?? Array.from(this._mergeSelection);
		const fromSelection = nodeIds === undefined;
		const statusEl = panel.querySelector<HTMLElement>('#merge-status');
		const dialog = panel.querySelector<HTMLDialogElement>('#merge-dialog');
		const dialogBody = panel.querySelector<HTMLElement>('#merge-dialog-body');
		if (!dialog || !dialogBody) return;

		if (statusEl) {
			statusEl.className = 'merge-status';
			statusEl.textContent = this.tr('recompose_loading', 'Processing...');
		}

		try {
			const res = await fetch('/api/atlas/recompose/merge/preview', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ node_ids: ids }),
			});
			if (!res.ok) throw new Error('preview failed');
			const data = await res.json() as { proposed_label: string; proposed_type: string };

			if (statusEl) statusEl.textContent = '';

			dialogBody.innerHTML = `
				<div class="dialog-field">
					<span class="dialog-field-label">${this.tr('merge_proposed_label', 'Proposed label')}</span>
					<span class="dialog-field-value">${this.esc(data.proposed_label ?? '')}</span>
				</div>
				<div class="dialog-field">
					<span class="dialog-field-label">${this.tr('merge_proposed_type', 'Proposed type')}</span>
					<span class="dialog-field-value">${this.esc(data.proposed_type ?? '')}</span>
				</div>
			`;

			// Wire confirm button
			const confirmBtn = panel.querySelector<HTMLButtonElement>('#confirm-merge-btn');
			// Remove old listener by cloning
			const newConfirm = confirmBtn?.cloneNode(true) as HTMLButtonElement | undefined;
			if (confirmBtn && newConfirm) {
				confirmBtn.replaceWith(newConfirm);
				newConfirm.addEventListener('click', () => {
					this.confirmMerge(panel, dialog, data.proposed_label, data.proposed_type, ids, fromSelection);
				});
			}

			dialog.showModal();
		} catch (_) {
			if (statusEl) {
				statusEl.className = 'merge-status error';
				statusEl.textContent = this.tr('recompose_error', 'Operation failed. Please try again.');
			}
		}
	}

	private async confirmMerge(
		panel: HTMLElement,
		dialog: HTMLDialogElement,
		proposedLabel: string,
		proposedType: string,
		nodeIds: number[],
		clearMergeMode: boolean = true,
	) {
		const statusEl = panel.querySelector<HTMLElement>('#merge-status');
		if (statusEl) {
			statusEl.className = 'merge-status';
			statusEl.textContent = this.tr('recompose_loading', 'Processing...');
		}
		dialog.close();

		try {
			const res = await fetch('/api/atlas/recompose/merge/confirm', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					node_ids: nodeIds,
					proposed_label: proposedLabel,
					proposed_type: proposedType,
				}),
			});
			if (!res.ok) throw new Error('confirm failed');

			if (clearMergeMode) {
				this._mergeSelection.clear();
				this._mergeMode = false;
			}

			if (statusEl) {
				statusEl.className = 'merge-status';
				statusEl.textContent = this.tr('merge_success', 'Nodes merged successfully.');
			}

			// Reload list
			await this.loadListLens();
		} catch (_) {
			if (statusEl) {
				statusEl.className = 'merge-status error';
				statusEl.textContent = this.tr('recompose_error', 'Operation failed. Please try again.');
			}
		}
	}

	// ── Node action event binding ────────────────────────────────────────────

	private bindNodeActionEvents(panel: HTMLElement) {
		panel.querySelectorAll<HTMLButtonElement>('.steel-man-btn[data-node-id]').forEach(btn => {
			btn.addEventListener('click', (e: MouseEvent) => {
				e.stopPropagation();
				const nodeId = Number(btn.dataset.nodeId);
				const extrasEl = btn.closest<HTMLElement>('.node-item')?.querySelector<HTMLElement>('.node-extras') ?? null;
				if (extrasEl) this.handleSteelMan({ nodeId }, btn, extrasEl);
			});
		});

		panel.querySelectorAll<HTMLButtonElement>('.echo-finder-btn[data-node-id]').forEach(btn => {
			btn.addEventListener('click', (e: MouseEvent) => {
				e.stopPropagation();
				const nodeId = Number(btn.dataset.nodeId);
				const extrasEl = btn.closest<HTMLElement>('.node-item')?.querySelector<HTMLElement>('.node-extras') ?? null;
				if (extrasEl) this.handleEchoFinder(nodeId, btn, extrasEl, panel);
			});
		});
	}

	private async handleSteelMan(
		target: { nodeId?: number; spineId?: string },
		btn: HTMLButtonElement,
		extrasEl: HTMLElement,
	) {
		const origText = btn.textContent ?? this.tr('steel_man_btn', 'Steel-man');
		btn.disabled = true;
		btn.setAttribute('aria-busy', 'true');
		btn.textContent = this.tr('recompose_loading', 'Processing...');

		try {
			const body = target.nodeId !== undefined
				? { node_id: target.nodeId }
				: { spine_id: target.spineId };
			const res = await fetch('/api/atlas/recompose/steel-man', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!res.ok) throw new Error('steel-man failed');
			const data = await res.json() as { steel_man: string };

			extrasEl.querySelector('.steel-man-result')?.remove();
			const detailsEl = document.createElement('details');
			detailsEl.className = 'steel-man-result';
			detailsEl.open = true;
			detailsEl.innerHTML = `<summary>${this.esc(this.tr('steel_man_result_label', 'Strongest counter-argument:'))}</summary><div class="steel-man-content">${this.esc(data.steel_man ?? '')}</div>`;
			extrasEl.prepend(detailsEl);
		} catch (_) {
			extrasEl.querySelector('.steel-man-result')?.remove();
			const errEl = document.createElement('div');
			errEl.className = 'steel-man-result';
			errEl.style.color = 'var(--color-danger, hsla(0, 80%, 60%, 1))';
			errEl.style.borderLeftColor = 'var(--color-danger, hsla(0, 80%, 60%, 1))';
			errEl.textContent = this.tr('recompose_error', 'Operation failed. Please try again.');
			extrasEl.prepend(errEl);
		} finally {
			btn.disabled = false;
			btn.removeAttribute('aria-busy');
			btn.textContent = origText;
		}
	}

	private async handleEchoFinder(
		nodeId: number,
		btn: HTMLButtonElement,
		extrasEl: HTMLElement,
		panel: HTMLElement,
	) {
		const origText = btn.textContent ?? this.tr('echo_finder_btn', 'Echo-finder');
		btn.disabled = true;
		btn.setAttribute('aria-busy', 'true');
		btn.textContent = this.tr('recompose_loading', 'Processing...');

		try {
			const res = await fetch(`/api/atlas/recompose/echo-finder/${encodeURIComponent(String(nodeId))}`);
			if (!res.ok) throw new Error('echo-finder failed');
			const candidates = await res.json() as Array<{ id: number; label: string; confidence: number }>;

			extrasEl.querySelector('.echo-candidates-panel')?.remove();
			const wrapEl = document.createElement('div');
			wrapEl.className = 'echo-candidates-panel';

			const lbl = document.createElement('span');
			lbl.className = 'echo-candidates-label';
			lbl.textContent = this.tr('echo_finder_candidates', 'Similar nodes:');
			wrapEl.appendChild(lbl);

			if (candidates.length === 0) {
				const emptySpan = document.createElement('span');
				emptySpan.style.fontSize = '0.8rem';
				emptySpan.style.color = 'var(--text-faint, hsla(0,0%,100%,0.4))';
				emptySpan.textContent = ' \u2014';
				lbl.appendChild(emptySpan);
			} else {
				const ul = document.createElement('ul');
				ul.className = 'echo-candidates';
				ul.setAttribute('role', 'list');

				candidates.forEach(c => {
					const conf = Math.round((c.confidence || 0) * 100);
					const li = document.createElement('li');
					li.innerHTML = `<span class="echo-candidate-label">${this.esc(c.label)}</span><span class="echo-candidate-conf">${conf}%</span>`;

					const mergeBtn = document.createElement('button');
					mergeBtn.className = 'echo-merge-btn';
					mergeBtn.setAttribute('aria-label', `${this.tr('merge_with_original', 'Merge with original')}: ${this.esc(c.label)}`);
					mergeBtn.textContent = this.tr('merge_with_original', 'Merge with original');
					mergeBtn.addEventListener('click', () => {
						this.openMergePreview(panel, [nodeId, c.id]);
					});
					li.appendChild(mergeBtn);
					ul.appendChild(li);
				});

				wrapEl.appendChild(ul);
			}

			extrasEl.appendChild(wrapEl);
		} catch (_) {
			extrasEl.querySelector('.echo-candidates-panel')?.remove();
			const errEl = document.createElement('div');
			errEl.className = 'echo-candidates-panel';
			errEl.style.color = 'var(--color-danger, hsla(0, 80%, 60%, 1))';
			errEl.textContent = this.tr('recompose_error', 'Operation failed. Please try again.');
			extrasEl.appendChild(errEl);
		} finally {
			btn.disabled = false;
			btn.removeAttribute('aria-busy');
			btn.textContent = origText;
		}
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
					<div class="node-actions spine-actions" style="margin-top:0.75rem;">
						<button
							class="node-action-btn steel-man-btn"
							data-spine-id="${this.esc(s.id)}"
							aria-label="${this.tr('aria_steel_man_btn', 'Generate strongest counter-argument for this item')}"
						>${this.tr('steel_man_btn', 'Steel-man')}</button>
					</div>
					<div class="spine-extras"></div>
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

		// Wire spine steel-man buttons
		panel.querySelectorAll<HTMLButtonElement>('.steel-man-btn[data-spine-id]').forEach(btn => {
			btn.addEventListener('click', (e: MouseEvent) => {
				e.stopPropagation();
				const extrasEl = btn.closest<HTMLElement>('details')?.querySelector<HTMLElement>('.spine-extras') ?? null;
				if (extrasEl) this.handleSteelMan({ spineId: btn.dataset.spineId ?? '' }, btn, extrasEl);
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

	// ── Timeline lens ──────────────────────────────────────────────────────

	private async loadTimelineLens() {
		const panel = this.shadowRoot?.getElementById('lens-timeline');
		if (!panel) return;
		try {
			const res = await fetch('/api/atlas/timeline?limit=100');
			if (!res.ok) throw new Error('fetch failed');
			const nodes: TimelineNode[] = await res.json();
			this.renderTimelineLens(panel, nodes);
		} catch (_) {
			this.renderTimelineLens(panel, []);
		}
	}

	private renderTimelineLens(panel: HTMLElement, nodes: TimelineNode[]) {
		if (nodes.length === 0) {
			panel.innerHTML = `<div class="empty-state" role="status">${this.tr('atlas_timeline_empty', 'No timeline events yet.')}</div>`;
			return;
		}
		const items = nodes.map(n => {
			const date = new Date(n.created_at).toLocaleDateString();
			return `<li role="listitem" class="timeline-entry">
				<span class="timeline-date">${this.esc(date)}</span>
				<span class="timeline-label">${this.esc(n.label)}</span>
				<span class="type-badge" aria-label="${this.tr('atlas_node_type', 'Type')}: ${this.esc(n.type)}">${this.esc(n.type)}</span>
			</li>`;
		}).join('');
		panel.innerHTML = `<ul
			role="list"
			class="timeline-list"
			aria-label="${this.tr('aria_timeline_lens', 'Memory timeline')}"
		>${items}</ul>`;
	}

	// ── Decisions lens ─────────────────────────────────────────────────────

	private async loadDecisionsLens() {
		const panel = this.shadowRoot?.getElementById('lens-decisions');
		if (!panel) return;
		try {
			const res = await fetch('/api/atlas/decisions');
			if (!res.ok) throw new Error('fetch failed');
			const decisions: Decision[] = await res.json();
			this.renderDecisionsLens(panel, decisions);
		} catch (_) {
			this.renderDecisionsLens(panel, []);
		}
	}

	private renderDecisionsLens(panel: HTMLElement, decisions: Decision[]) {
		if (decisions.length === 0) {
			panel.innerHTML = `<div class="empty-state" role="status">${this.tr('atlas_decisions_empty', 'No decisions captured yet. Use Cmd/Ctrl+Shift+D to capture a decision.')}</div>`;
			return;
		}
		const open = decisions.filter(d => d.status === 'open');
		const revisit = decisions.filter(d => d.status === 'revisit_due');
		const resolved = decisions.filter(d => d.status === 'resolved');

		const renderCard = (d: Decision): string => {
			const isResolved = d.status === 'resolved';
			const toggleLabel = isResolved
				? this.tr('reopen_decision', 'Reopen')
				: this.tr('mark_resolved', 'Resolve');
			const nextStatus = isResolved ? 'open' : 'resolved';
			const revisitHtml = d.revisit_when
				? `<span class="decision-revisit"><span class="decision-revisit-label">${this.tr('revisit_when_label', 'Revisit when:')}</span> ${this.esc(d.revisit_when)}</span>`
				: '';
			return `<div class="decision-card" data-decision-id="${this.esc(d.id)}">
				<span class="decision-rationale">${this.esc(d.rationale)}</span>
				${revisitHtml}
				<span class="status-badge ${this.esc(d.status)}">${this.esc(d.status.replace('_', ' '))}</span>
				<button
					class="node-action-btn decision-toggle-btn"
					data-decision-id="${this.esc(d.id)}"
					data-next-status="${nextStatus}"
					aria-label="${this.esc(toggleLabel)}"
				>${toggleLabel}</button>
			</div>`;
		};

		const renderColumn = (label: string, ariaLabel: string, items: Decision[]): string => `<div
			class="decisions-column"
			role="region"
			aria-label="${this.esc(ariaLabel)}"
		>
			<div class="decisions-column-header">${this.esc(label)}</div>
			${items.length === 0 ? '<div class="empty-state" style="padding:0.75rem 0;">\u2014</div>' : items.map(renderCard).join('')}
		</div>`;

		panel.innerHTML = `<div class="decisions-columns">
			${renderColumn('Open', 'Open decisions', open)}
			${renderColumn('Revisit Due', 'Revisit due decisions', revisit)}
			${renderColumn('Resolved', 'Resolved decisions', resolved)}
		</div>`;

		panel.querySelectorAll<HTMLButtonElement>('.decision-toggle-btn').forEach(btn => {
			btn.addEventListener('click', async () => {
				const id = btn.dataset.decisionId;
				const nextStatus = btn.dataset.nextStatus;
				if (!id || !nextStatus) return;
				try {
					await fetch(`/api/atlas/decisions/${encodeURIComponent(id)}/status`, {
						method: 'PUT',
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({ status: nextStatus }),
					});
				} catch (_) { /* ignore */ }
				await this.loadDecisionsLens();
			});
		});
	}

	// ── Contradictions lens ─────────────────────────────────────────────────

	private async loadContradictionsLens() {
		const panel = this.shadowRoot?.getElementById('lens-contradictions');
		if (!panel) return;
		try {
			const res = await fetch('/api/atlas/contradictions');
			if (!res.ok) throw new Error('fetch failed');
			const contradictions: Contradiction[] = await res.json();
			this.renderContradictionsLens(panel, contradictions);
		} catch (_) {
			this.renderContradictionsLens(panel, []);
		}
	}

	private renderContradictionsLens(panel: HTMLElement, contradictions: Contradiction[]) {
		if (contradictions.length === 0) {
			panel.innerHTML = `<div class="empty-state" role="status">${this.tr('atlas_contradictions_empty', 'No contradictions detected yet.')}</div>`;
			return;
		}
		const filtered = this._contradictionsShowAll
			? contradictions
			: contradictions.filter(c => c.status === 'open');

		const cards = filtered.map(c => {
			const date = new Date(c.detected_at).toLocaleDateString();
			return `<div class="contradiction-card" data-contradiction-id="${this.esc(c.id)}">
				<div class="contradiction-nodes">${this.esc(c.primary_node_id)} &#8596; ${this.esc(c.opposing_node_id)}</div>
				<div class="contradiction-date">${this.esc(date)}</div>
				<span class="status-badge ${this.esc(c.status)}">${this.esc(c.status)}</span>
				<div class="contradiction-actions">
					<button
						class="node-action-btn contradiction-action-btn"
						data-contradiction-id="${this.esc(c.id)}"
						data-next-status="dismissed"
						aria-label="${this.tr('dismiss_contradiction', 'Dismiss')}"
					>${this.tr('dismiss_contradiction', 'Dismiss')}</button>
					<button
						class="node-action-btn contradiction-action-btn"
						data-contradiction-id="${this.esc(c.id)}"
						data-next-status="resolved"
						aria-label="${this.tr('resolve_contradiction', 'Resolve')}"
					>${this.tr('resolve_contradiction', 'Resolve')}</button>
				</div>
			</div>`;
		}).join('');

		const openBtnClass = !this._contradictionsShowAll ? ' active' : '';
		const allBtnClass = this._contradictionsShowAll ? ' active' : '';

		panel.innerHTML = `
			<div class="contradiction-filter" role="group" aria-label="${this.tr('aria_contradictions_lens', 'Contradictions lens')}">
				<button
					class="contradiction-filter-btn${openBtnClass}"
					id="contradiction-filter-open"
					aria-pressed="${!this._contradictionsShowAll}"
				>Open</button>
				<button
					class="contradiction-filter-btn${allBtnClass}"
					id="contradiction-filter-all"
					aria-pressed="${this._contradictionsShowAll}"
				>All</button>
			</div>
			<div aria-live="polite">
				${filtered.length === 0
					? `<div class="empty-state">${this.tr('atlas_contradictions_empty', 'No contradictions detected yet.')}</div>`
					: cards}
			</div>
		`;

		panel.querySelector<HTMLButtonElement>('#contradiction-filter-open')?.addEventListener('click', () => {
			this._contradictionsShowAll = false;
			this.renderContradictionsLens(panel, contradictions);
		});
		panel.querySelector<HTMLButtonElement>('#contradiction-filter-all')?.addEventListener('click', () => {
			this._contradictionsShowAll = true;
			this.renderContradictionsLens(panel, contradictions);
		});

		panel.querySelectorAll<HTMLButtonElement>('.contradiction-action-btn').forEach(btn => {
			btn.addEventListener('click', async () => {
				const id = btn.dataset.contradictionId;
				const nextStatus = btn.dataset.nextStatus;
				if (!id || !nextStatus) return;
				try {
					await fetch(`/api/atlas/contradictions/${encodeURIComponent(id)}/status`, {
						method: 'PUT',
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({ status: nextStatus }),
					});
				} catch (_) { /* ignore */ }
				await this.loadContradictionsLens();
			});
		});
	}

	// ── Diffs lens ──────────────────────────────────────────────────────────

	private async loadDiffsLens() {
		const panel = this.shadowRoot?.getElementById('lens-diffs');
		if (!panel) return;
		try {
			const res = await fetch('/api/atlas/diffs?limit=30');
			if (!res.ok) throw new Error('fetch failed');
			const diffs: DiffEntry[] = await res.json();
			this.renderDiffsLens(panel, diffs);
		} catch (_) {
			this.renderDiffsLens(panel, []);
		}
	}

	private renderDiffsLens(panel: HTMLElement, diffs: DiffEntry[]) {
		if (diffs.length === 0) {
			panel.innerHTML = `<div class="empty-state" role="status">${this.tr('atlas_diffs_empty', 'No changes recorded yet.')}</div>`;
			return;
		}
		const entries = diffs.map(d => {
			const date = new Date(d.created_at).toLocaleDateString();
			const nodeLink = d.node_id
				? `<button class="diff-link-btn" data-diff-node-id="${this.esc(d.node_id)}" aria-label="${this.tr('lens_list', 'List')}">${this.tr('lens_list', 'List')}</button>`
				: '';
			const spineLink = d.spine_id
				? `<button class="diff-link-btn" data-diff-spine-id="${this.esc(d.spine_id)}" aria-label="${this.tr('lens_spines', 'Spines')}">${this.tr('lens_spines', 'Spines')}</button>`
				: '';
			const linksHtml = (d.node_id || d.spine_id)
				? `<div class="diff-links">${nodeLink}${spineLink}</div>`
				: '';
			return `<article role="article" class="diff-entry">
				<div class="diff-header">
					<span class="diff-date-chip">${this.esc(date)}</span>
					<span class="diff-kind-badge">${this.esc(d.kind)}</span>
				</div>
				<span class="diff-summary">${this.esc(d.summary)}</span>
				${linksHtml}
			</article>`;
		}).join('');

		panel.innerHTML = `<div
			role="feed"
			class="diffs-feed"
			aria-label="${this.tr('aria_diffs_lens', 'Changes feed')}"
		>${entries}</div>`;

		panel.querySelectorAll<HTMLButtonElement>('.diff-link-btn[data-diff-node-id]').forEach(btn => {
			btn.addEventListener('click', () => this.switchLens('list'));
		});
		panel.querySelectorAll<HTMLButtonElement>('.diff-link-btn[data-diff-spine-id]').forEach(btn => {
			btn.addEventListener('click', () => this.switchLens('spines'));
		});
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
