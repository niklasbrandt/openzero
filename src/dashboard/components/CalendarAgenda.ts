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
		window.addEventListener('refresh-data', (e: any) => {
			if (e.detail && e.detail.actions && e.detail.actions.includes('calendar')) {
				this.fetchEvents();
			}
		});
	}

	async deleteEvent(id: string) {
		if (!confirm('Delete this local event?')) return;
		try {
			const response = await fetch(`/api/dashboard/calendar/local/${id}`, { method: 'DELETE' });
			if (response.ok) {
				this.fetchEvents();
				window.dispatchEvent(new CustomEvent('refresh-data', { detail: { actions: ['calendar'] } }));
			}
		} catch (e) {
			console.error('Failed to delete event', e);
		}
	}

	async updateEvent(id: string, summary: string) {
		try {
			const response = await fetch(`/api/dashboard/calendar/local/${id}`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ summary })
			});
			if (response.ok) {
				this.fetchEvents();
				window.dispatchEvent(new CustomEvent('refresh-data', { detail: { actions: ['calendar'] } }));
			}
		} catch (e) {
			console.error('Failed to update event', e);
		}
	}

	async fetchEvents() {
		try {
			const response = await fetch('/api/dashboard/calendar');
			if (!response.ok) throw new Error('API error');
			this.events = await response.json();

			// Check if we have any non-local events (simple heuristic for Google sync)
			const hasGoogle = this.events.some(e => !e.is_local);
			const link = this.shadowRoot?.querySelector('.calendar-link');
			if (link) {
				if (hasGoogle) {
					link.setAttribute('href', 'https://calendar.google.com');
					link.setAttribute('target', '_blank');
					link.setAttribute('title', 'Open Google Calendar'); // Ensure title is set for Google
				} else {
					link.setAttribute('href', '#');
					link.addEventListener('click', (e) => {
						e.preventDefault();
						window.dispatchEvent(new CustomEvent('open-calendar'));
					});
					link.setAttribute('title', 'Open Local Calendar');
				}
			}

			this.displayEvents();
		} catch (e) {
			console.error('Failed to fetch calendar', e);
			const list = this.shadowRoot?.querySelector('#event-list');
			if (list) {
				list.innerHTML = '<div class="empty">Unable to load agenda. Check backend/integration.</div>';
			}
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

				const isBirthday = e.summary.toLowerCase().includes('birthday');
				return `
					<div class="event-item ${isBirthday ? 'birthday-item' : ''}" role="listitem">
						<div class="time-box">
							<span class="day">${day}</span>
							<span class="time">${time !== '00:00' ? time : 'All day'}</span>
						</div>
						<div class="details">
							<div class="summary-row" style="display: flex; justify-content: space-between; align-items: flex-start;">
								<span class="summary" style="flex: 1;">
									${!e.is_local ? '<span class="local-indicator" style="color: #14B8A6; background: rgba(20, 184, 166, 0.1); border-color: rgba(20, 184, 166, 0.2);">Google</span> ' : ''}
									<input type="text" class="event-title-edit" 
										value="${e.summary}" 
										data-id="${e.id}"
										${!e.is_local || e.is_birthday ? 'disabled' : ''}
										style="background: transparent; border: none; font-size: 0.9rem; font-weight: 500; color: #fff; width: 100%; outline: none;">
								</span>
								${e.is_local && !e.is_birthday ? `<button class="delete-btn" data-id="${e.id}" title="Delete event" style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); color: #f87171; cursor: pointer; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; transition: all 0.2s;">✕</button>` : ''}
							</div>
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

		if (list) {
			list.querySelectorAll('.delete-btn').forEach(btn => {
				btn.addEventListener('click', (e) => {
					const id = (e.currentTarget as HTMLElement).getAttribute('data-id');
					if (id) this.deleteEvent(id);
				});
			});

			list.querySelectorAll('.event-title-edit').forEach(input => {
				input.addEventListener('change', (e) => {
					const el = e.currentTarget as HTMLInputElement;
					const id = el.getAttribute('data-id');
					if (id) this.updateEvent(id, el.value);
				});
				input.addEventListener('keydown', (e: any) => {
					if (e.key === 'Enter') {
						e.target.blur();
					}
				});
			});
		}
	}

	render() {
		if (this.shadowRoot) {
			this.shadowRoot.innerHTML = `
				<style>
					h2 { font-size: 1.5rem; font-weight: bold; margin: 0; color: #fff; letter-spacing: 0.02em; }
					:host { display: block; }
					.card { height: 100%; display: flex; flex-direction: column; }
					.header-container { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
					.calendar-link {
						color: rgba(255, 255, 255, 0.5);
						transition: color 0.2s;
						display: flex;
						align-items: center;
						justify-content: center;
						padding: 0.3rem;
						border-radius: 0.4rem;
					}
					.calendar-link:hover { color: #14B8A6; background: rgba(255, 255, 255, 0.05); }
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
					.local-indicator {
						font-size: 0.65rem;
						color: #0066FF;
						background: rgba(0, 102, 255, 0.1);
						border: 1px solid rgba(0, 102, 255, 0.2);
						padding: 0.1rem 0.4rem;
						border-radius: 0.3rem;
						margin-right: 0.3rem;
						vertical-align: middle;
					}
					@keyframes rainbow-border {
						0% { border-color: #ff0000; box-shadow: 0 0 5px #ff000033; }
						20% { border-color: #ff8800; }
						40% { border-color: #ffff00; }
						60% { border-color: #00ff00; }
						80% { border-color: #0088ff; }
						100% { border-color: #cc00ff; box-shadow: 0 0 5px #cc00ff33; }
					}
					.birthday-item {
						border: 1px solid #ff0000 !important;
						animation: rainbow-border 3s linear infinite;
						background: rgba(255, 255, 255, 0.05) !important;
					}
					.birthday-item .day { color: #f472b6 !important; }
					.birthday-item .summary { color: #fbcfe8 !important; }
					.empty { font-size: 0.85rem; color: rgba(255, 255, 255, 0.3); text-align: center; padding: 2rem; }
					.filter-btn:focus-visible, .calendar-link:focus-visible { 
						outline: 2px solid #14B8A6; 
						outline-offset: 2px; 
					}
				</style>
				<div class="card">
					<div class="header-container">
						<h2>Calendar Agenda</h2>
						<a href="https://calendar.google.com" target="_blank" class="calendar-link" title="Open Google Calendar">
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
								<line x1="16" y1="2" x2="16" y2="6"></line>
								<line x1="8" y1="2" x2="8" y2="6"></line>
								<line x1="3" y1="10" x2="21" y2="10"></line>
								<polyline points="8 14 12 18 16 14"></polyline>
							</svg>
						</a>
					</div>
					<div id="filters"></div>
					<div id="event-list" role="list">Loading events...</div>
				</div>
			`;
		}
	}
}

customElements.define('calendar-agenda', CalendarAgenda);
