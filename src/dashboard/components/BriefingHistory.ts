export class BriefingHistory extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.render();
    this.fetchBriefings();
  }

  async fetchBriefings() {
    try {
      const response = await fetch('/api/dashboard/briefings');
      if (!response.ok) throw new Error('API error');
      const text = await response.text();
      if (!text) throw new Error('Empty response');
      const data = JSON.parse(text);
      this.displayBriefings(data);
    } catch (e) {
      const list = this.shadowRoot?.querySelector('#briefing-list');
      if (list) list.textContent = 'No briefings yet.';
    }
  }

  displayBriefings(briefings: any[]) {
    const list = this.shadowRoot?.querySelector('#briefing-list');
    if (list) {
      list.innerHTML = briefings.map((b) => `
        <div class="briefing-item">
          <div class="meta" onclick="this.parentElement.classList.toggle('active')">
            <div class="meta-left">
              <span class="type">${b.type.toUpperCase()}</span>
              <span class="date">${new Date(b.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
            </div>
            <div class="chevron">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="m6 9 6 6 6-6"/>
              </svg>
            </div>
          </div>
          <div class="content-wrapper">
            <div class="content-inner">
              <div class="content">${b.content}</div>
            </div>
          </div>
        </div>
      `).join('') || 'No briefings yet.';
    }
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
          }
          .meta-left { display: flex; align-items: center; gap: 0.75rem; }
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
            transition: grid-template-rows 0.4s cubic-bezier(0.4, 0, 0.2, 1);
          }
          .briefing-item.active .content-wrapper {
            grid-template-rows: 1fr;
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
