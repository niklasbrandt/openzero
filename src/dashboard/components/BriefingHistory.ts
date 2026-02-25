export class BriefingHistory extends HTMLElement {
	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
		this.fetchBriefings();
	}

	private currentLimit = 5;

	async fetchBriefings() {
		try {
			const response = await fetch(`/api/dashboard/briefings?limit=${this.currentLimit}`);
			if (!response.ok) throw new Error('API error');
			const data = await response.json();
			this.displayBriefings(data);
		} catch (e) {
			const list = this.shadowRoot?.querySelector('#briefing-list');
			if (list) list.textContent = 'No briefings yet.';
		}
	}

	showMore() {
		this.currentLimit += 15;
		this.fetchBriefings();
	}

	displayBriefings(briefings: any[]) {
		const list = this.shadowRoot?.querySelector('#briefing-list');
		if (!list) return;

		const itemsHtml = briefings.map((b) => `
				<div class="briefing-item">
					<button class="meta" 
						onclick="this.parentElement.classList.toggle('active'); this.setAttribute('aria-expanded', this.parentElement.classList.contains('active').toString())"
						aria-expanded="false"
						aria-label="Toggle briefing details for ${new Date(b.created_at).toLocaleDateString()}"
					>
						<div class="meta-left">
							<span class="type">${b.type.toUpperCase()}</span>
							<span class="date">${new Date(b.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
						</div>
						<div class="chevron">
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<path d="m6 9 6 6 6-6"/>
							</svg>
						</div>
					</button>
					<div class="content-wrapper">
						<div class="content-inner">
							<div class="content">${b.content}</div>
						</div>
					</div>
				</div>
			`).join('');

		list.innerHTML = `
			${itemsHtml || 'No briefings yet.'}
			${briefings.length >= 5 ? `<button class="load-more" onclick="this.closest('briefing-history').showMore()">Show More History</button>` : ''}
		`;
	}

	render() {
		if (this.shadowRoot) {
			this.shadowRoot.innerHTML = `
				<style>
					h2 { 
						font-size: 1.5rem; 
						font-weight: bold; 
						margin: 0 0 1.5rem 0; 
						color: #fff; 
						letter-spacing: -0.01em; 
					}
					:host { display: block; }
					.card {
						display: flex;
						flex-direction: column;
					}
					.briefing-item {
						background: rgba(255, 255, 255, 0.02);
						border-radius: 12px;
						margin-bottom: 0.75rem;
						border: 1px solid rgba(255, 255, 255, 0.05);
						overflow: hidden;
						transition: background 0.3s ease, border-color 0.3s ease;
					}
					.briefing-item:hover {
						background: rgba(255, 255, 255, 0.04);
						border-color: rgba(255, 255, 255, 0.1);
					}
					.briefing-item.active {
						background: rgba(255, 255, 255, 0.04);
						border-color: rgba(20, 184, 166, 0.2);
					}
					.meta { 
						display: flex; 
						justify-content: space-between; 
						align-items: center;
						padding: 1rem 1.25rem; 
						cursor: pointer;
						user-select: none;
						background: transparent;
						border: none;
						width: 100%;
						font-family: inherit;
						color: inherit;
					}
					.meta:focus-visible { 
						background: rgba(255, 255, 255, 0.05);
						outline: none;
					}
					.type { 
						background: rgba(20, 184, 166, 0.1); 
						color: #14B8A6; 
						font-size: 0.65rem; 
						padding: 0.2rem 0.6rem; 
						border-radius: 20px; 
						font-weight: 700;
						letter-spacing: 0.05em;
						border: 1px solid rgba(20, 184, 166, 0.2);
					}
					.date { 
						font-size: 0.8rem; 
						color: rgba(255, 255, 255, 0.4); 
						font-weight: 500;
					}
					.chevron { 
						transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1); 
						color: rgba(255, 255, 255, 0.2);
						display: flex;
						align-items: center;
					}
					.briefing-item.active .chevron { 
						transform: rotate(180deg); 
						color: #14B8A6;
					}
					
					.content-wrapper {
						display: grid;
						grid-template-rows: 0fr;
						pointer-events: none;
						transition: grid-template-rows 0.4s cubic-bezier(0.4, 0, 0.2, 1);
					}
					.briefing-item.active .content-wrapper {
						grid-template-rows: 1fr;
						pointer-events: auto;
					}
					.content-inner {
						overflow: hidden;
						min-height: 0;
					}
					.content { 
						padding: 0 1.25rem 1.25rem 1.25rem;
						font-size: 0.95rem; 
						white-space: pre-wrap; 
						line-height: 1.6; 
						color: rgba(255, 255, 255, 0.8); 
						border-top: 1px solid rgba(255, 255, 255, 0.03);
						padding-top: 1rem;
					}
					.load-more {
						width: 100%;
						background: rgba(255, 255, 255, 0.02);
						border: 1px dashed rgba(255, 255, 255, 0.1);
						color: rgba(255, 255, 255, 0.4);
						padding: 0.75rem;
						border-radius: 12px;
						font-size: 0.8rem;
						font-weight: 600;
						cursor: pointer;
						margin-top: 0.5rem;
						transition: all 0.2s;
					}
					.load-more:hover {
						background: rgba(20, 184, 166, 0.05);
						color: #14B8A6;
						border-color: rgba(20, 184, 166, 0.3);
					}
					.load-more:focus-visible { outline: 2px solid #14B8A6; outline-offset: 2px; }
				</style>
				<div class="card">
					<h2>Briefing History</h2>
					<div id="briefing-list">Loading briefings...</div>
				</div>
			`;
		}
	}
}

customElements.define('briefing-history', BriefingHistory);
