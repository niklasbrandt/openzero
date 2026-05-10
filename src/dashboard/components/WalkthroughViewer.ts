import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';

interface WalkthroughStop {
	id: string;
	stop_order: number;
	node_id: string;
	spine_id: string;
	narration: string;
	payload: {
		source_refs?: string[];
		confidence?: number;
		suggested_action?: string | null;
		atlas_node_ref?: string;
	};
	node_label?: string;
	spine_label?: string;
}

interface Walkthrough {
	id: string | number;
	title: string;
	briefing_id?: string | null;
	payload?: {
		kind?: string;
		summary?: string;
		deep_link?: string;
	};
	created_at: string;
	stops: WalkthroughStop[];
}

export class WalkthroughViewer extends HTMLElement {
	private shadow: ShadowRoot;
	private t: Record<string, string> = {};
	private walkthrough: Walkthrough | null = null;
	private currentStopIndex = 0;
	private sourcesVisible = false;
	private _keydownHandler: ((e: KeyboardEvent) => void) | null = null;

	constructor() {
		super();
		this.shadow = this.attachShadow({ mode: 'open' });
	}

	private async loadTranslations(): Promise<void> {
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

	static get observedAttributes() { return ['walkthrough-id', 'embedded']; }

	attributeChangedCallback(name: string, _old: string, _new: string): void {
		if (name === 'walkthrough-id' && _new !== _old) {
			this.load();
		}
	}

	connectedCallback(): void {
		this._keydownHandler = (e: KeyboardEvent) => this.handleKeydown(e);
		window.addEventListener('keydown', this._keydownHandler);
		this.loadTranslations().then(async () => {
			const id = this.getAttribute('walkthrough-id');
			if (id) {
				await this.load();
			} else {
				this.render();
			}
		});
	}

	disconnectedCallback(): void {
		if (this._keydownHandler) {
			window.removeEventListener('keydown', this._keydownHandler);
			this._keydownHandler = null;
		}
	}

	private async load(): Promise<void> {
		const id = this.getAttribute('walkthrough-id');
		if (!id) {
			this.render();
			return;
		}
		this.shadow.innerHTML = '<p>Loading...</p>';
		try {
			const res = await fetch(`/api/atlas/walkthroughs/${id}`);
			if (!res.ok) {
				this.shadow.innerHTML = '<p>Walk-through not found.</p>';
				return;
			}
			this.walkthrough = await res.json() as Walkthrough;
			this.currentStopIndex = 0;
			this.sourcesVisible = false;
			this.render();
		} catch (_) {
			this.shadow.innerHTML = '<p>Walk-through not found.</p>';
		}
	}

	private render(): void {
		if (!this.walkthrough) {
			this.shadow.innerHTML = `
				<style>${ACCESSIBILITY_STYLES}</style>
				<p>${this.getAttribute('walkthrough-id') ? 'Walk-through not found.' : 'No walk-through loaded.'}</p>
			`;
			return;
		}

		const isEmbedded = this.hasAttribute('embedded');
		const wt = this.walkthrough;
		const stops = wt.stops || [];
		const total = stops.length;
		const currentStop = stops[this.currentStopIndex];
		const summary = wt.payload?.summary || '';
		const deepLink = `${window.location.origin}/atlas?walkthrough=${encodeURIComponent(String(wt.id))}`;

		const viewerRole = isEmbedded ? 'dialog' : 'region';
		const viewerLabel = this.tr('aria_walkthrough_viewer', 'Walk-through viewer');

		this.shadow.innerHTML = `
			<style>
				${ACCESSIBILITY_STYLES}

				:host {
					display: block;
				}

				.overlay {
					display: none;
				}

				:host([embedded]) .overlay {
					display: flex;
					position: fixed;
					inset: 0;
					z-index: 1000;
					align-items: center;
					justify-content: center;
					background: hsla(0, 0%, 0%, 0.6);
				}

				.walkthrough-viewer {
					display: flex;
					flex-direction: column;
					gap: 1rem;
					padding: 1.5rem;
					background: var(--surface-1, hsla(220, 20%, 12%, 1));
					border-radius: var(--radius-md, 0.5rem);
					color: var(--text-primary, hsla(220, 15%, 90%, 1));
				}

				:host([embedded]) .walkthrough-viewer {
					position: relative;
					max-width: 42rem;
					width: calc(100% - 2rem);
					max-height: 90vh;
					overflow-y: auto;
					padding-top: 3rem;
				}

				.close-btn {
					position: absolute;
					top: 0.75rem;
					right: 0.75rem;
					background: none;
					border: none;
					cursor: pointer;
					padding: 0.5rem;
					min-width: 44px;
					min-height: 44px;
					display: flex;
					align-items: center;
					justify-content: center;
					color: var(--text-secondary, hsla(220, 15%, 65%, 1));
					font-size: 1.25rem;
					border-radius: var(--radius-sm, 0.25rem);
					line-height: 1;
					transition: color 0.15s, background 0.15s;
				}

				.close-btn:hover,
				.close-btn:focus-visible {
					color: var(--text-primary, hsla(220, 15%, 90%, 1));
					background: var(--surface-2, hsla(220, 20%, 18%, 1));
					outline: 2px solid var(--accent-teal, hsla(174, 77%, 40%, 1));
					outline-offset: 2px;
				}

				.summary-section {
					background: var(--surface-2, hsla(220, 20%, 18%, 1));
					border-radius: var(--radius-sm, 0.25rem);
					padding: 0.875rem 1rem;
					border-left: 3px solid var(--accent-teal, hsla(174, 77%, 40%, 1));
				}

				.summary-title {
					font-size: 0.75rem;
					font-weight: 700;
					text-transform: uppercase;
					letter-spacing: 0.08em;
					color: var(--accent-teal, hsla(174, 77%, 40%, 1));
					margin: 0 0 0.375rem;
				}

				.summary-text {
					margin: 0;
					font-size: 0.9rem;
					line-height: 1.5;
					color: var(--text-secondary, hsla(220, 15%, 65%, 1));
				}

				.stop-container {
					display: flex;
					flex-direction: column;
					gap: 0.75rem;
				}

				.stop-header {
					font-size: 0.75rem;
					font-weight: 600;
					color: var(--text-tertiary, hsla(220, 15%, 50%, 1));
					text-transform: uppercase;
					letter-spacing: 0.06em;
					margin: 0;
				}

				.stop-label {
					font-size: 1.05rem;
					font-weight: 700;
					color: var(--text-primary, hsla(220, 15%, 90%, 1));
					margin: 0;
				}

				.stop-context {
					font-size: 0.875rem;
					line-height: 1.6;
					color: var(--text-secondary, hsla(220, 15%, 65%, 1));
					margin: 0;
				}

				.stop-action {
					background: var(--surface-3, hsla(220, 20%, 22%, 1));
					border-radius: var(--radius-sm, 0.25rem);
					padding: 0.625rem 0.875rem;
					font-size: 0.8rem;
					color: var(--accent-amber, hsla(38, 92%, 60%, 1));
					display: flex;
					gap: 0.5rem;
					align-items: flex-start;
				}

				.stop-action-label {
					font-weight: 700;
					white-space: nowrap;
				}

				.stop-sources-toggle {
					background: none;
					border: 1px solid var(--border-subtle, hsla(220, 20%, 25%, 1));
					color: var(--text-secondary, hsla(220, 15%, 65%, 1));
					cursor: pointer;
					padding: 0.375rem 0.75rem;
					min-height: 44px;
					min-width: 44px;
					border-radius: var(--radius-sm, 0.25rem);
					font-size: 0.8rem;
					display: inline-flex;
					align-items: center;
					gap: 0.375rem;
					align-self: flex-start;
					transition: color 0.15s, border-color 0.15s, background 0.15s;
				}

				.stop-sources-toggle:hover,
				.stop-sources-toggle:focus-visible {
					color: var(--text-primary, hsla(220, 15%, 90%, 1));
					border-color: var(--accent-teal, hsla(174, 77%, 40%, 1));
					outline: 2px solid var(--accent-teal, hsla(174, 77%, 40%, 1));
					outline-offset: 2px;
				}

				.sources-popover {
					background: var(--surface-2, hsla(220, 20%, 18%, 1));
					border: 1px solid var(--border-subtle, hsla(220, 20%, 25%, 1));
					border-radius: var(--radius-sm, 0.25rem);
					padding: 0.75rem 1rem;
					display: flex;
					flex-direction: column;
					gap: 0.375rem;
				}

				.sources-popover-title {
					font-size: 0.7rem;
					font-weight: 700;
					text-transform: uppercase;
					letter-spacing: 0.08em;
					color: var(--text-tertiary, hsla(220, 15%, 50%, 1));
					margin: 0 0 0.25rem;
				}

				.source-ref {
					font-size: 0.78rem;
					color: var(--text-secondary, hsla(220, 15%, 65%, 1));
					padding: 0.125rem 0;
					display: block;
				}

				.confidence-row {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					margin-top: 0.375rem;
				}

				.confidence-label {
					font-size: 0.7rem;
					font-weight: 700;
					text-transform: uppercase;
					letter-spacing: 0.06em;
					color: var(--text-tertiary, hsla(220, 15%, 50%, 1));
				}

				.confidence-bar-wrap {
					flex: 1;
					height: 4px;
					background: var(--surface-3, hsla(220, 20%, 22%, 1));
					border-radius: 2px;
					overflow: hidden;
				}

				.confidence-bar {
					height: 100%;
					background: var(--accent-teal, hsla(174, 77%, 40%, 1));
					border-radius: 2px;
					transition: width 0.3s;
				}

				.confidence-value {
					font-size: 0.75rem;
					color: var(--text-secondary, hsla(220, 15%, 65%, 1));
					min-width: 2.5rem;
					text-align: right;
				}

				.nav-bar {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					flex-wrap: wrap;
					margin-top: 0.25rem;
				}

				.nav-btn {
					min-height: 44px;
					min-width: 44px;
					padding: 0.5rem 1rem;
					background: var(--surface-2, hsla(220, 20%, 18%, 1));
					border: 1px solid var(--border-subtle, hsla(220, 20%, 25%, 1));
					color: var(--text-primary, hsla(220, 15%, 90%, 1));
					border-radius: var(--radius-sm, 0.25rem);
					cursor: pointer;
					font-size: 0.85rem;
					font-weight: 600;
					transition: background 0.15s, border-color 0.15s;
					display: inline-flex;
					align-items: center;
					gap: 0.375rem;
				}

				.nav-btn:hover:not(:disabled),
				.nav-btn:focus-visible {
					background: var(--surface-3, hsla(220, 20%, 22%, 1));
					border-color: var(--accent-teal, hsla(174, 77%, 40%, 1));
					outline: 2px solid var(--accent-teal, hsla(174, 77%, 40%, 1));
					outline-offset: 2px;
				}

				.nav-btn:disabled {
					opacity: 0.4;
					cursor: not-allowed;
				}

				.atlas-link {
					margin-left: auto;
					min-height: 44px;
					min-width: 44px;
					padding: 0.5rem 1rem;
					background: none;
					border: 1px solid var(--accent-teal, hsla(174, 77%, 40%, 1));
					color: var(--accent-teal, hsla(174, 77%, 40%, 1));
					border-radius: var(--radius-sm, 0.25rem);
					text-decoration: none;
					font-size: 0.8rem;
					font-weight: 600;
					display: inline-flex;
					align-items: center;
					gap: 0.375rem;
					transition: background 0.15s;
				}

				.atlas-link:hover,
				.atlas-link:focus-visible {
					background: var(--accent-teal-alpha, hsla(174, 77%, 40%, 0.12));
					outline: 2px solid var(--accent-teal, hsla(174, 77%, 40%, 1));
					outline-offset: 2px;
				}

				@media (prefers-reduced-motion: reduce) {
					.confidence-bar,
					.nav-btn,
					.close-btn,
					.stop-sources-toggle,
					.atlas-link {
						transition: none;
					}
				}

				@media (forced-colors: active) {
					.walkthrough-viewer {
						border: 1px solid ButtonText;
					}

					.summary-section {
						border-left-color: ButtonText;
					}

					.nav-btn:focus-visible,
					.close-btn:focus-visible,
					.stop-sources-toggle:focus-visible,
					.atlas-link:focus-visible {
						outline: 3px solid ButtonText;
					}
				}
			</style>
			${isEmbedded ? `
				<div class="overlay" id="wv-overlay">
					<div class="walkthrough-viewer" role="${viewerRole}" aria-label="${viewerLabel}" aria-modal="true">
						<button class="close-btn" id="wv-close" aria-label="${this.tr('walkthrough_close', 'Close walk-through')}">&#x2715;</button>
						${this.renderContent(total, currentStop, summary, deepLink)}
					</div>
				</div>
			` : `
				<div class="walkthrough-viewer" role="${viewerRole}" aria-label="${viewerLabel}">
					${this.renderContent(total, currentStop, summary, deepLink)}
				</div>
			`}
		`;

		const prevBtn = this.shadow.getElementById('wv-prev');
		const nextBtn = this.shadow.getElementById('wv-next');
		const toggleBtn = this.shadow.getElementById('wv-sources-toggle');
		const closeBtn = this.shadow.getElementById('wv-close');
		const overlay = this.shadow.getElementById('wv-overlay');

		prevBtn?.addEventListener('click', () => this.navigate(-1));
		nextBtn?.addEventListener('click', () => this.navigate(1));
		toggleBtn?.addEventListener('click', () => this.toggleSources());

		if (isEmbedded) {
			closeBtn?.addEventListener('click', () => this.dispatchClose());
			overlay?.addEventListener('click', (e: Event) => {
				if (e.target === overlay) this.dispatchClose();
			});
		}
	}

	private renderContent(total: number, currentStop: WalkthroughStop | undefined, summary: string, deepLink: string): string {
		return `
			${summary ? `
				<section class="summary-section" aria-label="${this.tr('walkthrough_summary', 'Walk-through summary')}">
					<p class="summary-title">${this.tr('walkthrough_summary', 'Walk-through summary')}</p>
					<p class="summary-text">${this.esc(summary)}</p>
				</section>
			` : ''}
			<div class="stop-container" aria-live="polite" aria-label="${this.tr('aria_walkthrough_stop', 'Walk-through stop')}">
				${currentStop ? this.renderStop(currentStop, this.currentStopIndex, total) : `<p>${this.tr('walkthrough_stop', 'Stop')} — no stops available.</p>`}
			</div>
			<nav class="nav-bar" aria-label="Navigation">
				<button class="nav-btn" id="wv-prev" ${this.currentStopIndex <= 0 ? 'disabled' : ''} aria-label="${this.tr('walkthrough_prev', 'Previous stop')}">&#8592; ${this.tr('walkthrough_prev', 'Previous stop')}</button>
				<button class="nav-btn" id="wv-next" ${this.currentStopIndex >= total - 1 ? 'disabled' : ''} aria-label="${this.tr('walkthrough_next', 'Next stop')}">${this.tr('walkthrough_next', 'Next stop')} &#8594;</button>
				<a class="atlas-link" href="${this.esc(deepLink)}" target="_blank" rel="noopener noreferrer" aria-label="${this.tr('walkthrough_open_atlas', 'Open in Atlas')}">${this.tr('walkthrough_open_atlas', 'Open in Atlas')} &#8599;</a>
			</nav>
		`;
	}

	private renderStop(stop: WalkthroughStop, index: number, total: number): string {
		const label = stop.node_label || stop.payload?.atlas_node_ref || '';
		const narration = stop.narration || '';
		const sourceRefs = stop.payload?.source_refs || [];
		const confidence = stop.payload?.confidence ?? null;
		const suggestedAction = stop.payload?.suggested_action ?? null;
		const pct = confidence !== null ? Math.round(confidence * 100) : null;
		const hasSourcesSection = sourceRefs.length > 0 || confidence !== null;

		return `
			<p class="stop-header">${this.tr('walkthrough_stop', 'Stop')} ${index + 1} ${this.tr('walkthrough_of', 'of')} ${total}</p>
			<p class="stop-label">${this.esc(label)}</p>
			<p class="stop-context">${this.esc(narration)}</p>
			${suggestedAction ? `
				<div class="stop-action">
					<span class="stop-action-label">${this.tr('walkthrough_action', 'Suggested action')}:</span>
					<span>${this.esc(suggestedAction)}</span>
				</div>
			` : ''}
			${hasSourcesSection ? `
				<button class="stop-sources-toggle" id="wv-sources-toggle" aria-expanded="${this.sourcesVisible}" aria-label="${this.tr('walkthrough_sources', 'Sources')}">
					${this.tr('walkthrough_sources', 'Sources')}${sourceRefs.length > 0 ? ` (${sourceRefs.length})` : ''} ${this.sourcesVisible ? '&#9650;' : '&#9660;'}
				</button>
				${this.sourcesVisible ? `
					<div class="sources-popover" role="region" aria-label="${this.tr('walkthrough_sources', 'Sources')}">
						<p class="sources-popover-title">${this.tr('walkthrough_sources', 'Sources')}</p>
						${sourceRefs.map(ref => `<span class="source-ref">${this.esc(ref)}</span>`).join('')}
						${pct !== null ? `
							<div class="confidence-row">
								<span class="confidence-label">${this.tr('walkthrough_confidence', 'Confidence')}</span>
								<div class="confidence-bar-wrap" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100" aria-label="${this.tr('walkthrough_confidence', 'Confidence')} ${pct}%">
									<div class="confidence-bar" style="width: ${pct}%"></div>
								</div>
								<span class="confidence-value">${pct}%</span>
							</div>
						` : ''}
					</div>
				` : ''}
			` : ''}
		`;
	}

	private navigate(delta: number): void {
		const stops = this.walkthrough?.stops || [];
		const next = this.currentStopIndex + delta;
		this.currentStopIndex = Math.max(0, Math.min(stops.length - 1, next));
		this.sourcesVisible = false;
		this.render();
	}

	private toggleSources(): void {
		this.sourcesVisible = !this.sourcesVisible;
		this.render();
	}

	private handleKeydown(e: KeyboardEvent): void {
		const root = this.shadowRoot;
		const hasFocus = root ? root.contains(document.activeElement) : false;
		const isHost = document.activeElement === this;
		if (!hasFocus && !isHost) return;

		switch (e.key) {
			case 'ArrowLeft':
			case 'k':
			case 'K':
				e.preventDefault();
				this.navigate(-1);
				break;
			case 'ArrowRight':
			case 'j':
			case 'J':
				e.preventDefault();
				this.navigate(1);
				break;
			case '?':
				e.preventDefault();
				this.toggleSources();
				break;
		}
	}

	private dispatchClose(): void {
		this.dispatchEvent(new CustomEvent('walkthrough-close', { bubbles: true, composed: true }));
	}

	private esc(str: string): string {
		return str
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#39;');
	}
}

if (!customElements.get('walkthrough-viewer')) {
	customElements.define('walkthrough-viewer', WalkthroughViewer);
}
