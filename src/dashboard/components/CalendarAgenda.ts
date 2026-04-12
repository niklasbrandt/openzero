import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';

interface CalendarEvent {
	id: string;
	summary: string;
	start: string;
	end?: string;
	is_all_day: boolean;
	is_birthday?: boolean;
	is_local?: boolean;
	person?: string;
}

export class CalendarAgenda extends HTMLElement {
	private events: CalendarEvent[] = [];
	private filterPerson: string | null = null;
	private t: Record<string, string> = {};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
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

	private esc(s: string | undefined | null): string {
		if (!s) return '';
		return String(s)
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#39;');
	}

	connectedCallback() {
		this.loadTranslations().then(() => {
			this.render();
			this.fetchEvents();
		});
		window.addEventListener('refresh-data', (e: Event) => {
			const ce = e as CustomEvent;
			if (ce.detail && ce.detail.actions && ce.detail.actions.includes('calendar')) {
				this.fetchEvents();
			}
		});
	}

	async deleteEvent(id: string) {
		if (!confirm(this.tr('confirm_delete_event', 'Delete this local event?'))) return;
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
				list.removeAttribute('role');
				list.innerHTML = `<div class="empty-state">${this.tr('api_error_calendar', 'Unable to load agenda. Check backend/integration.')}</div>`;
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

			if (filtered.length > 0) {
				list.setAttribute('role', 'list');
			} else {
				list.removeAttribute('role');
			}

			list.innerHTML = filtered.map(e => {
				const date = new Date(e.start);
				const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
				const day = date.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' });

				const isBirthday = e.summary.toLowerCase().includes('birthday');
				return `
					<div class="event-item ${isBirthday ? 'birthday-item' : ''}" role="listitem">
						<div class="time-box">
							<span class="day">${day}</span>
							<span class="time">${time !== '00:00' ? time : this.tr('all_day', 'All day')}</span>
						</div>
						<div class="details">
							<div class="summary-row" style="display: flex; justify-content: space-between; align-items: flex-start;">
								<span class="summary" style="flex: 1;">
									${!e.is_local ? `<span class="local-indicator">Google</span> ` : ''}
									<input type="text" class="event-title-edit" 
										value="${this.esc(e.summary)}" 
										data-id="${e.id}"
										${!e.is_local || e.is_birthday ? 'disabled' : ''}
										aria-label="${!e.is_local || e.is_birthday ? this.tr('aria_event_name', 'Event') + ': ' : this.tr('aria_edit_event', 'Edit event title') + ': '}${this.esc(e.summary)}"
										style="background: transparent; border: none; font-size: 0.9rem; font-weight: 500; color: var(--text-primary, hsla(0, 0%, 100%, 1)); width: 100%; outline: none;">
								</span>
								${e.is_local && !e.is_birthday ? `<button class="delete-btn btn-sm" data-id="${e.id}" title="${this.tr('delete', 'Delete')}" aria-label="${this.tr('delete', 'Delete')}">✕</button>` : ''}
							</div>
							${e.person ? `<span class="person-badge">${this.esc(e.person)}</span>` : ''}
						</div>
					</div>
				`;
			}).join('') || `<div class="empty-state">${this.tr('no_events', 'No upcoming events.')}</div>`;
		}

