import { BUTTON_STYLES } from '../services/buttonStyles';
import { initGoo } from '../services/gooStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';

export class CalendarManager extends HTMLElement {
	private t: Record<string, string> = {};
	private events: any[] = [];
	private isOpen = false;
	private selectedDate: number | null = null;
	private viewMonth: number;
	private viewYear: number;
	private listenersBound = false;
	private isSubmitting = false;
	private abortController: AbortController | null = null;

	/** Bound handler for Escape and focus-trap while modal is open */
	private _handleKeyDown = (e: KeyboardEvent) => {
		if (e.key === 'Escape') {
			e.preventDefault();
			this.toggle(false);
			return;
		}
		if (e.key === 'Tab') {
			this._trapFocus(e);
		}
	};

	/** Keep Tab/Shift+Tab cycling within the modal */
	private _trapFocus(e: KeyboardEvent) {
		const modal = this.shadowRoot?.querySelector('.modal');
		if (!modal) return;
		const focusable = modal.querySelectorAll<HTMLElement>(
			'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
		);
		if (focusable.length === 0) return;
		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		if (e.shiftKey) {
			if (this.shadowRoot?.activeElement === first) {
				e.preventDefault();
				last.focus();
			}
		} else {
			if (this.shadowRoot?.activeElement === last) {
				e.preventDefault();
				first.focus();
			}
		}
	}

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
		const now = new Date();
		this.viewMonth = now.getMonth();
		this.viewYear = now.getFullYear();
	}

	private async loadTranslations() {
		if (window.__z_translations) { this.t = window.__z_translations; return; }
		try {
			await window.__z_translations_ready;
			if (window.__z_translations) { this.t = window.__z_translations; return; }
			const res = await fetch('/api/dashboard/translations');
			if (res.ok) this.t = await res.json();
		} catch (_) { }
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] || fallback;
	}

	connectedCallback() {
		this.loadTranslations().then(() => {
			this.render();
			this.fetchEvents();
		});
		initGoo(this);
		window.addEventListener('goo-changed', () => initGoo(this));
		window.addEventListener('open-calendar', () => this.toggle(true));
		window.addEventListener('refresh-data', (e: any) => {
			if (e.detail && e.detail.actions && e.detail.actions.includes('calendar')) {
				this.fetchEvents();
			}
		});
	}

	disconnectedCallback() {
		document.removeEventListener('keydown', this._handleKeyDown);
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

			// Trap focus inside modal and handle Escape
			document.addEventListener('keydown', this._handleKeyDown);

			// Focus close button after render settles
			requestAnimationFrame(() => {
				const closeBtn = this.shadowRoot?.querySelector('#close-modal') as HTMLElement;
				closeBtn?.focus();
			});
		} else {
			this.removeAttribute('open');
			document.removeEventListener('keydown', this._handleKeyDown);
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
		if (!confirm(this.tr('confirm_delete_event', 'Are you sure you want to delete this event?'))) return;
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
										${BUTTON_STYLES}
										${ACCESSIBILITY_STYLES}
										${SCROLLBAR_STYLES}
										:host {
												display: none;
												position: fixed;
												top: 0; left: 0; width: 100%; height: 100%;
												background: hsla(0, 0%, 0%, 0.4);
												backdrop-filter: blur(12px);
												z-index: 2000;
												align-items: center;
												justify-content: center;
												padding: 1.5rem;
												font-family: inherit;
										}
										:host([open]) { display: flex; }
										
										.modal {
												background: hsla(240, 10%, 9%, 0.9);
												border: 1px solid var(--border-medium, hsla(0, 0%, 100%, 0.12));
												border-radius: var(--radius-2xl, 1.5rem);
												width: 100%;
												max-width: 1000px;
												max-height: 85vh;
												display: flex;
												flex-direction: column;
												overflow: hidden;
												box-shadow: 0 40px 120px -20px hsla(0, 0%, 0%, 0.6);
												animation: modalPop 0.4s cubic-bezier(0.16, 1, 0.3, 1);
										}
										@keyframes modalPop {
												from { opacity: 0; transform: scale(0.95) translateY(30px); }
												to { opacity: 1; transform: scale(1) translateY(0); }
										}
										
										.header {
												padding: 1.5rem 2rem;
												border-bottom: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
												display: flex;
												justify-content: space-between;
												align-items: center;
												background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
										}
										
										.nav-controls {
												display: flex;
												align-items: center;
												gap: 1.5rem;
										}
										.month-label { 
												font-size: 1.25rem; 
												font-weight: 700; 
												color: var(--text-primary, hsla(0, 0%, 100%, 1)); 
												min-width: 180px; 
												text-align: center;
												letter-spacing: -0.01em;
										}
										.nav-btn {
												background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.05));
												border: 1px solid var(--border-medium, hsla(0, 0%, 100%, 0.12));
												color: var(--text-primary, hsla(0, 0%, 100%, 1));
												width: 32px; height: 32px;
												border-radius: var(--radius-sm, 0.35rem);
												display: flex; align-items: center; justify-content: center;
												cursor: pointer;
												transition: all 0.2s;
										}
										.nav-btn:hover { 
												background: var(--surface-hover, hsla(0, 0%, 100%, 0.06)); 
												border-color: var(--border-accent, hsla(173, 80%, 40%, 0.25)); 
										}

										.close-btn {
												background: transparent;
												border: none;
												color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
												font-size: 1.5rem;
												cursor: pointer;
												transition: color 0.2s;
										}
										.close-btn:hover { color: var(--text-primary, hsla(0, 0%, 100%, 1)); }

										.content-grid {
												flex: 1;
												display: grid;
												grid-template-columns: 1fr 340px;
												overflow: hidden;
										}
										
										.calendar-panel {
												padding: 2rem;
												border-right: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
												display: flex;
												flex-direction: column;
												gap: 2rem;
										}
										.month-grid {
												display: grid;
												grid-template-columns: repeat(7, 1fr);
												gap: 8px;
										}
										.weekday { text-align: center; font-size: 0.7rem; color: var(--text-faint, hsla(0, 0%, 100%, 0.2)); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding-bottom: 0.5rem; }
										.day-cell {
												aspect-ratio: 1.2;
												background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
												border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
												border-radius: var(--radius-md, 0.5rem);
												display: flex;
												align-items: center;
												justify-content: center;
												font-size: 0.95rem;
												color: var(--text-secondary, hsla(0, 0%, 100%, 0.7));
												position: relative;
												cursor: pointer;
												transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
										}
										.day-cell:hover { 
												background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.05)); 
												border-color: var(--border-accent, hsla(173, 80%, 40%, 0.25)); 
												color: var(--text-primary, hsla(0, 0%, 100%, 1)); 
												transform: translateY(-2px); 
										}
										.day-cell.today { 
												border-color: var(--accent-color, hsla(173, 80%, 40%, 1)); 
												color: var(--accent-color, hsla(173, 80%, 40%, 1)); 
												background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.1); 
												font-weight: 700; 
										}
										.day-cell.selected { 
												background: var(--accent-color, hsla(173, 80%, 40%, 1)); 
												color: hsla(0, 0%, 0%, 1); 
												border-color: var(--accent-color, hsla(173, 80%, 40%, 1)); 
												transform: translateY(-2px); 
												box-shadow: 0 10px 20px -5px rgba(var(--accent-color-rgb, 20, 184, 166), 0.4); 
												font-weight: 700; 
										}
										
										.event-dot {
												position: absolute;
												bottom: 6px;
												width: 4px; height: 4px;
												background: var(--accent-color, hsla(173, 80%, 40%, 1));
												border-radius: 50%;
												opacity: 0.8;
										}
										.day-cell.selected .event-dot { background: hsla(0, 0%, 0%, 1); }

										.agenda-panel {
												background: hsla(0, 0%, 100%, 0.015);
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
												color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
										}

										.events-list {
												flex: 1;
												overflow-y: auto;
												padding: 0 1.5rem;
												display: flex;
												flex-direction: column;
												gap: 0.75rem;
										}
										
										.event-card {
												padding: 1rem;
												background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
												border-radius: var(--radius-md, 0.5rem);
												border-left: 3px solid var(--accent-color, hsla(173, 80%, 40%, 1));
												transition: transform var(--duration-fast, 0.2s), background var(--duration-fast, 0.2s);
										}
										.event-card.birthday { border-left-color: var(--color-birthday, hsla(329, 86%, 70%, 1)); background: hsla(329, 86%, 70%, 0.05); }
										.event-card.local { border-left-color: var(--color-info, hsla(217, 91%, 60%, 1)); }

										.event-card:hover { transform: translateX(4px); background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.05)); }
										
										.event-card-inner { display: flex; justify-content: space-between; align-items: flex-start; }
										.event-info { flex: 1; }
