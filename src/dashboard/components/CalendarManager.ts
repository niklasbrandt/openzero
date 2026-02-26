export class CalendarManager extends HTMLElement {
	private events: any[] = [];
	private isOpen = false;
	private selectedDate: number | null = null;
	private viewMonth: number;
	private viewYear: number;
	private listenersBound = false;
	private isSubmitting = false;
	private abortController: AbortController | null = null;

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
		const now = new Date();
		this.viewMonth = now.getMonth();
		this.viewYear = now.getFullYear();
	}

	connectedCallback() {
		this.render();
		this.fetchEvents();
		window.addEventListener('open-calendar', () => this.toggle(true));
		window.addEventListener('refresh-data', (e: any) => {
			if (e.detail && e.detail.actions && e.detail.actions.includes('calendar')) {
				this.fetchEvents();
			}
		});
	}

	async fetchEvents() {
		if (this.abortController) {
			this.abortController.abort();
		}
		this.abortController = new AbortController();
		const signal = this.abortController.signal;

		try {
			const url = new URL('/api/dashboard/calendar', window.location.origin);
			url.searchParams.set('year', this.viewYear.toString());
			url.searchParams.set('month', (this.viewMonth + 1).toString());

			const response = await fetch(url.toString(), { signal });
			if (response.ok) {
				const data = await response.json();
				if (!signal.aborted) {
					this.events = data;
					this.render();
				}
			}
		} catch (e: any) {
			if (e.name !== 'AbortError') {
				console.error('Failed to fetch events', e);
			}
		} finally {
			if (this.abortController?.signal === signal) {
				this.abortController = null;
			}
		}
	}

	toggle(force?: boolean) {
		this.isOpen = force !== undefined ? force : !this.isOpen;
		if (this.isOpen) {
			// Reset to current month/state on reopen
			const now = new Date();
			this.viewMonth = now.getMonth();
			this.viewYear = now.getFullYear();
			this.selectedDate = null;

			this.setAttribute('open', '');
			this.fetchEvents();
		} else {
			this.removeAttribute('open');
		}
		this.render();
	}

	changeMonth(delta: number) {
		this.viewMonth += delta;
		if (this.viewMonth > 11) {
			this.viewMonth = 0;
			this.viewYear++;
		} else if (this.viewMonth < 0) {
			this.viewMonth = 11;
			this.viewYear--;
		}
		this.selectedDate = null;
		this.fetchEvents();
	}

	async addEvent(e: Event) {
		e.preventDefault();
		if (this.isSubmitting) return;
		this.isSubmitting = true;

		const form = e.target as HTMLFormElement;
		const formData = new FormData(form);
		const data = {
			summary: formData.get('summary'),
			start_time: formData.get('start'),
			end_time: formData.get('end') || null,
			is_all_day: true // Default to all day
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
				window.dispatchEvent(new CustomEvent('refresh-data', { detail: { actions: ['calendar'] } }));
			}
		} catch (err) {
			console.error('Failed to add event', err);
		} finally {
			this.isSubmitting = false;
		}
	}

	async deleteEvent(id: string) {
		if (!confirm('Are you sure you want to delete this event?')) return;
		try {
			const response = await fetch(`/api/dashboard/calendar/local/${id}`, {
				method: 'DELETE'
			});
			if (response.ok) {
				this.fetchEvents();
				window.dispatchEvent(new CustomEvent('refresh-data', { detail: { actions: ['calendar'] } }));
			}
		} catch (err) {
			console.error('Failed to delete event', err);
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
		} catch (err) {
			console.error('Failed to update event', err);
		}
	}

	render() {
		if (!this.shadowRoot) return;

		// 1. First-time template injection
		if (!this.shadowRoot.querySelector('.modal')) {
			this.shadowRoot.innerHTML = `
								<style>
										:host {
												display: none;
												position: fixed;
												top: 0; left: 0; width: 100%; height: 100%;
												background: rgba(0, 0, 0, 0.4);
												backdrop-filter: blur(12px);
												z-index: 2000;
												align-items: center;
												justify-content: center;
												padding: 1.5rem;
												font-family: 'Inter', system-ui, sans-serif;
										}
										:host([open]) { display: flex; }
										
										.modal {
												background: rgba(20, 20, 25, 0.9);
												border: 1px solid rgba(255, 255, 255, 0.12);
												border-radius: 2rem;
												width: 100%;
												max-width: 1000px;
												max-height: 85vh;
												display: flex;
												flex-direction: column;
												overflow: hidden;
												box-shadow: 0 40px 120px -20px rgba(0, 0, 0, 0.6);
												animation: modalPop 0.4s cubic-bezier(0.16, 1, 0.3, 1);
										}
										@keyframes modalPop {
												from { opacity: 0; transform: scale(0.95) translateY(30px); }
												to { opacity: 1; transform: scale(1) translateY(0); }
										}
										
										.header {
												padding: 1.5rem 2rem;
												border-bottom: 1px solid rgba(255, 255, 255, 0.08);
												display: flex;
												justify-content: space-between;
												align-items: center;
												background: rgba(255, 255, 255, 0.02);
										}
										
										.nav-controls {
												display: flex;
												align-items: center;
												gap: 1.5rem;
										}
										.month-label { 
												font-size: 1.25rem; 
												font-weight: 700; 
												color: #fff; 
												min-width: 180px; 
												text-align: center;
												letter-spacing: -0.01em;
										}
										.nav-btn {
												background: rgba(255, 255, 255, 0.06);
												border: 1px solid rgba(255, 255, 255, 0.1);
												color: #fff;
												width: 32px; height: 32px;
												border-radius: 8px;
												display: flex; align-items: center; justify-content: center;
												cursor: pointer;
												transition: all 0.2s;
										}
										.nav-btn:hover { background: rgba(255, 255, 255, 0.12); border-color: rgba(255,255,255,0.2); }

										.close-btn {
												background: transparent;
												border: none;
												color: rgba(255, 255, 255, 0.4);
												font-size: 1.5rem;
												cursor: pointer;
												transition: color 0.2s;
										}
										.close-btn:hover { color: #fff; }

										.content-grid {
												flex: 1;
												display: grid;
												grid-template-columns: 1fr 340px;
												overflow: hidden;
										}
										
										.calendar-panel {
												padding: 2rem;
												border-right: 1px solid rgba(255, 255, 255, 0.06);
												display: flex;
												flex-direction: column;
												gap: 2rem;
										}
										.month-grid {
												display: grid;
												grid-template-columns: repeat(7, 1fr);
												gap: 8px;
										}
										.weekday { text-align: center; font-size: 0.7rem; color: rgba(255,255,255,0.3); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding-bottom: 0.5rem; }
										.day-cell {
												aspect-ratio: 1.2;
												background: rgba(255, 255, 255, 0.03);
												border: 1px solid rgba(255, 255, 255, 0.06);
												border-radius: 12px;
												display: flex;
												align-items: center;
												justify-content: center;
												font-size: 0.95rem;
												color: rgba(255,255,255,0.6);
												position: relative;
												cursor: pointer;
												transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
										}
										.day-cell:hover { background: rgba(255, 255, 255, 0.08); border-color: rgba(255, 255, 255, 0.2); color: #fff; transform: translateY(-2px); }
										.day-cell.today { border-color: #14B8A6; color: #14B8A6; background: rgba(20, 184, 166, 0.08); font-weight: 700; }
										.day-cell.selected { background: #14B8A6; color: #000; border-color: #14B8A6; transform: translateY(-2px); box-shadow: 0 10px 20px -5px rgba(20, 184, 166, 0.4); font-weight: 700; }
										
										.event-dot {
												position: absolute;
												bottom: 6px;
												width: 4px; height: 4px;
												background: #14B8A6;
												border-radius: 50%;
												opacity: 0.8;
										}
										.day-cell.selected .event-dot { background: #000; }

										.agenda-panel {
												background: rgba(255, 255, 255, 0.015);
												display: flex;
												flex-direction: column;
												overflow: hidden;
										}
										
										.agenda-header {
												padding: 1.5rem 1.5rem 0.75rem;
												font-size: 0.75rem;
												font-weight: 700;
												text-transform: uppercase;
												letter-spacing: 0.1em;
												color: rgba(255, 255, 255, 0.4);
										}

										.events-list {
												flex: 1;
												overflow-y: auto;
												padding: 0 1.5rem;
												display: flex;
												flex-direction: column;
												gap: 0.75rem;
										}
										.events-list::-webkit-scrollbar { width: 4px; }
										.events-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
										
										.event-card {
												padding: 1rem;
												background: rgba(255, 255, 255, 0.04);
												border-radius: 14px;
												border-left: 3px solid #14B8A6;
												transition: transform 0.2s;
										}
										.event-card.birthday { border-left-color: #F472B6; background: rgba(244, 114, 182, 0.05); }
										.event-card.local { border-left-color: #60A5FA; }

										.event-card:hover { transform: translateX(4px); background: rgba(255, 255, 255, 0.07); }
										
										.event-card-inner { display: flex; justify-content: space-between; align-items: flex-start; }
										.event-info { flex: 1; }
										.delete-event-btn { 
												background: transparent; 
												border: none; 
												color: rgba(255, 255, 255, 0.2); 
												cursor: pointer; 
												padding: 4px;
												border-radius: 4px;
												transition: all 0.2s;
										}
										.delete-event-btn:hover { color: #f87171; background: rgba(248, 113, 113, 0.1); }
										
										.event-title { font-size: 0.9rem; font-weight: 600; color: #fff; margin-bottom: 0.25rem; display: block; }
										.event-meta { font-size: 0.75rem; color: rgba(255,255,255,0.4); display: flex; align-items: center; gap: 0.5rem; }
										.badge { font-size: 0.6rem; padding: 1px 4px; border-radius: 4px; background: rgba(255,255,255,0.1); }

										.quick-add {
												padding: 1.5rem;
												border-top: 1px solid rgba(255, 255, 255, 0.06);
												background: rgba(0, 0, 0, 0.2);
										}
										.event-form { display: flex; flex-direction: column; gap: 0.75rem; }
										.input-group { display: flex; flex-direction: column; gap: 0.5rem; }
										
										input { 
												background: rgba(255, 255, 255, 0.05); 
												border: 1px solid rgba(255, 255, 255, 0.1); 
												padding: 0.6rem 0.8rem; 
												border-radius: 10px; 
												color: #fff; 
												font-size: 0.85rem;
												outline: none;
										}
										input:focus { border-color: #14B8A6; background: rgba(255, 255, 255, 0.08); }
										
										button.submit { 
												background: #14B8A6; 
												color: #000; 
												border: none; 
												padding: 0.75rem; 
												border-radius: 10px; 
												font-weight: 700; 
												cursor: pointer; 
												font-size: 0.85rem;
												transition: transform 0.2s, opacity 0.2s;
										}
										button.submit:hover { transform: translateY(-1px); opacity: 0.9; }
								</style>
								
								<div class="modal">
										<div class="header">
												<div class="nav-controls">
														<button class="nav-btn" id="prev-month">&larr;</button>
														<div class="month-label"></div>
														<button class="nav-btn" id="next-month">&rarr;</button>
												</div>
												<button class="close-btn" id="close-modal">&times;</button>
										</div>
										
										<div class="content-grid">
												<div class="calendar-panel">
														<div class="month-grid"></div>
												</div>
												
												<div class="agenda-panel">
														<div class="agenda-header"></div>
														<div class="events-list"></div>
														
														<div class="quick-add">
																<form class="event-form" id="add-event-form">
																		<input type="text" name="summary" placeholder="Quick add event..." required>
																		<div class="input-group">
																				<input type="datetime-local" name="start" required>
																				<input type="datetime-local" name="end">
																		</div>
																		<button type="submit" class="submit">Add to Calendar</button>
																</form>
														</div>
												</div>
										</div>
								</div>
						`;

		}

		// 2. Dynamic Update (Partial Rendering)
		const now = new Date();
		const firstDay = new Date(this.viewYear, this.viewMonth, 1).getDay();
		const daysInMonth = new Date(this.viewYear, this.viewMonth + 1, 0).getDate();
		const monthName = new Date(this.viewYear, this.viewMonth).toLocaleString('default', { month: 'long' });

		this.shadowRoot.querySelector('.month-label')!.textContent = `${monthName} ${this.viewYear}`;

		const eventDays = new Set(
			this.events.filter(e => {
				const d = new Date(e.start);
				return d.getMonth() === this.viewMonth && d.getFullYear() === this.viewYear;
			}).map(e => new Date(e.start).getDate())
		);

		let displayedEvents = this.events;
		if (this.selectedDate) {
			displayedEvents = this.events.filter(e => {
				if (!e.start) return false;
				const d = new Date(e.start);
				return d.getDate() === this.selectedDate && d.getMonth() === this.viewMonth && d.getFullYear() === this.viewYear;
			});
		} else {
			displayedEvents = this.events.filter(e => {
				if (!e.start) return false;
				const d = new Date(e.start);
				return d.getMonth() === this.viewMonth && d.getFullYear() === this.viewYear;
			}).sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime()).slice(0, 15);
		}

		const eventsListHtml = displayedEvents.map(e => {
			const date = new Date(e.start);
			const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
			const typeClass = e.is_birthday ? 'birthday' : (e.is_local ? 'local' : '');
			return `
								<div class="event-card ${typeClass}">
										<div class="event-card-inner">
												<div class="event-info">
														<input type="text" class="event-title-edit" 
																value="${e.summary}" 
																data-id="${e.id}"
																${!e.is_local || e.is_birthday ? 'disabled' : ''}
																style="background: transparent; border: none; font-size: 0.9rem; font-weight: 600; color: #fff; width: 100%; outline: none;">
														<div class="event-meta">
																<span>${timeStr === '00:00' ? 'All Day' : timeStr}</span>
																${e.person ? `<span class="badge">${e.person}</span>` : ''}
														</div>
												</div>
												${e.is_local && !e.is_birthday ? `
													<div style="display: flex; gap: 4px;">
														<button class="delete-event-btn" data-id="${e.id}" title="Delete event" style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); color: #f87171; cursor: pointer; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: bold;">✕</button>
													</div>
												` : ''}
										</div>
								</div>
						`;
		}).join('') || '<div style="padding: 2rem; text-align: center; opacity: 0.3;">Clear schedule.</div>';

		const monthGrid = this.shadowRoot.querySelector('.month-grid')!;
		monthGrid.innerHTML = `
						${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => `<div class="weekday">${d}</div>`).join('')}
						${Array(firstDay).fill(null).map(() => `<div></div>`).join('')}
						${Array(daysInMonth).fill(null).map((_, i) => {
			const day = i + 1;
			const isToday = day === now.getDate() && this.viewMonth === now.getMonth() && this.viewYear === now.getFullYear();
			const isSelected = day === this.selectedDate;
			return `
										<div class="day-cell ${isToday ? 'today' : ''} ${isSelected ? 'selected' : ''}" data-day="${day}">
												${day}
												${eventDays.has(day) ? '<div class="event-dot"></div>' : ''}
										</div>`;
		}).join('')}
				`;

		this.shadowRoot.querySelector('.events-list')!.innerHTML = eventsListHtml;
		this.shadowRoot.querySelector('.agenda-header')!.textContent = this.selectedDate ? `Schedule for ${monthName} ${this.selectedDate}` : 'Coming Up';

		// Only attach persistent listeners once if they aren't already attached
		if (!this.listenersBound) {
			this.shadowRoot.querySelector('#close-modal')?.addEventListener('click', () => this.toggle(false));
			this.shadowRoot.querySelector('#prev-month')?.addEventListener('click', () => this.changeMonth(-1));
			this.shadowRoot.querySelector('#next-month')?.addEventListener('click', () => this.changeMonth(1));
			this.shadowRoot.querySelector('#add-event-form')?.addEventListener('submit', (e) => this.addEvent(e));
			this.listenersBound = true;
		}

		this.shadowRoot.querySelectorAll('.delete-event-btn').forEach(btn => {
			btn.addEventListener('click', (e) => {
				e.stopPropagation();
				const id = (e.currentTarget as HTMLElement).getAttribute('data-id');
				if (id) this.deleteEvent(id);
			});
		});

		this.shadowRoot.querySelectorAll('.event-title-edit').forEach(input => {
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

		this.shadowRoot.querySelectorAll('.day-cell[data-day]').forEach(cell => {
			cell.addEventListener('click', () => {
				const day = parseInt(cell.getAttribute('data-day') || '1');
				this.selectedDate = day;
				this.render();

				const date = new Date(this.viewYear, this.viewMonth, day);
				const isoStr = new Date(date.getTime() - (date.getTimezoneOffset() * 60000)).toISOString().slice(0, 16);
				const startInput = this.shadowRoot?.querySelector('input[name="start"]') as HTMLInputElement;
				if (startInput) startInput.value = isoStr;
			});
		});
	}
}

customElements.define('calendar-manager', CalendarManager);
