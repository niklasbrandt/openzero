export class LifeOverview extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.render();
    this.fetchData();
    window.addEventListener('refresh-data', () => {
      this.fetchData();
    });
  }

  async fetchData() {
    try {
      const response = await fetch('/api/dashboard/life-tree');
      if (!response.ok) throw new Error('API error');
      const data = await response.json();
      this.updateUI(data);
    } catch (e) {
      console.error('Failed to fetch life tree', e);
      this.showError();
    }
  }

  showError() {
    const container = this.shadowRoot?.querySelector('#overview-container');
    if (container) {
      container.innerHTML = '<div class="error">Unable to load Life Overview. Check backend connection.</div>';
    }
  }

  updateUI(data: any) {
    const container = this.shadowRoot?.querySelector('#overview-container');
    if (!container) return;

    const innerHtml = data.social_circles.inner.length > 0
      ? data.social_circles.inner.map((p: any) => `<li>${p.name} <span class="rel">(${p.relationship})</span></li>`).join('')
      : '<li class="empty-li">No family connections.</li>';

    const closeHtml = data.social_circles.close.length > 0
      ? data.social_circles.close.map((p: any) => `<li>${p.name} <span class="rel">(${p.relationship})</span></li>`).join('')
      : '<li class="empty-li">No social circle added.</li>';

    const timelineHtml = data.timeline.length > 0
      ? data.timeline.map((e: any) => `
          <div class="timeline-item">
            <span class="time">${e.time}</span>
            <span class="summary">${e.summary} ${e.is_local ? '<small>(local)</small>' : ''}</span>
          </div>
        `).join('')
      : '<div class="empty">No upcoming events for the next 3 days.</div>';

    container.innerHTML = `
      <div class="overview-grid">
        <section class="mission-control">
          <div class="section-header">
            <h3>Mission Control</h3>
            <button class="action-btn" onclick="this.closest('life-overview').parentElement.querySelector('create-project').toggle()">+ New Mission</button>
          </div>
          <div class="tree-content">${data.projects_tree || 'Initializing projects...'}</div>
        </section>
        
        <div class="side-panel">
          <section class="social-section">
            <div class="circle-group">
                <h3>Inner Circle <small>(Family & Care)</small></h3>
                <ul>${innerHtml}</ul>
            </div>
            <div class="circle-group" style="margin-top: 1.5rem;">
                <h3>Close Circle <small>(Friends & Social)</small></h3>
                <ul>${closeHtml}</ul>
            </div>
          </section>

          <section class="timeline">
            <h3>Timeline (Next 3 Days)</h3>
            <div class="timeline-list">${timelineHtml}</div>
          </section>
        </div>
      </div>
    `;
  }

  render() {
    if (this.shadowRoot) {
      this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; }
          h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1.5rem 0; color: #fff; letter-spacing: 0.02em; }
          h3 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.1em; color: rgba(255, 255, 255, 0.4); margin-bottom: 1rem; }
          h3 small { font-size: 0.65rem; text-transform: none; letter-spacing: 0.02em; opacity: 0.8; margin-left: 0.4rem; font-weight: 400; }
          
          .overview-grid {
            display: grid;
            grid-template-columns: 1.5fr 1fr;
            gap: 2rem;
          }

          @media (max-width: 900px) {
            .overview-grid { grid-template-columns: 1fr; }
          }

          pre, .tree-content {
            background: rgba(0, 0, 0, 0.2);
            padding: 1.25rem;
            border-radius: 0.75rem;
            font-family: 'Fira Code', monospace;
            font-size: 0.9rem;
            line-height: 1.6;
            color: rgba(255, 255, 255, 0.85);
            margin: 0;
            overflow-x: auto;
            border: 1px solid rgba(255, 255, 255, 0.03);
            white-space: pre-wrap;
          }

          .tree-content b { color: #14B8A6; font-weight: 600; }
          .tree-content a { color: inherit; text-decoration: none; border-bottom: 1px solid rgba(255,255,255,0.1); transition: all 0.2s; }
          .tree-content a:hover { color: #0066FF; border-bottom-color: #0066FF; }

          .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
          }

          .action-btn {
            background: rgba(20, 184, 166, 0.1);
            color: #14B8A6;
            border: 1px solid rgba(20, 184, 166, 0.3);
            padding: 0.25rem 0.75rem;
            border-radius: 0.5rem;
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
          }
          .action-btn:hover { background: #14B8A6; color: #fff; }

          .side-panel { display: flex; flex-direction: column; gap: 2rem; }

          ul { list-style: none; padding: 0; margin: 0; }
          li { 
            font-size: 0.95rem; 
            line-height: 1.4;
            color: #fff; 
            margin-bottom: 0.5rem; 
            display: flex;
            align-items: center;
            gap: 0.5rem;
          }
          .rel { color: rgba(255, 255, 255, 0.4); font-size: 0.8rem; }
          .empty-li { font-size: 0.85rem; color: rgba(255, 255, 255, 0.25); font-style: italic; }

          .timeline-list { display: flex; flex-direction: column; gap: 0.75rem; }
          .timeline-item {
            display: flex;
            gap: 1rem;
            background: rgba(255, 255, 255, 0.02);
            padding: 0.75rem;
            border-radius: 0.6rem;
            font-size: 0.85rem;
          }
          .time { color: #14B8A6; font-weight: 600; min-width: 70px; }
          .summary { color: rgba(255, 255, 255, 0.8); }
          .summary small { color: #3b82f6; opacity: 0.7; font-size: 0.7rem; margin-left: 0.3rem; }


          .error { color: #ef4444; text-align: center; padding: 2rem; }
        </style>
        <div class="card">
          <h2>Life Overview</h2>
          <div id="overview-container">
            <div style="text-align: center; padding: 2rem; color: rgba(255,255,255,0.3);">Mapping your world...</div>
          </div>
        </div>
      `;
    }
  }
}

customElements.define('life-overview', LifeOverview);