.delete-event-btn {
												background: rgba(var(--color-danger-rgb, 239, 68, 68), 0.1);
												border: 1px solid rgba(var(--color-danger-rgb, 239, 68, 68), 0.25);
												color: var(--color-danger, hsla(0, 91%, 71%, 1));
												cursor: pointer;
												padding: 0.18rem 0.5rem;
												border-radius: var(--radius-xs, 0.35rem);
												font-size: 0.72rem;
												transition: background var(--duration-fast, 0.2s), border-color var(--duration-fast, 0.2s);
												flex-shrink: 0;
												min-width: 44px;
												min-height: 44px;
												display: inline-flex;
												align-items: center;
												justify-content: center;
											}
											.delete-event-btn:hover { background: rgba(var(--color-danger-rgb, 239, 68, 68), 0.2); border-color: rgba(var(--color-danger-rgb, 239, 68, 68), 0.5); }
										
										.event-title { font-size: 0.9rem; font-weight: 600; color: var(--text-primary, hsla(0, 0%, 100%, 1)); margin-bottom: 0.25rem; display: block; }
										.event-meta { font-size: 0.75rem; color: rgba(255,255,255,0.4); display: flex; align-items: center; gap: 0.5rem; }
										.badge { font-size: 0.6rem; padding: 1px 4px; border-radius: 4px; background: rgba(255,255,255,0.1); }

										.quick-add {
												padding: 1.5rem;
												border-top: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
												background: hsla(0, 0%, 100%, 0.01);
										}
										.event-form {
												display: flex;
												flex-direction: column;
												gap: 12px;
										}
										.event-form input {
												background: hsla(0, 0%, 100%, 0.04);
												border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
												border-radius: var(--radius-md, 0.5rem);
												color: var(--text-primary, hsla(0, 0%, 100%, 1));
												padding: 12px 1rem;
												font-size: 0.9rem;
												font-family: inherit;
												transition: all 0.2s;
										}
										.event-form input:focus {
												background: hsla(0, 0%, 100%, 0.07);
												border-color: var(--accent-color, hsla(173, 80%, 40%, 1));
												outline: none;
												box-shadow: 0 0 0 3px rgba(var(--accent-color-rgb, 20, 184, 166), 0.1);
										}
										.input-group {
												display: grid;
												grid-template-columns: 1fr 1fr;
												gap: 12px;
										}
										.submit {
												background: var(--accent-color, hsla(173, 80%, 40%, 1));
												color: hsla(0, 0%, 0%, 1);
												border: none;
												border-radius: var(--radius-md, 0.5rem);
												padding: 12px;
												font-weight: 700;
												cursor: pointer;
												transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
												box-shadow: 0 4px 15px -5px rgba(var(--accent-color-rgb, 20, 184, 166), 0.4);
										}
										.submit:hover { 
												transform: translateY(-2px); 
												box-shadow: 0 8px 25px -5px rgba(var(--accent-color-rgb, 20, 184, 166), 0.6); 
										}
											@media (forced-colors: active) {
												.day-cell.today { border-color: Highlight; }
												.day-cell.selected { background: Highlight; color: HighlightText; border-color: Highlight; }
												.event-dot { background: ButtonText; }
												.event-card { border-left-color: Highlight; }
												.event-card.birthday { border-left-color: LinkText; }
												.delete-event-btn { border: 1px solid LinkText; color: LinkText; }
												.badge { border: 1px solid ButtonText; }
											}
								</style>
								
