export class CalendarAgenda extends HTMLElement {
    private events: any[] = [];
    private filterPerson: string | null = null;

    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
    }

    connectedCallback() {
        this.render();
        this.fetchEvents();
    }

    async fetchEvents() {
        try {
            const response = await fetch('/api/dashboard/calendar');
            if (!response.ok) throw new Error('API error');
            this.events = await response.json();
            this.displayEvents();
        } catch (e) {
            console.error('Failed to fetch calendar', e);
        }
    }

    setFilter(person: string | null) {
        this.filterPerson = person;
        this.displayEvents();
    }

    displayEvents() {
        const list = this.shadowRoot?.querySelector('#event-list');
        const filters = this.shadowRoot?.querySelector('#filters');

        if (list) {
            const filtered = this.filterPerson
                ? this.events.filter(e => e.person === this.filterPerson)
                : this.events;

            list.innerHTML = filtered.map(e => {
                const date = new Date(e.start);
                const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const day = date.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' });

                return `
          <div class="event-item">
            <div class="time-box">
              <span class="day">${day}</span>
              <span class="time">${time !== '00:00' ? time : 'All day'}</span>
            </div>
            <div class="details">
              <span class="summary">${e.summary}</span>
              ${e.person ? `<span class="person-badge">${e.person}</span>` : ''}
            </div>
          </div>
        `;
            }).join('') || '<div class="empty">No upcoming events.</div>';
        }

        // Refresh filter buttons
        if (filters) {
            const people = [...new Set(this.events.filter(e => e.person).map(e => e.person))];
            filters.innerHTML = `
        <button class="filter-btn ${!this.filterPerson ? 'active' : ''}" data-person="">All</button>
        ${people.map(p => `
          <button class="filter-btn ${this.filterPerson === p ? 'active' : ''}" data-person="${p}">${p}</button>
        `).join('')}
      `;

            filters.querySelectorAll('.filter-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const person = (e.target as HTMLElement).getAttribute('data-person');
                    this.setFilter(person || null);
                });
            });
        }
    }

    render() {
        if (this.shadowRoot) {
            this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; }
          .card { height: 100%; display: flex; flex-direction: column; }
          #filters { display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; }
          .filter-btn {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: rgba(255, 255, 255, 0.6);
            padding: 0.25rem 0.75rem;
            border-radius: 2rem;
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.2s;
          }
          .filter-btn.active {
            background: rgba(20, 184, 166, 0.2);
            border-color: #14B8A6;
            color: #14B8A6;
          }
          #event-list { overflow-y: auto; flex: 1; }
          .event-item {
            display: flex;
            gap: 1rem;
            padding: 0.75rem;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 0.75rem;
            margin-bottom: 0.5rem;
            border: 1px solid transparent;
          }
          .time-box {
            display: flex;
            flex-direction: column;
            min-width: 70px;
            font-size: 0.75rem;
          }
          .day { color: #14B8A6; font-weight: 700; }
          .time { color: rgba(255, 255, 255, 0.4); }
          .details { display: flex; flex-direction: column; gap: 0.25rem; flex: 1; }
          .summary { font-size: 0.9rem; color: #fff; font-weight: 500; }
          .person-badge {
            align-self: flex-start;
            font-size: 0.7rem;
            color: #14B8A6;
            background: rgba(20, 184, 166, 0.1);
            border: 1px solid rgba(20, 184, 166, 0.2);
            padding: 0.15rem 0.5rem;
            border-radius: 0.4rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
          }
          .empty { font-size: 0.85rem; color: rgba(255, 255, 255, 0.3); text-align: center; padding: 2rem; }
        </style>
        <div class="card">
          <h2>Calendar Agenda</h2>
          <div id="filters"></div>
          <div id="event-list">Loading events...</div>
        </div>
      `;
        }
    }
}

customElements.define('calendar-agenda', CalendarAgenda);
