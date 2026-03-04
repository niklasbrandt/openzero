import { BUTTON_STYLES } from '../services/buttonStyles';

interface MemoryItem {
	id: string | null;
	text: string;
	type: 'memory' | 'profile' | 'project';
	score?: number | null;
	stored_at?: string | null;
}

type Mode = 'search' | 'browse';

export class MemorySearch extends HTMLElement {
	private t: Record<string, string> = {};
	private mode: Mode = 'search';
	private searchResults: MemoryItem[] = [];
	private browseItems: MemoryItem[] = [];
	private browseTotal = 0;
	private browseOffset = 0;
	private browseLoading = false;
	private searchLoading = false;
	private pendingDelete = new Set<string>();

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	private async loadTranslations() {
		try {
			const res = await fetch('/api/dashboard/translations');
			if (res.ok) this.t = await res.json();
		} catch (_) { }
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] || fallback;
	}

	connectedCallback() {
		this.loadTranslations().then(() => this.render());
	}

	// ── Search mode ─────────────────────────────────────────────────────────

	async runSearch(query: string) {
		if (!query.trim()) return;
		this.searchLoading = true;
		this.renderResultsPanel();
		try {
			const res = await fetch(`/api/dashboard/memory/search?query=${encodeURIComponent(query)}`);
			const data = await res.json();
			this.searchResults = data.results ?? [];
		} catch {
			this.searchResults = [];
		}
		this.searchLoading = false;
		this.renderResultsPanel();
	}

	// ── Browse mode ─────────────────────────────────────────────────────────

	async loadBrowsePage(reset = false) {
		if (this.browseLoading) return;
		if (reset) {
			this.browseItems = [];
			this.browseOffset = 0;
		}
		this.browseLoading = true;
		this.renderResultsPanel();
		try {
			const res = await fetch(`/api/dashboard/memory/list?offset=${this.browseOffset}&limit=50`);
			const data = await res.json();
			const newItems: MemoryItem[] = (data.items ?? []).map((i: any) => ({
id: i.id,
text: i.text,
type: 'memory' as const,
stored_at: i.stored_at ?? null,
}));
			this.browseItems = [...this.browseItems, ...newItems];
			this.browseTotal = data.total ?? 0;
			// next_offset may be a number (qdrant page token) or null when exhausted
			this.browseOffset = typeof data.next_offset === 'number' ? data.next_offset : this.browseOffset + newItems.length;
		} catch {
			// leave list as-is on error
		}
		this.browseLoading = false;
		this.renderResultsPanel();
	}

	// ── Delete ──────────────────────────────────────────────────────────────

	private async deleteMemory(id: string) {
		// First click → arm for confirmation
		if (!this.pendingDelete.has(id)) {
			this.pendingDelete.add(id);
			this.renderResultsPanel();
			// Auto-disarm after 4 s if no second click
			setTimeout(() => {
				if (this.pendingDelete.has(id)) {
					this.pendingDelete.delete(id);
					this.renderResultsPanel();
				}
			}, 4000);
			return;
		}
		// Second click → confirmed, execute delete
		this.pendingDelete.delete(id);
		try {
			const res = await fetch(`/api/dashboard/memory/${encodeURIComponent(id)}`, { method: 'DELETE' });
			if (res.ok) {
				this.searchResults = this.searchResults.filter(r => r.id !== id);
				this.browseItems   = this.browseItems.filter(b => b.id !== id);
				if (this.browseTotal > 0) this.browseTotal--;
			}
		} catch { /* silent */ }
		this.renderResultsPanel();
	}

	// ── Render helpers ───────────────────────────────────────────────────────

	private formatDate(iso: string | null | undefined): string {
		if (!iso) return '';
		try {
			return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', year: '2-digit' });
		} catch { return ''; }
	}

	private escapeHtml(s: string): string {
		return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
	}

	private renderItem(item: MemoryItem, idx: number): string {
		const canDelete =  git add src/dashboard/components/ChatPrompt.ts && git commit -m "chat: contrast-aware text color for agent bubbles (WCAG luminance)" && git push origin main && bash scripts/sync.sh 2>&1 | tail -20item.id && item.type === 'memory';
		const isPending = canDelete && this.pendingDelete.has(item.id!);
		const typeIcon = item.type === 'profile' ? '👤' : item.type === 'project' ? '🌳' : '🧠';
		const scoreLabel = item.score != null
			? `<span class="score" aria-label="${this.tr('aria_similarity_score', 'Similarity score')}: ${item.score}">${(item.score * 100).toFixed(0)}%</span>`
			: '';
		const dateLabel = item.stored_at
			? `<span class="item-date">${this.formatDate(item.stored_at)}</span>`
			: '';

		const deleteBtn = canDelete ? `
			<button
				class="delete-btn${isPending ? ' pending' : ''}"
				data-id="${item.id}"
				aria-label="${isPending
? this.tr('aria_confirm_unlearn', 'Confirm unlearn — click again to permanently delete')
: this.tr('aria_unlearn', 'Unlearn this memory')}"
				title="${isPending
? this.tr('confirm_unlearn', 'Click again to confirm deletion')
: this.tr('unlearn', 'Unlearn')}"
			>
				${isPending
? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true" focusable="false"><polyline points="20 6 9 17 4 12"/></svg><span>${this.tr('confirm', 'Confirm?')}</span>`
					: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>`
				}
			</button>` : '';

		return `
			<li class="result-item${isPending ? ' item-pending' : ''}" role="listitem">
				<span class="item-icon" aria-hidden="true">${typeIcon}</span>
				<span class="item-body">
					<span class="item-text" id="mem-${idx}">${this.escapeHtml(item.text)}</span>
					<span class="item-meta" aria-hidden="true">${scoreLabel}${dateLabel}</span>
				</span>
				${deleteBtn}
			</li>`;
	}

	private renderResultsPanel() {
		const panel = this.shadowRoot?.querySelector('#results-panel');
		if (!panel) return;

		if (this.mode === 'search') {
			if (this.searchLoading) {
				panel.innerHTML = `<div class="status-msg" role="status" aria-live="polite">${this.tr('searching', 'Searching\u2026')}</div>`;
				return;
			}
			const query = this.shadowRoot?.querySelector<HTMLInputElement>('#memory-search-input')?.value.trim();
			if (!this.searchResults.length) {
				panel.innerHTML = query
					? `<div class="status-msg" role="status">${this.tr('no_results', 'No memories found.')}</div>`
					: '';
				return;
			}
			panel.innerHTML = `
				<p class="results-count" aria-live="polite">
					${this.searchResults.length} ${this.tr('results', 'result(s)')}
					<span class="sr-only"> ${this.tr('aria_found', 'found for your query')}</span>
				</p>
				<ul role="list" aria-label="${this.tr('aria_memory_results', 'Memory search results')}" class="results-list">
					${this.searchResults.map((item, i) => this.renderItem(item, i)).join('')}
				</ul>`;

		} else {
			// Browse mode
			if (this.browseLoading && this.browseItems.length === 0) {
				panel.innerHTML = `<div class="status-msg" role="status" aria-live="polite">${this.tr('loading', 'Loading\u2026')}</div>`;
				return;
			}
			const hasMore = this.browseItems.length < this.browseTotal;
			panel.innerHTML = `
				<p class="results-count" aria-live="polite">
					${this.browseItems.length} / ${this.browseTotal} ${this.tr('memories', 'memories')}
				</p>
				<ul role="list" aria-label="${this.tr('aria_all_memories', 'All stored memories')}" class="results-list">
					${this.browseItems.map((item, i) => this.renderItem(item, i)).join('')}
				</ul>
				${hasMore ? `<button id="load-more-btn" class="load-more-btn" aria-label="${this.tr('aria_load_more', 'Load more memories')}">
					${this.browseLoading ? this.tr('loading', 'Loading\u2026') : this.tr('load_more', 'Load more')}
				</button>` : ''}
				${this.browseLoading && this.browseItems.length > 0
? `<div class="status-msg" role="status" aria-live="polite">${this.tr('loading', 'Loading\u2026')}</div>`
					: ''}`;

			this.shadowRoot?.querySelector('#load-more-btn')
				?.addEventListener('click', () => this.loadBrowsePage());
		}

		// Bind delete buttons
		this.shadowRoot?.querySelectorAll<HTMLButtonElement>('.delete-btn').forEach(btn => {
			btn.addEventListener('click', () => {
				const id = btn.dataset.id;
				if (id) this.deleteMemory(id);
			});
		});
	}

	private switchMode(newMode: Mode) {
		this.mode = newMode;
		this.shadowRoot?.querySelectorAll<HTMLButtonElement>('.tab-btn').forEach(btn => {
			const active = btn.dataset.mode === newMode;
			btn.setAttribute('aria-selected', active ? 'true' : 'false');
			btn.classList.toggle('active', active);
		});
		const searchPanel = this.shadowRoot?.querySelector<HTMLElement>('#search-panel');
		const browsePanel = this.shadowRoot?.querySelector<HTMLElement>('#browse-panel');
		if (searchPanel) searchPanel.hidden = newMode !== 'search';
		if (browsePanel) browsePanel.hidden = newMode !== 'browse';
		this.renderResultsPanel();
		if (newMode === 'browse' && this.browseItems.length === 0) {
			this.loadBrowsePage(true);
		}
	}

	render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
			<style>
				${BUTTON_STYLES}
				:host { display: block; }
				h2 {
					font-size: 1.5rem;
					font-weight: bold;
					margin: 0 0 1rem 0;
					color: #fff;
					letter-spacing: 0.02em;
					display: flex;
					align-items: center;
					gap: 0.5rem;
				}
				.icon {
					display: inline-flex;
					width: 28px; height: 28px;
					background: linear-gradient(135deg, #8b5cf6 0%, #14B8A6 100%);
					border-radius: 0.4rem;
					align-items: center;
					justify-content: center;
					flex-shrink: 0;
				}
				.subtitle {
					font-size: 0.65rem;
					font-weight: 400;
					color: rgba(255,255,255,0.3);
					margin-left: auto;
					text-transform: uppercase;
					letter-spacing: 0.1em;
				}
				.tabs {
					display: flex;
					gap: 0.25rem;
					margin-bottom: 1rem;
					background: rgba(255,255,255,0.04);
					border-radius: 0.75rem;
					padding: 0.25rem;
				}
				.tab-btn {
					flex: 1;
					background: none;
					border: none;
					color: rgba(255,255,255,0.5);
					font-family: inherit;
					font-size: 0.8rem;
					font-weight: 600;
					padding: 0.4rem 0.75rem;
					border-radius: 0.55rem;
					cursor: pointer;
					transition: background 0.18s, color 0.18s;
					letter-spacing: 0.04em;
					text-transform: uppercase;
				}
				.tab-btn.active, .tab-btn[aria-selected="true"] {
					background: rgba(255,255,255,0.1);
					color: #fff;
				}
				.tab-btn:focus-visible {
					outline: 2px solid #14B8A6;
					outline-offset: 2px;
				}
				.tab-btn:hover:not(.active) {
					color: rgba(255,255,255,0.75);
					background: rgba(255,255,255,0.06);
				}
				label {
					display: block;
					font-size: 0.7rem;
					font-weight: 600;
					color: rgba(255,255,255,0.5);
					text-transform: uppercase;
					letter-spacing: 0.06em;
					margin-bottom: 0.25rem;
				}
				.search-row {
					display: flex;
					gap: 0.5rem;
					align-items: flex-end;
					margin-bottom: 0.5rem;
				}
				.input-group { flex: 1; }
				input[type="search"] {
					width: 100%;
					background: rgba(0,0,0,0.2);
					border: 1px solid rgba(255,255,255,0.08);
					border-radius: 0.75rem;
					padding: 0.6rem 1rem;
					color: #fff;
					font-family: inherit;
					font-size: 0.9rem;
					box-sizing: border-box;
					transition: border-color 0.2s, background 0.2s;
				}
				input[type="search"]:focus {
					outline: none;
					border-color: rgba(20,184,166,0.4);
					background: rgba(0,0,0,0.28);
				}
				input[type="search"]:focus-visible {
					outline: 2px solid #14B8A6;
					outline-offset: 2px;
				}
				.results-list {
					list-style: none;
					padding: 0;
					margin: 0;
					display: flex;
					flex-direction: column;
					gap: 0.4rem;
					max-height: 480px;
					overflow-y: auto;
					scrollbar-width: thin;
					scrollbar-color: rgba(255,255,255,0.1) transparent;
				}
				.results-list::-webkit-scrollbar { width: 4px; }
				.results-list::-webkit-scrollbar-track { background: transparent; }
				.results-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
				.result-item {
					display: flex;
					align-items: flex-start;
					gap: 0.5rem;
					padding: 0.65rem 0.75rem;
					background: rgba(255,255,255,0.03);
					border-radius: 0.6rem;
					border-left: 3px solid rgba(139,92,246,0.5);
					transition: background 0.15s, border-color 0.15s;
				}
				.result-item:hover { background: rgba(255,255,255,0.055); }
				.result-item.item-pending {
					border-left-color: rgba(239,68,68,0.7);
					background: rgba(239,68,68,0.05);
				}
				.item-icon {
					font-size: 1rem;
					flex-shrink: 0;
					line-height: 1.4;
					margin-top: 0.05rem;
				}
				.item-body {
					flex: 1;
					min-width: 0;
					display: flex;
					flex-direction: column;
					gap: 0.2rem;
				}
				.item-text {
					font-size: 0.875rem;
					line-height: 1.5;
					color: rgba(255,255,255,0.88);
					word-break: break-word;
				}
				.item-meta {
					display: flex;
					gap: 0.5rem;
					align-items: center;
				}
				.score {
					font-size: 0.65rem;
					font-weight: 700;
					background: rgba(20,184,166,0.15);
					color: #5eead4;
					padding: 0.1rem 0.4rem;
					border-radius: 0.3rem;
					letter-spacing: 0.03em;
				}
				.item-date {
					font-size: 0.65rem;
					color: rgba(255,255,255,0.3);
				}
				.delete-btn {
					flex-shrink: 0;
					display: flex;
					align-items: center;
					justify-content: center;
					gap: 0.3rem;
					background: none;
					border: 1px solid rgba(255,255,255,0.1);
					border-radius: 0.45rem;
					color: rgba(255,255,255,0.3);
					padding: 0.3rem 0.5rem;
					font-size: 0.7rem;
					font-family: inherit;
					cursor: pointer;
					transition: background 0.15s, color 0.15s, border-color 0.15s;
					min-height: 44px;
					min-width: 44px;
				}
				.delete-btn:hover {
					color: rgba(239,68,68,0.9);
					border-color: rgba(239,68,68,0.4);
					background: rgba(239,68,68,0.08);
				}
				.delete-btn.pending {
					color: #f87171;
					border-color: rgba(239,68,68,0.6);
					background: rgba(239,68,68,0.12);
					padding: 0.3rem 0.65rem;
					gap: 0.4rem;
					animation: pulse-warn 0.6s ease infinite alternate;
				}
				.delete-btn:focus-visible {
					outline: 2px solid #14B8A6;
					outline-offset: 2px;
				}
				@keyframes pulse-warn {
					from { box-shadow: 0 0 0 0 rgba(239,68,68,0); }
					to   { box-shadow: 0 0 0 4px rgba(239,68,68,0.2); }
				}
				.status-msg {
					color: rgba(255,255,255,0.4);
					font-size: 0.85rem;
					padding: 1rem 0.25rem;
					text-align: center;
				}
				.results-count {
					font-size: 0.7rem;
					color: rgba(255,255,255,0.35);
					margin: 0 0 0.6rem 0;
					text-transform: uppercase;
					letter-spacing: 0.06em;
				}
				.load-more-btn {
					width: 100%;
					margin-top: 0.75rem;
					background: rgba(255,255,255,0.05);
					border: 1px solid rgba(255,255,255,0.1);
					border-radius: 0.65rem;
					color: rgba(255,255,255,0.6);
					font-family: inherit;
					font-size: 0.8rem;
					font-weight: 600;
					padding: 0.6rem;
					cursor: pointer;
					transition: background 0.15s, color 0.15s;
				}
				.load-more-btn:hover {
					background: rgba(255,255,255,0.09);
					color: #fff;
				}
				.load-more-btn:focus-visible {
					outline: 2px solid #14B8A6;
					outline-offset: 2px;
				}
				.hint {
					font-size: 0.68rem;
					color: rgba(255,255,255,0.3);
					margin: 0 0 0.75rem 0;
					line-height: 1.5;
				}
				.sr-only {
					position: absolute;
					width: 1px; height: 1px;
					padding: 0; margin: -1px;
					overflow: hidden;
					clip: rect(0,0,0,0);
					white-space: nowrap;
					border: 0;
				}
				@media (prefers-reduced-motion: reduce) {
					.tab-btn, input[type="search"], .result-item,
					.delete-btn, .load-more-btn { transition: none; }
					.delete-btn.pending { animation: none; }
				}
				@media (forced-colors: active) {
					.result-item { border-left-color: Highlight; }
					.delete-btn.pending { border-color: LinkText; color: LinkText; }
				}
			</style>

			<div class="card">
				<h2>
					<span class="icon" aria-hidden="true">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"
							stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
							<ellipse cx="12" cy="5" rx="9" ry="3"/>
							<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
							<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
						</svg>
					</span>
					${this.tr('memory_vault', 'Memory Vault')}
					<span class="subtitle" aria-hidden="true">Qdrant</span>
				</h2>

				<div role="tablist" aria-label="${this.tr('aria_memory_tabs', 'Memory view tabs')}" class="tabs">
					<button role="tab" class="tab-btn active" data-mode="search"
						aria-selected="true" aria-controls="search-panel" id="tab-search">
						${this.tr('search', 'Search')}
					</button>
					<button role="tab" class="tab-btn" data-mode="browse"
						aria-selected="false" aria-controls="browse-panel" id="tab-browse">
						${this.tr('browse_all', 'Browse All')}
					</button>
				</div>

				<section id="search-panel" role="tabpanel" aria-labelledby="tab-search">
					<form class="search-row" role="search"
						aria-label="${this.tr('aria_search_memory', 'Search semantic memory')}"
						onsubmit="return false;">
						<div class="input-group">
							<label for="memory-search-input">${this.tr('search_label', 'Search query')}</label>
							<input
								type="search"
								id="memory-search-input"
								name="query"
								placeholder="${this.tr('search_placeholder', 'Search your memories\u2026')}"
								autocomplete="off"
								aria-describedby="search-hint"
							/>
						</div>
						<button id="search-btn" type="submit"
							aria-label="${this.tr('search', 'Search')} ${this.tr('memories', 'memories')}">
							${this.tr('search', 'Search')}
						</button>
					</form>
					<p id="search-hint" class="hint">${this.tr('search_hint', 'Semantic similarity search across all stored memories')}</p>
				</section>

				<section id="browse-panel" role="tabpanel" aria-labelledby="tab-browse" hidden>
					<p class="hint">${this.tr('browse_hint', 'All memories stored in Qdrant. Click the trash icon once to arm, then again to permanently unlearn.')}</p>
				</section>

				<div id="results-panel" aria-live="polite" aria-relevant="additions removals text"></div>
			</div>
		`;

		// Tab keyboard & click handling
		this.shadowRoot.querySelectorAll<HTMLButtonElement>('.tab-btn').forEach(btn => {
			btn.addEventListener('click', () => {
				const m = btn.dataset.mode as Mode;
				if (m && m !== this.mode) this.switchMode(m);
			});
			btn.addEventListener('keydown', (e: KeyboardEvent) => {
				if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
					e.preventDefault();
					const tabs = [...(this.shadowRoot?.querySelectorAll<HTMLButtonElement>('.tab-btn') ?? [])];
					const idx = tabs.indexOf(btn);
					const next = tabs[(idx + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
					next?.focus();
					next?.click();
				}
			});
		});

		// Search
		this.shadowRoot.querySelector('#search-btn')?.addEventListener('click', () => {
			const q = this.shadowRoot?.querySelector<HTMLInputElement>('#memory-search-input')?.value ?? '';
			this.runSearch(q);
		});
		this.shadowRoot.querySelector<HTMLInputElement>('#memory-search-input')
			?.addEventListener('keydown', (e: KeyboardEvent) => {
				if (e.key === 'Enter') {
					e.preventDefault();
					this.runSearch((e.target as HTMLInputElement).value);
				}
			});
	}
}

customElements.define('memory-search', MemorySearch);