<div class="modal" role="dialog" aria-modal="true" aria-labelledby="cal-modal-title">
						<div class="header">
								<div class="nav-controls">
										<button class="nav-btn" id="prev-month" aria-label="${this.tr('aria_prev_month', 'Previous month')}">&larr;</button>
										<div class="month-label" id="cal-modal-title"></div>
										<button class="nav-btn" id="next-month" aria-label="${this.tr('aria_next_month', 'Next month')}">&rarr;</button>
								</div>
								<button class="close-btn" id="close-modal" aria-label="${this.tr('aria_close_calendar', 'Close calendar')}">&times;</button>
										</div>
										
										<div class="content-grid">
												<div class="calendar-panel">
														<div class="month-grid"></div>
												</div>
												
												<div class="agenda-panel">
														<div class="agenda-header"></div>
														<div class="events-list" role="list"></div>
														
														<div class="quick-add">
																<form class="event-form" id="add-event-form">
																		<label for="cal-summary" class="sr-only">${this.tr('aria_event_title', 'Event title')}</label>
																		<input type="text" id="cal-summary" name="summary" placeholder="${this.tr('quick_add_event', 'Quick add event...')}" required aria-required="true">
																		<div class="input-group">
																				<label for="cal-start" class="sr-only">${this.tr('aria_start_time', 'Start date and time')}</label>
																				<input type="datetime-local" id="cal-start" name="start" required aria-required="true" aria-label="${this.tr('aria_start_time', 'Start date and time')}">
																				<label for="cal-end" class="sr-only">${this.tr('aria_end_time', 'End date and time')}</label>
																				<input type="datetime-local" id="cal-end" name="end" aria-label="${this.tr('aria_end_time', 'End date and time (optional)')}">
																		</div>
																		<button type="submit" class="submit">${this.tr('add_to_calendar', 'Add to Calendar')}</button>
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

		let displayedEvents: typeof this.events;
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
								<div class="event-card ${typeClass}" role="listitem">
										<div class="event-card-inner">
												<div class="event-info">
														<input type="text" class="event-title-edit" 
																value="${e.summary}" 
																data-id="${e.id}"
																${!e.is_local || e.is_birthday ? 'disabled' : ''}
																aria-label="${!e.is_local || e.is_birthday ? this.tr('aria_event', 'Event') + ': ' : this.tr('aria_edit_event_title', 'Edit event title') + ': '}${e.summary}"
																style="background: transparent; border: none; font-size: 0.9rem; font-weight: 600; color: var(--text-primary, hsla(0, 0%, 100%, 1)); width: 100%; outline: none;">
														<div class="event-meta">
																<span>${timeStr === '00:00' ? this.tr('all_day', 'All Day') : timeStr}</span>
																${e.person ? `<span class="badge">${e.person}</span>` : ''}
														</div>
												</div>
												${e.is_local && !e.is_birthday ? `
													<div style="display: flex; gap: 4px;">
														<button class="delete-event-btn" data-id="${e.id}" title="Delete event" aria-label="${this.tr('aria_delete_event', 'Delete event')}: ${e.summary}">&times;</button>
													</div>
												` : ''}
										</div>
								</div>
						`;
		}).join('') || `<div style="padding: 2rem; text-align: center; opacity: 0.3;">${this.tr('clear_schedule', 'Clear schedule.')}</div>`;

		const monthGrid = this.shadowRoot.querySelector('.month-grid')!;
		monthGrid.innerHTML = `
									${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d, i) => {
										const fullDays = [
									this.tr('sun', 'Sunday'), this.tr('mon', 'Monday'), this.tr('tue', 'Tuesday'),
									this.tr('wed', 'Wednesday'), this.tr('thu', 'Thursday'), this.tr('fri', 'Friday'), this.tr('sat', 'Saturday')
								];
										return `<div class="weekday" role="columnheader" aria-label="${fullDays[i]}">${d}</div>`;
									}).join('')}
						${Array(firstDay).fill(null).map(() => `<div></div>`).join('')}
						${Array(daysInMonth).fill(null).map((_, i) => {
			const day = i + 1;
			const isToday = day === now.getDate() && this.viewMonth === now.getMonth() && this.viewYear === now.getFullYear();
			const isSelected = day === this.selectedDate;
			return `
										<div class="day-cell ${isToday ? 'today' : ''} ${isSelected ? 'selected' : ''}" data-day="${day}" role="button" tabindex="0" aria-label="${monthName} ${day}, ${this.viewYear}" ${isToday ? 'aria-current="date"' : ''} aria-pressed="${isSelected ? 'true' : 'false'}">
												${day}
												${eventDays.has(day) ? '<div class="event-dot" aria-hidden="true"></div>' : ''}
										</div>`;
		}).join('')}
				`;

		this.shadowRoot.querySelector('.events-list')!.innerHTML = eventsListHtml;
		this.shadowRoot.querySelector('.agenda-header')!.textContent = this.selectedDate ? `${this.tr('schedule_for', 'Schedule for')} ${monthName} ${this.selectedDate}` : this.tr('coming_up', 'Coming Up');

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
			const selectDay = () => {
				const day = parseInt(cell.getAttribute('data-day') || '1');
				this.selectedDate = day;
				this.render();

				const date = new Date(this.viewYear, this.viewMonth, day);
				const isoStr = new Date(date.getTime() - (date.getTimezoneOffset() * 60000)).toISOString().slice(0, 16);
				const startInput = this.shadowRoot?.querySelector('input[name="start"]') as HTMLInputElement;
				if (startInput) startInput.value = isoStr;
			};
			cell.addEventListener('click', selectDay);
			cell.addEventListener('keydown', (e: Event) => {
				const ke = e as KeyboardEvent;
				if (ke.key === 'Enter' || ke.key === ' ') {
					ke.preventDefault();
					selectDay();
				}
			});
		});
	}
}

customElements.define('calendar-manager', CalendarManager);
