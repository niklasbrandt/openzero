import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';

interface DiffEntry {
	id: string;
	kind: string;
	summary: string;
	created_at: string;
	node_id?: string | null;
	spine_id?: string | null;
}

export class DiffRibbon extends HTMLElement {
	private t: Record<string, string> = {};
	private diffs: DiffEntry[] = [];
	private dismissed: Set<string> = new Set();
	private intervalId: ReturnType<typeof setInterval> | null = null;

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
		this.loadTranslations().then(() => {
			this.fetchDiffs();
			this.intervalId = setInterval(() => this.fetchDiffs(), 5 * 60 * 1000);
		});
	}

	disconnectedCallback() {
		if (this.intervalId !== null) {
			clearInterval(this.intervalId);
			this.intervalId = null;
		}
	}

	private async fetchDiffs() {
		try {
			const res = await fetch('/api/atlas/diffs?limit=5');
			if (!res.ok) { this.hide(); return; }
			const data = await res.json();
			this.diffs = Array.isArray(data) ? data : (data.diffs ?? []);
		} catch (_) {
			this.hide();
			return;
		}
		this.render();
	}

	private hide() {
		(this as HTMLElement).style.display = 'none';
	}

	private render() {
		const visible = this.diffs.filter(d => !this.dismissed.has(d.id));

		if (visible.length === 0) {
			this.hide();
			return;
		}

		(this as HTMLElement).style.display = '';

		const shadow = this.shadowRoot!;
		shadow.innerHTML = `
			<style>
				${ACCESSIBILITY_STYLES}

				:host {
					display: block;
					width: 100%;
				}

				#ribbon {
					display: flex;
					gap: 0.75rem;
					align-items: center;
					flex-wrap: wrap;
					padding: 0.5rem 1rem;
					background: var(--diff-ribbon-bg, hsla(173, 80%, 10%, 0.6));
					border-bottom: 1px solid var(--diff-ribbon-border, hsla(173, 80%, 40%, 0.2));
				}

				#ribbon-entries {
					display: flex;
					gap: 0.5rem;
					flex-wrap: wrap;
					align-items: center;
					flex: 1;
					min-width: 0;
				}

				.entry {
					display: inline-flex;
					align-items: center;
					gap: 0.4rem;
					background: var(--diff-ribbon-entry-bg, hsla(173, 80%, 40%, 0.1));
					border-radius: 0.5rem;
					padding: 0.25rem 0.5rem;
					font-size: 0.8rem;
					cursor: pointer;
					color: var(--text-primary, hsla(0, 0%, 90%, 1));
					border: 1px solid transparent;
					transition: border-color 0.15s ease;
				}

				.entry:hover,
				.entry:focus-visible {
					border-color: var(--diff-ribbon-border, hsla(173, 80%, 40%, 0.4));
					outline: none;
				}

				.entry:focus-visible {
					outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				.kind-badge {
					font-size: 0.65rem;
					text-transform: uppercase;
					letter-spacing: 0.05em;
					background: var(--accent-color, hsla(173, 80%, 40%, 1));
					color: hsla(0, 0%, 0%, 1);
					border-radius: 0.25rem;
					padding: 0.1rem 0.3rem;
					white-space: nowrap;
					flex-shrink: 0;
				}

				.summary {
					white-space: nowrap;
					overflow: hidden;
					text-overflow: ellipsis;
					max-width: 24rem;
				}

				.dismiss-btn {
					background: transparent;
					border: none;
					cursor: pointer;
					color: var(--text-muted, hsla(0, 0%, 60%, 1));
					font-size: 1rem;
					min-width: 2rem;
					min-height: 2rem;
					padding: 0;
					display: inline-flex;
					align-items: center;
					justify-content: center;
					border-radius: 0.25rem;
					flex-shrink: 0;
					line-height: 1;
				}

				.dismiss-btn:hover {
					color: var(--text-primary, hsla(0, 0%, 90%, 1));
				}

				.dismiss-btn:focus-visible {
					outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				#ribbon-dismiss-all {
					background: transparent;
					border: 1px solid var(--diff-ribbon-border, hsla(173, 80%, 40%, 0.2));
					cursor: pointer;
					color: var(--text-muted, hsla(0, 0%, 60%, 1));
					font-size: 0.75rem;
					padding: 0.25rem 0.6rem;
					border-radius: 0.35rem;
					min-height: 2rem;
					white-space: nowrap;
					flex-shrink: 0;
					margin-left: auto;
				}

				#ribbon-dismiss-all:hover {
					color: var(--text-primary, hsla(0, 0%, 90%, 1));
					border-color: var(--diff-ribbon-border, hsla(173, 80%, 40%, 0.5));
				}

				#ribbon-dismiss-all:focus-visible {
					outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1));
					outline-offset: 2px;
				}

				@media (prefers-reduced-motion: reduce) {
					.entry,
					.dismiss-btn,
					#ribbon-dismiss-all {
						transition: none !important;
					}
				}

				@media (forced-colors: active) {
					#ribbon {
						border-bottom: 1px solid ButtonText;
					}
					.kind-badge {
						background: ButtonText;
						color: ButtonFace;
					}
					.entry {
						border: 1px solid ButtonText;
					}
					.dismiss-btn,
					#ribbon-dismiss-all {
						border: 1px solid ButtonText;
					}
				}
			</style>

			<div
				id="ribbon"
				role="status"
				aria-live="polite"
				aria-label="${this.tr('aria_diff_ribbon', 'Recent changes')}"
			>
				<div id="ribbon-entries"></div>
				<button
					id="ribbon-dismiss-all"
					type="button"
					aria-label="${this.tr('dismiss_all', 'Dismiss all')}"
				>${this.tr('dismiss_all', 'Dismiss all')}</button>
			</div>
		`;

		const entriesEl = shadow.getElementById('ribbon-entries')!;
		visible.forEach(diff => {
			const entry = document.createElement('div');
			entry.className = 'entry';
			entry.setAttribute('tabindex', '0');
			entry.setAttribute('role', 'button');
			entry.setAttribute('aria-label', `${this.tr('aria_diff_ribbon_entry', 'Change entry')}: ${diff.kind} — ${diff.summary}`);

			const truncated = diff.summary.length > 80
				? diff.summary.slice(0, 80) + '\u2026'
				: diff.summary;

			entry.innerHTML = `
				<span class="kind-badge">${this._escapeHtml(diff.kind)}</span>
				<span class="summary">${this._escapeHtml(truncated)}</span>
				<button
					class="dismiss-btn"
					type="button"
					aria-label="${this.tr('aria_dismiss_diff', 'Dismiss this change')}"
					data-id="${this._escapeAttr(diff.id)}"
				>&times;</button>
			`;

			// Navigate on click (not on dismiss)
			entry.addEventListener('click', (e: Event) => {
				const target = e.target as HTMLElement;
				if (target.closest('.dismiss-btn')) return;
				this.dispatchEvent(new CustomEvent('diff-ribbon-navigate', {
					bubbles: true,
					composed: true,
					detail: {
						node_id: diff.node_id ?? null,
						spine_id: diff.spine_id ?? null,
						kind: diff.kind,
					},
				}));
			});

			// Keyboard activation for the entry div
			entry.addEventListener('keydown', (e: KeyboardEvent) => {
				if (e.key === 'Enter' || e.key === ' ') {
					e.preventDefault();
					entry.click();
				}
			});

			// Dismiss button
			const dismissBtn = entry.querySelector('.dismiss-btn') as HTMLButtonElement;
			dismissBtn.addEventListener('click', (e: Event) => {
				e.stopPropagation();
				this.dismissEntry(diff.id);
			});

			entriesEl.appendChild(entry);
		});

		const dismissAll = shadow.getElementById('ribbon-dismiss-all') as HTMLButtonElement;
		dismissAll.addEventListener('click', () => this.dismissAll());
	}

	private dismissEntry(id: string) {
		this.dismissed.add(id);
		this.render();
	}

	private dismissAll() {
		this.diffs.forEach(d => this.dismissed.add(d.id));
		this.hide();
	}

	private _escapeHtml(s: string): string {
		return s
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#39;');
	}

	private _escapeAttr(s: string): string {
		return s.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
	}
}

customElements.define('diff-ribbon', DiffRibbon);
