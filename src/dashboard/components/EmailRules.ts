export class EmailRules extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.render();
    this.fetchRules();
  }

  private editingId: number | null = null;
  private currentRules: any[] = [];

  async fetchRules() {
    try {
      const response = await fetch('/api/dashboard/email-rules');
      if (!response.ok) throw new Error('API error');
      const data = await response.json();
      this.currentRules = data;
      this.displayRules(data);
    } catch (e) {
      const list = this.shadowRoot?.querySelector('#rules-list');
      if (list) list.textContent = 'No rules defined.';
    }
  }

  async addRule(pattern: string, action: string) {
    try {
      await fetch('/api/dashboard/email-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender_pattern: pattern, action })
      });
      this.fetchRules();
    } catch (e) {
      console.error('Failed to add rule', e);
    }
  }

  async updateRule(id: number, pattern: string, action: string) {
    try {
      await fetch(`/api/dashboard/email-rules/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender_pattern: pattern, action })
      });
      this.editingId = null;
      this.render();
      this.fetchRules();
    } catch (e) {
      console.error('Failed to update rule', e);
    }
  }


  displayRules(rules: any[]) {
    const list = this.shadowRoot?.querySelector('#rules-list');
    if (list) {
      list.innerHTML = rules.map(r => `
        <div class="rule-item">
          <div class="info">
            <span class="pattern">${r.sender_pattern}</span>
            <span class="action-tag">${r.action === 'urgent' ? '⚡ Urgent Notify' : '📋 Daily Summary'}</span>
          </div>
          <div class="item-actions">
            <button class="edit-btn" data-id="${r.id}">Edit</button>
            <button class="delete-btn" data-id="${r.id}">Delete</button>
          </div>
        </div>
      `).join('') || 'No rules defined.';

      list.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const id = (e.currentTarget as HTMLElement).getAttribute('data-id');
          if (id) this.deleteRule(parseInt(id));
        });
      });

      list.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const id = (e.currentTarget as HTMLElement).getAttribute('data-id');
          const rule = this.currentRules.find(r => r.id === parseInt(id!));
          if (rule) {
            this.editingId = rule.id;
            this.render();
            (this.shadowRoot?.querySelector('#ruleInput') as HTMLInputElement).value = rule.sender_pattern;
            (this.shadowRoot?.querySelector('#actionInput') as HTMLSelectElement).value = rule.action;
          }
        });
      });
    }
  }

  render() {
    if (this.shadowRoot) {
      this.shadowRoot.innerHTML = `
        <style>
          h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1rem 0; color: #fff; letter-spacing: 0.02em; }
          :host { display: block; }
          .add-box { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1.5rem; background: rgba(255,255,255,0.02); padding: 1rem; border-radius: 1rem; }
          .input-row { display: flex; gap: 0.5rem; }
          input, select {
            flex: 1;
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 0.75rem;
            padding: 0.6rem 1rem;
            color: #fff;
            outline: none;
            font-family: 'Inter', system-ui, sans-serif;
            font-size: 0.9rem;
          }
          select option { background: #000; }
          .rule-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.03);
            padding: 0.75rem 1rem;
            border-radius: 0.75rem;
            margin-bottom: 0.5rem;
          }
          .info { display: flex; flex-direction: column; gap: 4px; }
          .pattern { color: #fff; font-weight: 500; font-size: 0.9rem; }
          .action-tag { font-size: 0.7rem; color: #14B8A6; opacity: 0.8; }
          .delete-btn { background: rgba(239, 68, 68, 0.1); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.15); padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 0.75rem; }
          .edit-btn { background: rgba(255, 255, 255, 0.05); color: #fff; border: 1px solid rgba(255, 255, 255, 0.1); padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 0.75rem; margin-right: 4px; }
          button#addBtn {
            background: rgba(20, 184, 166, 0.12);
            color: #14B8A6;
            border: 1px solid rgba(20, 184, 166, 0.2);
            padding: 0.6rem 1.25rem;
            border-radius: 0.75rem;
            cursor: pointer;
            font-weight: 600;
          }
        </style>
        <div class="card">
          <h2>Email Intelligence Rules</h2>
          <div class="add-box">
            <div class="input-row">
              <input type="text" id="ruleInput" placeholder="Pattern (e.g. @domain.com or 'Invoice')">
              <select id="actionInput">
                <option value="urgent">⚡ Urgent Notification</option>
                <option value="summarize">📋 Daily Summary</option>
              </select>
            </div>
            <div style="display:flex; gap:0.5rem;">
              <button id="addBtn">${this.editingId ? 'Update Rule' : 'Create Rule'}</button>
              ${this.editingId ? '<button id="cancelEdit" style="background:transparent; color:#fff; border:none; cursor:pointer; font-size:0.8rem;">Cancel</button>' : ''}
            </div>
          </div>
          <div id="rules-list">${this.currentRules.length > 0 ? '' : 'Loading rules...'}</div>
        </div>
      `;

      this.shadowRoot.querySelector('#addBtn')?.addEventListener('click', () => {
        const pattern = (this.shadowRoot?.querySelector('#ruleInput') as HTMLInputElement).value;
        const action = (this.shadowRoot?.querySelector('#actionInput') as HTMLSelectElement).value;
        if (pattern) {
          if (this.editingId) {
            this.updateRule(this.editingId, pattern, action);
          } else {
            this.addRule(pattern, action);
          }
          (this.shadowRoot?.querySelector('#ruleInput') as HTMLInputElement).value = '';
        }
      });

      // Accessibility: Submit on Enter
      this.shadowRoot.querySelectorAll('input, select').forEach(el => {
        el.addEventListener('keydown', (e: any) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            this.shadowRoot?.querySelector<HTMLButtonElement>('#addBtn')?.click();
          }
        });
      });

      this.shadowRoot.querySelector('#cancelEdit')?.addEventListener('click', () => {
        this.editingId = null;
        this.render();
        this.displayRules(this.currentRules);
      });
    }
  }

  async deleteRule(id: number) {
    if (!confirm('Are you sure you want to delete this intelligence rule?')) return;
    try {
      await fetch(`/api/dashboard/email-rules/${id}`, { method: 'DELETE' });
      this.fetchRules();
    } catch (e) {
      console.error('Failed to delete rule', e);
    }
  }
}

customElements.define('email-rules', EmailRules);