		// Refresh filter buttons
		if (filters) {
			const people = [...new Set(this.events.filter(e => e.person).map(e => e.person))];
			filters.innerHTML = `
				<button class="filter-btn ${!this.filterPerson ? 'active' : ''}" data-person="" aria-pressed="${!this.filterPerson ? 'true' : 'false'}">${this.tr('filter_all', 'All')}</button>
				${people.map(p => `
					<button class="filter-btn ${this.filterPerson === p ? 'active' : ''}" data-person="${this.esc(p)}" aria-pressed="${this.filterPerson === p ? 'true' : 'false'}">${this.esc(p)}</button>
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
				input.addEventListener('keydown', (e: Event) => {
					const ke = e as KeyboardEvent;
					if (ke.key === 'Enter') {
						const target = e.target as HTMLInputElement;
						target.blur();
					}
				});
			});
		}
	}

	render() {
		if (this.shadowRoot) {
			this.shadowRoot.innerHTML = `
				<style>
					${BUTTON_STYLES}
					${ACCESSIBILITY_STYLES}
					${SECTION_HEADER_STYLES}
					${EMPTY_STATE_STYLES}
					/* Override icon gradient */
					h2 .h-icon {
						background: linear-gradient(135deg, hsla(216, 100%, 50%, 1) 0%, var(--accent-color, hsla(173, 80%, 40%, 1)) 100%);
					}
					:host { display: block; }
					.card { height: 100%; display: flex; flex-direction: column; }
					.header-container { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
					.calendar-link {
						color: var(--on-accent-text, hsla(228, 45%, 8%, 1));
						background: var(--accent-color, hsla(173, 80%, 40%, 1));
						transition: filter 0.2s, transform 0.1s;
						display: flex;
						align-items: center;
						justify-content: center;
						padding: 0.5rem 1rem;
						border-radius: var(--radius-sm, 0.35rem);
						text-decoration: none;
						font-weight: 600;
						font-size: 0.85rem;
						letter-spacing: 0.02em;
						gap: 0.5rem;
					}
					.calendar-link:hover { 
						filter: brightness(1.2);
					}
					#filters { display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; }
					.filter-btn {
						background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
						border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
						color: var(--text-muted, hsla(0, 0%, 100%, 0.7));
						padding: 0.25rem 0.75rem;
						border-radius: var(--radius-pill, 9999px);
						font-size: 0.75rem;
						cursor: pointer;
						transition: all 0.2s;
					}
					.filter-btn.active {
						background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
						border-color: var(--accent-color, hsla(173, 80%, 40%, 1));
						color: var(--accent-color, hsla(173, 80%, 40%, 1));
					}
					#event-list { overflow-y: auto; flex: 1; }
					.event-item {
						display: flex;
						gap: 1rem;
						padding: 0.75rem;
						background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
						border-radius: var(--radius-lg, 0.75rem);
						margin-bottom: 0.5rem;
						border: 1px solid transparent;
					}
					.time-box {
						display: flex;
						flex-direction: column;
						min-width: 70px;
						font-size: 0.75rem;
					}
					.day { color: var(--accent-color, hsla(173, 80%, 40%, 1)); font-weight: 700; }
					.time { color: var(--text-muted, hsla(0, 0%, 100%, 0.7)); }
					.details { display: flex; flex-direction: column; gap: 0.25rem; flex: 1; }
					.summary { font-size: 0.9rem; color: var(--text-primary, hsla(0, 0%, 100%, 1)); font-weight: 500; }
					.person-badge {
						align-self: flex-start;
						font-size: 0.7rem;
						color: var(--accent-color, hsla(173, 80%, 40%, 1));
						background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.1);
						border: 1px solid rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
						padding: 0.15rem 0.5rem;
						border-radius: var(--radius-sm, 0.35rem);
						text-transform: uppercase;
						letter-spacing: 0.05em;
					}
					.local-indicator {
						font-size: 0.65rem;
						color: var(--accent-secondary, hsla(216, 100%, 50%, 1));
						background: rgba(var(--accent-secondary-rgb, 0, 102, 255), 0.1);
						border: 1px solid rgba(var(--accent-secondary-rgb, 0, 102, 255), 0.2);
						padding: 0.1rem 0.4rem;
						border-radius: var(--radius-xs, 0.25rem);
						margin-right: 0.3rem;
						vertical-align: middle;
					}
					@keyframes theme-pulse-border {
						0% { border-color: var(--accent-color, hsla(173, 80%, 40%, 1)); }
						50% { border-color: var(--accent-secondary, hsla(216, 100%, 50%, 1)); }
						100% { border-color: var(--accent-color, hsla(173, 80%, 40%, 1)); }
					}
					.birthday-item {
						border-width: 1px !important;
						border-style: solid !important;
						border-color: var(--accent-color, hsla(173, 80%, 40%, 1));
						animation: theme-pulse-border 4s ease-in-out infinite;
						background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.05)) !important;
					}
					.birthday-item .day { color: var(--accent-color, hsla(173, 80%, 40%, 1)) !important; }
					.birthday-item .summary { color: var(--accent-secondary, hsla(216, 100%, 50%, 1)) !important; }
					.empty-state { font-size: 0.85rem; color: var(--text-secondary, hsla(0, 0%, 100%, 0.7)); text-align: center; padding: 2rem; }
					.filter-btn:focus-visible, .calendar-link:focus-visible { 
						outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1)); 
						outline-offset: 2px; 
					}
					.event-title-edit:focus-visible { outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1)); outline-offset: 1px; border-radius: 2px; }
					.delete-btn:focus-visible { outline: 2px solid var(--color-danger, hsla(0, 91%, 71%, 1)); outline-offset: 2px; }
					.delete-btn { min-width: 44px; min-height: 44px; display: inline-flex; align-items: center; justify-content: center; }
					@media (forced-colors: active) {
						.h-icon { background: ButtonFace; border: 1px solid ButtonText; }
						.filter-btn.active { border-color: Highlight; }
						.person-badge, .location-badge { border: 1px solid ButtonText; }
						.birthday-item { border-color: LinkText; animation: none; }
					}
				</style>
				<div class="card">
					<div class="header-container">
						<h2>
					<span class="h-icon" aria-hidden="true">
						<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
							<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
							<line x1="16" y1="2" x2="16" y2="6"></line>
							<line x1="8" y1="2" x2="8" y2="6"></line>
							<line x1="3" y1="10" x2="21" y2="10"></line>
						</svg>
					</span>
					${this.tr('calendar_agenda', 'Calendar')}
				</h2>
					<a href="https://calendar.google.com" target="_blank" class="calendar-link" title="${this.tr('aria_open_google_calendar', 'Open Google Calendar (opens in new tab)')}" aria-label="${this.tr('open_calendar', 'Open Calendar')}: Google Calendar (opens in new tab)" rel="noopener noreferrer">
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
								<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
								<line x1="16" y1="2" x2="16" y2="6"></line>
								<line x1="8" y1="2" x2="8" y2="6"></line>
								<line x1="3" y1="10" x2="21" y2="10"></line>
								<polyline points="8 14 12 18 16 14"></polyline>
							</svg>
							${this.tr('open_calendar', 'Open Calendar')}
						</a>
					</div>
					<div id="filters"></div>
					<div id="event-list" aria-live="polite">${this.tr('loading_events', 'Loading events...')}</div>
				</div>
			`;
		}
	}
}

customElements.define('calendar-agenda', CalendarAgenda);
