export class CircleManager extends HTMLElement {
  private circleType: string = 'inner';

  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  static get observedAttributes() {
    return ['type'];
  }

  attributeChangedCallback(name: string, _oldValue: string, newValue: string) {
    if (name === 'type') {
      this.circleType = newValue;
      this.render();
      this.fetchPeople();
    }
  }

  connectedCallback() {
    this.circleType = this.getAttribute('type') || 'inner';
    this.render();
    this.fetchPeople();
    window.addEventListener('refresh-data', (e: any) => {
      if (e.detail.actions.includes('people')) {
        this.fetchPeople();
      }
    });
  }

  async fetchPeople() {
    try {
      const response = await fetch(`/api/dashboard/people?circle_type=${this.circleType}`);
      if (!response.ok) throw new Error('API error');
      const text = await response.text();
      if (!text) throw new Error('Empty response');
      const data = JSON.parse(text);
      this.displayPeople(data);
    } catch (e) {
      const list = this.shadowRoot?.querySelector('#people-list');
      if (list) list.textContent = 'No people added to this circle.';
    }
  }

  async addPerson(name: string, relationship: string, context: string, birthday: string = '') {
    try {
      await fetch('/api/dashboard/people', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, relationship, context, circle_type: this.circleType, birthday })
      });
      this.fetchPeople();
    } catch (e) {
      console.error('Failed to add person', e);
    }
  }

  async deletePerson(id: number) {
    try {
      await fetch(`/api/dashboard/people/${id}`, { method: 'DELETE' });
      this.fetchPeople();
    } catch (e) {
      console.error('Failed to delete person', e);
    }
  }

  displayPeople(people: any[]) {
    const list = this.shadowRoot?.querySelector('#people-list');
    if (list) {
      list.innerHTML = people.map(p => `
        <div class="person-item">
          <div class="info">
            <span class="name">${p.name}</span>
            <span class="rel">${p.relationship}</span>
            ${p.birthday ? `<span class="cal-badge">🎂 ${p.birthday}</span>` : ''}
            <p class="ctx">${p.context || 'No specific focus set.'}</p>
          </div>
          <button class="delete-btn" data-id="${p.id}">Remove</button>
        </div>
      `).join('') || `No people added to this circle.`;

      list.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const id = (e.target as HTMLElement).getAttribute('data-id');
          if (id) this.deletePerson(parseInt(id));
        });
      });
    }
  }

  render() {
    if (this.shadowRoot) {
      const title = this.circleType === 'inner' ? 'Inner Circle (Family & Care)' : 'Close Circle (Friends & Social)';
      const accent = this.circleType === 'inner' ? '#3b82f6' : '#10b981';

      this.shadowRoot.innerHTML = `
        <style>
          h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1rem 0; color: #fff; letter-spacing: 0.02em; }
          :host { display: block; }
          .add-form { display: grid; gap: 0.5rem; margin-bottom: 1.5rem; }
          input, textarea {
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
          input:focus, textarea:focus {
            border-color: rgba(20, 184, 166, 0.4);
            background: rgba(0, 0, 0, 0.28);
          }
          .person-item {
            background: rgba(255, 255, 255, 0.03);
            border-radius: 1rem;
            padding: 1rem;
            margin-bottom: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
          }
          .name { font-weight: 700; color: #fff; display: block; }
          .rel { font-size: 0.8rem; color: ${accent}; }
          .ctx { font-size: 0.85rem; color: rgba(255, 255, 255, 0.6); margin: 0.5rem 0 0 0; }
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
          .cal-badge {
            display: inline-block;
            font-size: 0.7rem;
            color: #14B8A6;
            background: rgba(20, 184, 166, 0.1);
            border: 1px solid rgba(20, 184, 166, 0.2);
            padding: 0.15rem 0.5rem;
            border-radius: 0.4rem;
            margin-left: 0.5rem;
          }
          .checkbox-row {
            display: none; /* Removed */
          }
          .checkbox-row input[type="checkbox"] {
            width: 16px;
            height: 16px;
            accent-color: #14B8A6;
            cursor: pointer;
          }
          .checkbox-row label {
            font-size: 0.85rem;
            color: rgba(255, 255, 255, 0.7);
            cursor: pointer;
            user-select: none;
          }
          #bdayInput.hidden {
            display: none;
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
          <h2>${title}</h2>
          <div class="add-form">
            <input type="text" id="nameInput" placeholder="Name">
            <input type="text" id="relInput" placeholder="Relationship (e.g. Son, Friend)">
            <input type="text" id="bdayInput" placeholder="Birthday (e.g. MM-DD or YYYY-MM-DD)">
            <textarea id="ctxInput" placeholder="Focus..."></textarea>
            <button id="addBtn">Add to Circle</button>
          </div>
          <div id="people-list">Loading...</div>
        </div>
      `;

      this.shadowRoot.querySelector('#addBtn')?.addEventListener('click', () => {
        const name = (this.shadowRoot?.querySelector('#nameInput') as HTMLInputElement).value;
        const rel = (this.shadowRoot?.querySelector('#relInput') as HTMLInputElement).value;
        const ctx = (this.shadowRoot?.querySelector('#ctxInput') as HTMLTextAreaElement).value;
        const bday = (this.shadowRoot?.querySelector('#bdayInput') as HTMLInputElement).value;
        if (name && rel) {
          this.addPerson(name, rel, ctx, bday);
          (this.shadowRoot?.querySelector('#nameInput') as HTMLInputElement).value = '';
          (this.shadowRoot?.querySelector('#relInput') as HTMLInputElement).value = '';
          (this.shadowRoot?.querySelector('#ctxInput') as HTMLTextAreaElement).value = '';
          (this.shadowRoot?.querySelector('#bdayInput') as HTMLInputElement).value = '';
        }
      });
    }
  }
}

customElements.define('circle-manager', CircleManager);
