export class MemorySearch extends HTMLElement {
	private t: Record<string, string> = {};

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

	async search(query: string) {
		const resultsContainer = this.shadowRoot?.querySelector('#results');
		if (resultsContainer) resultsContainer.innerHTML = 'Searching...';

		try {
			const response = await fetch(`/api/dashboard/memory/search?query=${encodeURIComponent(query)}`);
			const data = await response.json();
			this.displayResults(data.results);
		} catch (e) {
			console.error('Search failed', e);
		}
	}

	displayResults(results: string[]) {
		const resultsContainer = this.shadowRoot?.querySelector('#results');
		if (resultsContainer) {
			if (!results.length) {
				resultsContainer.innerHTML = '<p>No results found.</p>';
				return;
			}
			resultsContainer.innerHTML = `
				<ul role="list" aria-label="Memory results" style="list-style:none;padding:0;margin:0;">
					${results.map((res, i) => `
						<li role="listitem" class="result-item">
							<span class="sr-only">Result ${i + 1}: </span>${res}
						</li>
					`).join('')}
				</ul>`;
		}
	}

	render() {
		if (this.shadowRoot) {
			this.shadowRoot.innerHTML = `
				<style>
					h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1.5rem 0; color: #fff; letter-spacing: 0.02em; display: flex; align-items: center; gap: 0.5rem; }
					.icon { display: inline-flex; width: 28px; height: 28px; background: linear-gradient(135deg, #8b5cf6 0%, #14B8A6 100%); border-radius: 0.4rem; align-items: center; justify-content: center; flex-shrink: 0; }
					.subtitle { font-size: 0.65rem; font-weight: 400; color: rgba(255, 255, 255, 0.3); margin-left: 0.5rem; text-transform: uppercase; letter-spacing: 0.1em; }
					:host { display: block; }
					.search-box { display: flex; gap: 0.5rem; margin-bottom: 1rem; align-items: flex-end; }
					.input-group { flex: 1; display: flex; flex-direction: column; gap: 0.25rem; }
					label {
						display: block;
						font-size: 0.7rem;
						font-weight: 600;
						color: rgba(255, 255, 255, 0.5);
						text-transform: uppercase;
						letter-spacing: 0.06em;
						margin-bottom: 0.2rem;
					}
					input {
						flex: 1;
						background: rgba(0, 0, 0, 0.2);
						border: 1px solid rgba(255, 255, 255, 0.08);
						border-radius: 0.75rem;
						padding: 0.6rem 1rem;
						color: #fff;
						font-family: 'Inter', system-ui, sans-serif;
						font-size: 0.9rem;
						transition: all 0.3s ease;
						width: 100%;
						box-sizing: border-box;
					}
					input:focus {
						border-color: rgba(20, 184, 166, 0.4);
						background: rgba(0, 0, 0, 0.28);
					}
					button {
						background: rgba(20, 184, 166, 0.12);
						color: #14B8A6;
						border: 1px solid rgba(20, 184, 166, 0.2);
						padding: 0.6rem 1rem;
						border-radius: 0.6rem;
						cursor: pointer;
						font-weight: 600;
						font-size: 0.8rem;
						font-family: 'Inter', system-ui, sans-serif;
						letter-spacing: 0.02em;
						transition: all 0.25s ease;
						white-space: nowrap;
					}
					button:hover {
						background: rgba(20, 184, 166, 0.22);
						border-color: rgba(20, 184, 166, 0.4);
					}
					.result-item {
						padding: 0.75rem;
						background: rgba(255, 255, 255, 0.03);
						border-radius: 0.5rem;
						margin-bottom: 0.5rem;
						font-size: 0.9rem;
						border-left: 3px solid #14B8A6;
					}
					button:focus-visible, input:focus-visible {
						outline: 2px solid #14B8A6;
						outline-offset: 2px;
					}
					@media (prefers-reduced-motion: reduce) {
						input { transition: none; }
						button { transition: none; }
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
				</style>
				<div class="card">
					<h2>
						<span class="icon" aria-hidden="true">
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
								<circle cx="11" cy="11" r="8"></circle>
								<line x1="21" y1="21" x2="16.65" y2="16.65"></line>
							</svg>
						</span>
						${this.tr('memory_search', 'Memory Search')}
						<span class="subtitle" aria-hidden="true">Semantic</span>
					</h2>
					<form class="search-box" role="search" aria-label="Search semantic memory" onsubmit="return false;">
						<div class="input-group">
							<label for="memory-search-input">${this.tr('search_label', 'Search query')}</label>
							<input
								type="search"
								id="memory-search-input"
								name="query"
								placeholder="${this.tr('search_placeholder', 'Search your memories...')}"
								autocomplete="off"
								aria-describedby="memory-search-hint"
							/>
							<span id="memory-search-hint" style="font-size:0.68rem;color:rgba(255,255,255,0.3);margin-top:0.15rem;">${this.tr('search_hint', 'Semantic similarity search across all stored memories')}</span>
						</div>
						<button id="searchBtn" type="submit" aria-label="${this.tr('search', 'Search')} semantic memory">${this.tr('search', 'Search')}</button>
					</form>
					<div id="results"
						role="status"
						aria-live="polite"
						aria-label="Memory search results"
						aria-atomic="false"></div>
				</div>
			`;

			this.shadowRoot.querySelector('#searchBtn')?.addEventListener('click', () => {
				const input = this.shadowRoot?.querySelector<HTMLInputElement>('#memory-search-input');
				if (input) this.search(input.value);
			});
			// Also support Enter key
			this.shadowRoot.querySelector<HTMLInputElement>('#memory-search-input')?.addEventListener('keydown', (e: KeyboardEvent) => {
				if (e.key === 'Enter') {
					e.preventDefault();
					const input = this.shadowRoot?.querySelector<HTMLInputElement>('#memory-search-input');
					if (input) this.search(input.value);
				}
			});
		}
	}
}

customElements.define('memory-search', MemorySearch);
