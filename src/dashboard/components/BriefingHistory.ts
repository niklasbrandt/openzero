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
      const data = await response.json();
      this.displayBriefings(data);
    } catch (e) {
      console.error('Failed to fetch briefings', e);
      const list = this.shadowRoot?.querySelector('#briefing-list');
      if (list) list.textContent = 'No briefings yet.';
    }
  }

  displayBriefings(briefings: any[]) {
    const list = this.shadowRoot?.querySelector('#briefing-list');
    if (list) {
      list.innerHTML = briefings.map(b => `
        <div class="briefing-item">
          <div class="meta">
            <span class="type">${b.type.toUpperCase()}</span>
            <span class="date">${new Date(b.created_at).toLocaleDateString()}</span>
          </div>
          <div class="content">${b.content}</div>
        </div>
      `).join('') || 'No briefings yet.';
    }
  }

  render() {
    if (this.shadowRoot) {
      this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; }
          .briefing-item {
            background: rgba(255, 255, 255, 0.03);
            border-radius: 1rem;
            padding: 1.25rem;
            margin-bottom: 1rem;
            border: 1px solid rgba(255, 255, 255, 0.05);
          }
          .meta { display: flex; justify-content: space-between; margin-bottom: 0.5rem; }
          .type { 
            background: #14B8A6; 
            color: #fff; 
            font-size: 0.7rem; 
            padding: 0.2rem 0.5rem; 
            border-radius: 4px; 
            font-weight: 700;
          }
          .date { font-size: 0.8rem; color: rgba(255, 255, 255, 0.5); }
          .content { font-size: 0.9rem; white-space: pre-wrap; line-height: 1.4; color: rgba(255, 255, 255, 0.8); }
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
