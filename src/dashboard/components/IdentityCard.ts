export class IdentityCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.fetchIdentity();
  }

  async fetchIdentity() {
    try {
      const response = await fetch('/api/dashboard/people?circle_type=identity');
      if (!response.ok) throw new Error('API error');
      const data = await response.json();
      this.render(data[0] || null);
    } catch (e) {
      this.render(null);
    }
  }

  render(me: any) {
    if (!this.shadowRoot) return;

    const birthdayText = me?.birthday || 'Unknown';
    const contextHtml = me?.context
      ? me.context.split('\n').map((line: string) => `<li>${line}</li>`).join('')
      : '<li class="empty">Z has not distilled your core essence yet.</li>';

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .card {
          background: linear-gradient(145deg, rgba(20, 184, 166, 0.05), rgba(0, 0, 0, 0.2));
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 1.25rem;
          padding: 1.5rem;
          height: 100%;
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
          position: relative;
          overflow: hidden;
        }
        .card::before {
          content: '';
          position: absolute;
          top: -100px;
          right: -100px;
          width: 200px;
          height: 200px;
          background: radial-gradient(circle, rgba(20, 184, 166, 0.1) 0%, transparent 70%);
          border-radius: 50%;
          pointer-events: none;
        }
        .header { display: flex; align-items: center; gap: 1rem; }
        .avatar {
          width: 48px;
          height: 48px;
          background: #14B8A6;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 800;
          font-size: 1.2rem;
          color: #fff;
          box-shadow: 0 0 20px rgba(20, 184, 166, 0.3);
        }
        .name-group h2 { margin: 0; font-size: 1.1rem; letter-spacing: -0.01em; color: #fff; }
        .name-group p { margin: 2px 0 0 0; font-size: 0.75rem; color: rgba(255, 255, 255, 0.4); text-transform: uppercase; letter-spacing: 0.1em; }
        
        .stats {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.75rem;
        }
        .stat-box {
          background: rgba(255, 255, 255, 0.03);
          padding: 0.75rem;
          border-radius: 0.75rem;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .stat-label { font-size: 0.65rem; color: rgba(255, 255, 255, 0.3); text-transform: uppercase; margin-bottom: 4px; }
        .stat-value { font-size: 0.9rem; color: #fff; font-weight: 600; }

        .essence h3 { font-size: 0.75rem; color: rgba(255, 255, 255, 0.3); text-transform: uppercase; margin: 0 0 0.75rem 0; letter-spacing: 0.05em; }
        ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.6rem; }
        li { font-size: 0.85rem; color: rgba(255, 255, 255, 0.8); line-height: 1.5; position: relative; padding-left: 1rem; }
        li::before {
          content: '→';
          position: absolute;
          left: 0;
          color: #14B8A6;
          font-weight: bold;
        }
        .empty { color: rgba(255, 255, 255, 0.2); font-style: italic; padding-left: 0; }
        .empty::before { display: none; }
      </style>
      <div class="card">
        <div class="header">
          <div class="avatar">${(me?.name || 'U')[0]}</div>
          <div class="name-group">
            <h2>${me?.name || 'User'}</h2>
            <p>Subject Zero</p>
          </div>
        </div>

        <div class="stats">
          <div class="stat-box">
            <div class="stat-label">Birthday</div>
            <div class="stat-value">${birthdayText}</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Identity Level</div>
            <div class="stat-value">Alpha</div>
          </div>
        </div>

        <div class="essence">
          <h3>Core Essence</h3>
          <ul>${contextHtml}</ul>
        </div>
      </div>
    `;
  }
}

customElements.define('identity-card', IdentityCard);
