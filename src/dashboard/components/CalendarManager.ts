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

        this.shadowRoot.innerHTML = `
        <style>
            :host {
                display: none;
                position: fixed;
                top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0, 0, 0, 0.6);
                backdrop-filter: blur(12px);
                z-index: 2000;
                align-items: center;
                justify-content: center;
                padding: 2rem;
            }
            :host([open]) { display: flex; }
            
            .modal {
                background: rgba(15, 15, 15, 0.85);
                backdrop-filter: blur(25px) ;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 2rem;
                width: 100%;
                max-width: 900px;
                max-height: 85vh;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                box-shadow: 0 40px 100px -20px rgba(0, 0, 0, 0.7);
                animation: modalPop 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            }
            @keyframes modalPop {
                from { opacity: 0; transform: scale(0.95) translateY(20px); }
                to { opacity: 1; transform: scale(1) translateY(0); }
            }
            .header {
                padding: 2rem;
                background: linear-gradient(to bottom, rgba(255,255,255,0.03), transparent);
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            h2 { 
                margin: 0; 
                font-size: 1.8rem; 
                background: linear-gradient(135deg, #fff 0%, rgba(255,255,255,0.6) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-weight: 700;
            }
            .close-btn {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #fff;
                width: 32px; height: 32px;
                border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                cursor: pointer;
                transition: all 0.2s;
                font-size: 1.2rem;
            }
            .close-btn:hover { background: rgba(239, 68, 68, 0.2); border-color: #ef4444; }
            
            .content {
                padding: 2.5rem;
                overflow-y: auto;
                display: grid;
                grid-template-columns: 350px 1fr;
                gap: 3rem;
            }
            
            .event-form {
                display: flex;
                flex-direction: column;
                gap: 1.2rem;
                background: rgba(255, 255, 255, 0.03);
                padding: 1.5rem;
                border-radius: 1.2rem;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            input, textarea {
                background: rgba(0, 0, 0, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 0.75rem;
                padding: 0.8rem 1rem;
                color: #fff;
                font-family: inherit;
                font-size: 0.9rem;
                transition: border-color 0.2s;
            }
            input:focus { border-color: #14B8A6; outline: none; }
            button.submit {
                background: linear-gradient(135deg, #14B8A6 0%, #0D9488 100%);
                color: #fff;
                border: none;
                padding: 1rem;
                border-radius: 0.75rem;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
                margin-top: 0.5rem;
            }
            button.submit:hover { transform: translateY(-2px); box-shadow: 0 4px 20px rgba(20, 184, 166, 0.3); }
            
            .events-list {
                display: flex;
                flex-direction: column;
                gap: 1rem;
            }
            .event-item {
                background: rgba(255, 255, 255, 0.03);
                padding: 1.2rem;
                border-radius: 1rem;
                border: 1px solid rgba(255, 255, 255, 0.05);
                transition: transform 0.2s;
            }
            .event-item:hover { transform: translateX(5px); background: rgba(255, 255, 255, 0.05); }
            .event-title { font-weight: 600; color: #fff; font-size: 1.05rem; display: block; margin-bottom: 0.4rem; }
            .event-time { font-size: 0.85rem; color: #14B8A6; opacity: 0.8; }
            .local-tag {
                font-size: 0.7rem;
                background: rgba(0, 102, 255, 0.15);
                color: #60a5fa;
                padding: 0.2rem 0.6rem;
                border-radius: 0.5rem;
                margin-left: 0.75rem;
                border: 1px solid rgba(0, 102, 255, 0.2);
            }
            h3 { color: #fff; font-size: 1.1rem; margin-top: 0; margin-bottom: 1.5rem; letter-spacing: 0.5px; opacity: 0.7; }
        </style>
        <div class="modal">
            <div class="header">
                <h2>Agenda & Local Events</h2>
                <button class="close-btn" id="close-modal">&times;</button>
            </div>
            <div class="content">
                <div>
                    <h3 style="color: rgba(255,255,255,0.6); font-size: 1rem; margin-top: 0;">Add Local Event</h3>
                    <form class="event-form" id="add-event-form">
                        <input type="text" name="summary" placeholder="Event Summary" required>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
                            <div>
                                <label style="display:block; font-size: 0.7rem; color: #666; margin-bottom: 0.2rem;">Start</label>
                                <input type="datetime-local" name="start" required style="width: 90%;">
                            </div>
                            <div>
                                <label style="display:block; font-size: 0.7rem; color: #666; margin-bottom: 0.2rem;">End</label>
                                <input type="datetime-local" name="end" required style="width: 90%;">
                            </div>
                        </div>
                        <button type="submit" class="submit">Add to Calendar</button>
                    </form>
                </div>
                <div>
                    <h3 style="color: rgba(255,255,255,0.6); font-size: 1rem; margin-top: 0;">Upcoming</h3>
                    <div class="events-list">
                        ${this.events.map(e => `
                            <div class="event-item">
                                <span class="event-title">${e.summary}${e.is_local ? '<span class="local-tag">Local</span>' : ''}</span>
                                <span class="event-time">${new Date(e.start).toLocaleString()}</span>
                            </div>
                        `).join('') || '<p style="color: #444; text-align: center;">No events scheduled.</p>'}
                    </div>
                </div>
            </div>
        </div>
        `;

        this.shadowRoot.querySelector('#close-modal')?.addEventListener('click', () => this.toggle(false));
        this.shadowRoot.querySelector('#add-event-form')?.addEventListener('submit', (e) => this.addEvent(e));
    }
}

customElements.define('calendar-manager', CalendarManager);
