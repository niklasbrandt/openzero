export class CalendarManager extends HTMLElement {
    private events: any[] = [];
    private isOpen = false;

    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
    }

    connectedCallback() {
        this.render();
        this.fetchEvents();
        // Listen for global button to open/close
        window.addEventListener('open-calendar', () => this.toggle(true));
    }

    async fetchEvents() {
        try {
            const response = await fetch('/api/dashboard/calendar');
            if (response.ok) {
                this.events = await response.json();
                this.render();
            }
        } catch (e) {
            console.error('Failed to fetch events', e);
        }
    }

    toggle(force?: boolean) {
        this.isOpen = force !== undefined ? force : !this.isOpen;
        if (this.isOpen) {
            this.setAttribute('open', '');
        } else {
            this.removeAttribute('open');
        }
        this.render();
    }

    async addEvent(e: Event) {
        e.preventDefault();
        const form = e.target as HTMLFormElement;
        const formData = new FormData(form);
        const data = {
            summary: formData.get('summary'),
            start_time: formData.get('start'),
            end_time: formData.get('end'),
        };

        try {
            const response = await fetch('/api/dashboard/calendar/local', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (response.ok) {
                form.reset();
                this.fetchEvents();
            }
        } catch (err) {
            console.error('Failed to add event', err);
        }
    }

    render() {
        if (!this.shadowRoot) return;

        const now = new Date();
        const month = now.getMonth();
        const year = now.getFullYear();
        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const monthName = now.toLocaleString('default', { month: 'long' });

        // Days with events
        const eventDays = new Set(this.events.map(e => new Date(e.start).getDate()));

        this.shadowRoot.innerHTML = `
        <style>
            :host {
                display: none;
                position: fixed;
                top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0, 0, 0, 0.7);
                backdrop-filter: blur(16px);
                z-index: 2000;
                align-items: center;
                justify-content: center;
                padding: 2rem;
            }
            :host([open]) { display: flex; }
            
            .modal {
                background: rgba(10, 10, 12, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 2.5rem;
                width: 100%;
                max-width: 1100px;
                max-height: 90vh;
                display: grid;
                grid-template-rows: auto 1fr;
                overflow: hidden;
                box-shadow: 0 50px 100px -20px rgba(0, 0, 0, 0.8);
                animation: modalPop 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            }
            @keyframes modalPop {
                from { opacity: 0; transform: scale(0.98) translateY(20px); }
                to { opacity: 1; transform: scale(1) translateY(0); }
            }
            .header {
                padding: 2rem 2.5rem;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            h2 { 
                margin: 0; 
                font-size: 2rem; 
                background: linear-gradient(135deg, #fff 0%, rgba(255,255,255,0.5) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-weight: 800;
                letter-spacing: -0.02em;
            }
            .close-btn {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #fff;
                width: 40px; height: 40px;
                border-radius: 12px;
                display: flex; align-items: center; justify-content: center;
                cursor: pointer;
                transition: all 0.2s;
                font-size: 1.5rem;
            }
            .close-btn:hover { background: rgba(239, 68, 68, 0.2); border-color: #ef4444; }
            
            .content-grid {
                padding: 2.5rem;
                display: grid;
                grid-template-columns: 1fr 380px;
                gap: 3rem;
                overflow: hidden;
            }
            
            /* Month Grid */
            .calendar-view {
                display: flex;
                flex-direction: column;
                gap: 1.5rem;
            }
            .month-label { font-size: 1.2rem; color: #fff; font-weight: 600; opacity: 0.9; }
            .month-grid {
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 0.5rem;
            }
            .weekday { text-align: center; font-size: 0.75rem; color: #666; font-weight: 600; margin-bottom: 0.5rem; }
            .day-cell {
                aspect-ratio: 1;
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 0.75rem;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 0.9rem;
                color: #888;
                position: relative;
                transition: all 0.2s;
            }
            .day-cell.today { border-color: #14B8A6; color: #14B8A6; background: rgba(20, 184, 166, 0.05); }
            .day-cell.has-event::after {
                content: '';
                position: absolute;
                bottom: 20%; left: 50%;
                transform: translateX(-50%);
                width: 4px; height: 4px;
                background: #14B8A6;
                border-radius: 50%;
                box-shadow: 0 0 8px #14B8A6;
            }
            .day-cell:hover { background: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.15); color: #fff; }
            
            /* Right Column */
            .events-overview { overflow-y: auto; display: flex; flex-direction: column; gap: 2rem; }
            .event-item {
                background: rgba(255, 255, 255, 0.03);
                padding: 1.2rem;
                border-radius: 1.2rem;
                border: 1px solid rgba(255, 255, 255, 0.05);
                margin-bottom: 0.75rem;
            }
            .event-title { font-weight: 600; color: #fff; font-size: 1rem; margin-bottom: 0.3rem; display: block; }
            .event-time { font-size: 0.8rem; color: #14B8A6; opacity: 0.8; }
            
            .event-form {
                background: rgba(255, 255, 255, 0.02);
                padding: 1.5rem;
                border-radius: 1.5rem;
                border: 1px solid rgba(255, 255, 255, 0.04);
                display: flex;
                flex-direction: column;
                gap: 1rem;
            }
            input { background: #000; border: 1px solid #333; padding: 0.8rem; border-radius: 0.75rem; color: #fff; }
            button.submit { background: #14B8A6; color: #000; border: none; padding: 1rem; border-radius: 0.75rem; font-weight: 700; cursor: pointer; }
        </style>
        <div class="modal">
            <div class="header">
                <h2>Local Calendar</h2>
                <button class="close-btn" id="close-modal">&times;</button>
            </div>
            <div class="content-grid">
                <div class="calendar-view">
                    <div class="month-label">${monthName} ${year}</div>
                    <div class="month-grid">
                        ${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => `<div class="weekday">${d}</div>`).join('')}
                        ${Array(firstDay).fill(null).map(() => `<div></div>`).join('')}
                        ${Array(daysInMonth).fill(null).map((_, i) => {
            const day = i + 1;
            const isToday = day === now.getDate() && month === now.getMonth();
            return `<div class="day-cell ${isToday ? 'today' : ''} ${eventDays.has(day) ? 'has-event' : ''}">${day}</div>`;
        }).join('')}
                    </div>
                    
                    <form class="event-form" id="add-event-form" style="margin-top: 2rem;">
                        <h3 style="margin:0; font-size: 1rem; opacity: 0.7;">Quick Add</h3>
                        <input type="text" name="summary" placeholder="What's happening?" required>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                            <input type="datetime-local" name="start" required>
                            <input type="datetime-local" name="end" required>
                        </div>
                        <button type="submit" class="submit">Save Event</button>
                    </form>
                </div>
                
                <div class="events-overview">
                    <h3 style="margin:0; opacity: 0.7;">Agenda</h3>
                    <div class="events-list">
                        ${this.events.slice(0, 8).map(e => `
                            <div class="event-item">
                                <span class="event-title">${e.summary}</span>
                                <span class="event-time">${new Date(e.start).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                            </div>
                        `).join('') || '<p style="color: #444;">Quiet week ahead.</p>'}
                    </div>
                </div>
            </div>
        </div>
        `;

        this.shadowRoot.querySelector('#close-modal')?.addEventListener('click', () => this.toggle(false));
        this.shadowRoot.querySelector('#add-event-form')?.addEventListener('submit', (e) => this.addEvent(e));

        // Add click handlers for day cells to pre-fill the form
        this.shadowRoot.querySelectorAll('.day-cell').forEach(cell => {
            cell.addEventListener('click', () => {
                const day = cell.textContent;
                const date = new Date(year, month, parseInt(day || '1'));
                const isoStr = new Date(date.getTime() - (date.getTimezoneOffset() * 60000)).toISOString().slice(0, 16);
                const startInput = this.shadowRoot?.querySelector('input[name="start"]') as HTMLInputElement;
                if (startInput) startInput.value = isoStr;
            });
        });
    }
}

customElements.define('calendar-manager', CalendarManager);
