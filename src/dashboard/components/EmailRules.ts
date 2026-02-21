export class EmailRules extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.render();
    this.fetchRules();
  }

  async fetchRules() {
    try {
      const response = await fetch('/api/dashboard/email-rules');
      const data = await response.json();
      this.displayRules(data);
    } catch (e) {
      console.error('Failed to fetch rules', e);
      const list = this.shadowRoot?.querySelector('#rules-list');
      if (list) list.textContent = 'No rules defined.';
    }
  }

  async addRule(pattern: string) {
    try {
      await fetch('/api/dashboard/email-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender_pattern: pattern, action: 'urgent' })
      });
      this.fetchRules();
    } catch (e) {
      console.error('Failed to add rule', e);
    }
  }

  async deleteRule(id: number) {
    try {
      await fetch(`/api/dashboard/email-rules/${id}`, { method: 'DELETE' });
      this.fetchRules();
    } catch (e) {
      console.error('Failed to delete rule', e);
    }
  }

  displayRules(rules: any[]) {
    const list = this.shadowRoot?.querySelector('#rules-list');
    if (list) {
      list.innerHTML = rules.map(r => `
        <div class="rule-item">
          <span>${r.sender_pattern}</span>
          <button class="delete-btn" data-id="${r.id}">Delete</button>
        </div>
      `).join('') || 'No rules defined.';

      list.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const id = (e.target as HTMLElement).getAttribute('data-id');
          if (id) this.deleteRule(parseInt(id));
        });
      });
    }
  }

  render() {
    if (this.shadowRoot) {
      this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; }
          .add-box { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
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
          .rule-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.03);
            padding: 0.75rem 1rem;
            border-radius: 0.75rem;
            margin-bottom: 0.5rem;
          }
          .delete-btn {
            background: rgba(239, 68, 68, 0.12);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.2);
            padding: 0.4rem 0.8rem;
            border-radius: 0.6rem;
            cursor: pointer;
            font-size: 0.8rem;
            font-weight: 600;
            font-family: 'Inter', system-ui, sans-serif;
            letter-spacing: 0.02em;
            transition: all 0.25s ease;
          }
          .delete-btn:hover {
            background: rgba(239, 68, 68, 0.22);
            border-color: rgba(239, 68, 68, 0.4);
          }
          button#addBtn {
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
          button#addBtn:hover {
            background: rgba(20, 184, 166, 0.22);
            border-color: rgba(20, 184, 166, 0.4);
          }
        </style>
        <div class="card">
          <h2>Email Rules</h2>
          <div class="add-box">
            <input type="text" id="ruleInput" placeholder="Sender pattern (e.g. @school.com)">
            <button id="addBtn">Add</button>
          </div>
          <div id="rules-list">Loading rules...</div>
        </div>
      `;

      this.shadowRoot.querySelector('#addBtn')?.addEventListener('click', () => {
        const input = this.shadowRoot?.querySelector('#ruleInput') as HTMLInputElement;
        if (input.value) {
          this.addRule(input.value);
          input.value = '';
        }
      });
    }
  }
}

customElements.define('email-rules', EmailRules);
