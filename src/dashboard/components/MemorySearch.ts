export class MemorySearch extends HTMLElement {
	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
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
			resultsContainer.innerHTML = results.map(res => `
				<div class="result-item">${res}</div>
			`).join('') || 'No results found.';
		}
	}

	render() {
		if (this.shadowRoot) {
			this.shadowRoot.innerHTML = `
				<style>
					h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1rem 0; color: #fff; letter-spacing: 0.02em; }
					:host { display: block; }
					.search-box { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
					input {
						flex: 1;
						background: rgba(0, 0, 0, 0.2);
						border: 1px solid rgba(255, 255, 255, 0.08);
						border-radius: 0.75rem;
						padding: 0.6rem 1rem;
						color: #fff;
						outline: none;
						font-family: 'Inter', system-ui, sans-serif;
						font-size: 0.9rem;
						transition: all 0.3s ease;
					}
					input:focus {
						border-color: rgba(20, 184, 166, 0.4);
						background: rgba(0, 0, 0, 0.28);
					}
					button {
						background: rgba(20, 184, 166, 0.12);
						color: #14B8A6;
						border: 1px solid rgba(20, 184, 166, 0.2);
						padding: 0.4rem 1rem;
						border-radius: 0.6rem;
						cursor: pointer;
						font-weight: 600;
						font-size: 0.8rem;
						font-family: 'Inter', system-ui, sans-serif;
						letter-spacing: 0.02em;
						transition: all 0.25s ease;
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
				</style>
				<div class="card">
					<h2>Memory Search</h2>
					<div class="search-box">
						<input type="text" placeholder="Search your memories...">
						<button id="searchBtn">Search</button>
					</div>
					<div id="results" aria-live="polite"></div>
				</div>
			`;

			this.shadowRoot.querySelector('#searchBtn')?.addEventListener('click', () => {
				const input = this.shadowRoot?.querySelector('input');
				if (input) this.search(input.value);
			});
		}
	}
}

customElements.define('memory-search', MemorySearch);
