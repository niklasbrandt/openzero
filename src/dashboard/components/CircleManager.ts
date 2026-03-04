import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { FEEDBACK_STYLES } from '../services/feedbackStyles';

export class CircleManager extends HTMLElement {
	private circleType: string = 'inner';
	private editingId: number | null = null;
	private isAdding: boolean = false;
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

	static get observedAttributes() {
		return ['type'];
	}

	attributeChangedCallback(name: string, _oldValue: string, newValue: string) {
		if (name === 'type') {
			this.circleType = newValue;
			this.isAdding = false;
			this.editingId = null;
			this.render();
			this.fetchPeople();
		}
	}

	connectedCallback() {
		this.circleType = this.getAttribute('type') || 'inner';
		this.loadTranslations().then(() => { this.render(); this.fetchPeople(); });
		window.addEventListener('refresh-data', (e: any) => {
			if (e.detail && e.detail.actions && e.detail.actions.includes('people')) {
				this.fetchPeople();
			}
		});
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => this.render());
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
			if (list) list.textContent = this.tr('no_people', 'No people added to this circle.');
		}
	}

	async addPerson(name: string, relationship: string, context: string, birthday: string = '') {
		try {
			await fetch('/api/dashboard/people', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name, relationship, context, circle_type: this.circleType, birthday })
			});
			this.isAdding = false;
			this.render();
			this.fetchPeople();
		} catch (e) {
			console.error('Failed to add person', e);
		}
	}

	async deletePerson(id: number) {
		if (!confirm(this.tr('confirm_remove', 'Are you sure you want to remove this person from your circle?'))) return;
		try {
			await fetch(`/api/dashboard/people/${id}`, { method: 'DELETE' });
			this.fetchPeople();
		} catch (e) {
			console.error('Failed to delete person', e);
		}
	}

	async updatePerson(id: number, name: string, relationship: string, context: string, birthday: string) {
		try {
			await fetch(`/api/dashboard/people/${id}`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name, relationship, context, circle_type: this.circleType, birthday })
			});
			this.editingId = null;
			this.isAdding = false;
			this.render();
			this.fetchPeople();
		} catch (e) {
			console.error('Failed to update person', e);
			alert('Update failed');
		}
	}

	private currentPeople: any[] = [];

	displayPeople(people: any[]) {
		this.currentPeople = people;
		const list = this.shadowRoot?.querySelector('#people-list');
		if (list) {
			list.innerHTML = people.map(p => `
				<div class="person-item">
					<div class="info">
						<span class="name">${p.name}</span>
						<span class="rel">${p.relationship}</span>
						${p.birthday ? `<span class="cal-badge" aria-label="${this.tr('aria_birthday_badge', 'Birthday')}: ${p.birthday}"><span aria-hidden="true">&#127874;</span> ${p.birthday}</span>` : ''}
						<p class="ctx">${p.context || this.tr('no_focus', 'No specific focus set.')}</p>
					</div>
					<div class="item-actions" role="group" aria-label="${this.tr('aria_actions_for', 'Actions for')} ${p.name}">
						<button class="edit-btn" data-id="${p.id}" aria-label="${this.tr('aria_edit_details', 'Edit details for')} ${p.name}">${this.tr('edit', 'Edit')}</button>
						<button class="delete-btn" data-id="${p.id}" aria-label="${this.tr('aria_remove_from_circle', 'Remove from circle')}: ${p.name}">${this.tr('remove', 'Remove')}</button>
					</div>
				</div>
			`).join('') || this.tr('no_people', 'No people added to this circle.');

			list.querySelectorAll('.delete-btn').forEach(btn => {
				btn.addEventListener('click', (e) => {
					const id = (e.currentTarget as HTMLElement).getAttribute('data-id');
					if (id) this.deletePerson(parseInt(id));
				});
			});

			list.querySelectorAll('.edit-btn').forEach(btn => {
				btn.addEventListener('click', (e) => {
					const id = (e.currentTarget as HTMLElement).getAttribute('data-id');
					const person = people.find(p => p.id === parseInt(id!));
					if (person) {
						this.editingId = person.id;
						this.isAdding = true;
						this.render();
						// Populate fields
						(this.shadowRoot?.querySelector('#nameInput') as HTMLInputElement).value = person.name;
						(this.shadowRoot?.querySelector('#relInput') as HTMLInputElement).value = person.relationship;
						(this.shadowRoot?.querySelector('#bdayInput') as HTMLInputElement).value = person.birthday || '';
						(this.shadowRoot?.querySelector('#ctxInput') as HTMLTextAreaElement).value = person.context || '';
					}
				});
			});
		}
	}

	render() {
		if (this.shadowRoot) {
			const titles: Record<string, string> = {
				inner: this.tr('inner_circle_full', 'Inner Circle'),
				close: this.tr('close_circle_full', 'Close Circle'),
				outer: this.tr('outer_circle_full', 'Outer Circle'),
			};
			const accents: Record<string, string> = {
				inner: 'hsla(217, 91%, 60%, 1)',
				close: '#10b981',
				outer: '#a78bfa',
			};
			const title = titles[this.circleType] || titles['outer'];
			const accent = accents[this.circleType] || accents['outer'];

			this.shadowRoot.innerHTML = `
				<style>
					${BUTTON_STYLES}
					${ACCESSIBILITY_STYLES}
					${FEEDBACK_STYLES}
					h2 { font-size: 1.5rem; font-weight: bold; margin: 0; color: #fff; letter-spacing: 0.02em; display: flex; align-items: center; gap: 0.5rem; overflow-wrap: break-word; word-break: break-word; min-width: 0; flex: 1; }
					.h-icon { display: inline-flex; width: 32px; height: 32px; background: ${accent}; border-radius: var(--radius-sm, 0.4rem); align-items: center; justify-content: center; flex-shrink: 0; }
					.subtitle { font-size: 0.65rem; font-weight: 400; color: var(--text-faint, rgba(255, 255, 255, 0.3)); margin-left: 0.5rem; text-transform: uppercase; letter-spacing: 0.1em; }
					:host { display: block; }
					.add-form {
						display: grid;
						gap: 0.25rem;
						margin-bottom: 1.5rem;
						animation: fadeIn 0.3s ease-in-out;
						background: rgba(255, 255, 255, 0.02);
						padding: 1rem;
						border-radius: 1rem;
					}
					@keyframes fadeIn {
						from { opacity: 0; transform: translateY(-10px); }
						to { opacity: 1; transform: translateY(0); }
					}
					label {
						display: block;
						font-size: 0.7rem;
						font-weight: 600;
						color: rgba(255, 255, 255, 0.4);
						text-transform: uppercase;
						letter-spacing: 0.06em;
						margin-bottom: 0.2rem;
						margin-top: 0.5rem;
					}
					label .required { color: var(--color-danger, hsla(0, 91%, 71%, 1)); margin-left: 0.15rem; }
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
						width: 100%;
						box-sizing: border-box;
					}
					input:focus, textarea:focus {
						border-color: rgba(var(--accent-color-rgb, 20, 184, 166), 0.4);
						background: rgba(0, 0, 0, 0.28);
					}
					input.field-error, textarea.field-error {
						border-color: rgba(var(--color-danger-rgb, 239, 68, 68), 0.5);
						background: rgba(var(--color-danger-rgb, 239, 68, 68), 0.05);
					}
					.field-hint {
						font-size: 0.68rem;
						color: rgba(255, 255, 255, 0.2);
						margin-top: 0.15rem;
					}
					.field-error-msg {
						font-size: 0.72rem;
						color: var(--color-danger, hsla(0, 91%, 71%, 1));
						margin-top: 0.15rem;
						min-height: 0;
						opacity: 0;
						transition: opacity 0.2s ease;
					}
					.field-error-msg.visible { opacity: 1; }
					.person-item {
						background: rgba(255, 255, 255, 0.03);
						border-radius: 1rem;
						padding: 1rem;
						margin-bottom: 1rem;
						display: flex;
						justify-content: space-between;
						align-items: flex-start;
					gap: 0.75rem;
				}
				.info {
					flex: 1;
					min-width: 0;
					word-break: break-word;
					overflow-wrap: break-word;
				}
				.name { font-weight: 700; color: #fff; display: block; overflow-wrap: break-word; }
				.rel { font-size: 0.8rem; color: ${accent}; display: block; overflow-wrap: break-word; }
				.ctx { font-size: 0.85rem; color: rgba(255, 255, 255, 0.6); margin: 0.5rem 0 0 0; overflow-wrap: break-word; }
				.edit-btn { margin-right: 0; }
				.edit-btn:hover { background: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.2); }
				.item-actions {
					display: flex;
					flex-direction: column;
					gap: 0.4rem;
					flex-shrink: 0;
					align-items: stretch;
					min-width: 72px;
				}
					.cal-badge {
						display: inline-block;
						font-size: 0.7rem;
						color: var(--accent-color, hsla(173, 80%, 40%, 1));
						background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.1);
						border: 1px solid rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
						padding: 0.15rem 0.5rem;
						border-radius: var(--radius-sm, 0.4rem);
						margin-left: 0.5rem;
					}


					.form-feedback {
						font-size: 0.78rem;
						padding: 0.5rem 0.75rem;
						border-radius: var(--radius-md, 0.5rem);
						margin-top: 0.5rem;
						opacity: 0;
						transition: opacity var(--duration-base, 0.25s) ease;
					}
					.form-feedback.visible { opacity: 1; }
					.form-feedback.error {
						background: rgba(var(--color-danger-rgb, 239, 68, 68), 0.1);
						border: 1px solid rgba(var(--color-danger-rgb, 239, 68, 68), 0.2);
						color: var(--color-danger, hsla(0, 91%, 71%, 1));
					}
					.form-feedback.success {
						background: rgba(var(--color-success-rgb, 34, 197, 94), 0.1);
						border: 1px solid rgba(var(--color-success-rgb, 34, 197, 94), 0.2);
						color: var(--color-success, hsla(142, 69%, 58%, 1));
					}
					button:focus-visible, input:focus-visible, textarea:focus-visible {
						outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1));
						outline-offset: 2px;
					}
				</style>
				<div class="card">
					<div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem;">
						<h2>
					<span class="h-icon" aria-hidden="true">
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
									<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
									<circle cx="9" cy="7" r="4"></circle>
									<path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
									<path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
								</svg>
							</span>
							${title}
						</h2>
						${!this.isAdding ? `<button id="showAddBtn" class="btn-primary" aria-label="Add a new person to ${title}">${this.tr('new_person', '+ New Person')}</button>` : ''}
					</div>

					${this.isAdding ? `
					<form class="add-form" id="personForm" novalidate>
						<label for="nameInput">${this.tr('name_label', 'Name')} <span class="required" aria-hidden="true">*</span></label>
						<input type="text" id="nameInput" placeholder="${this.tr('name_placeholder', 'e.g. Maria')}" required aria-required="true" autocomplete="off" aria-describedby="nameError">
						<div class="field-error-msg" id="nameError" role="alert"></div>

						<label for="relInput">${this.tr('relationship_label', 'Relationship')} <span class="required" aria-hidden="true">*</span></label>
						<input type="text" id="relInput" placeholder="${this.tr('rel_placeholder', 'e.g. Son, Friend, Colleague')}" required aria-required="true" autocomplete="off" aria-describedby="relError">
						<div class="field-error-msg" id="relError" role="alert"></div>

						<label for="bdayInput">${this.tr('birthday_label', 'Birthday')}</label>
						<input type="text" id="bdayInput" placeholder="${this.tr('bday_placeholder', 'e.g. 27.02.2019')}" autocomplete="off">
						<div class="field-hint">${this.tr('birthday_hint', 'DD.MM.YYYY or DD.MM.YY — optional')}</div>

						<label for="ctxInput">${this.tr('context_label', 'Context / Focus')}</label>
						<textarea id="ctxInput" rows="2" placeholder="${this.tr('notes_placeholder', 'Notes, hobbies, important details...')}"></textarea>

						<div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
<button type="submit" id="addBtn" class="btn-primary">${this.editingId ? this.tr('update_person', 'Update Person') : this.tr('add_to_circle', 'Add to Circle')}</button>
						<button type="button" id="cancelEditBtn" class="cancel-btn">${this.tr('cancel', 'Cancel')}</button>
						</div>
						<div class="form-feedback" id="formFeedback" role="status" aria-live="polite"></div>
					</form>
					` : ''}
					<div id="people-list">${this.tr('loading', 'Loading...')}</div>
				</div>
			`;

			if (!this.isAdding) {
				this.shadowRoot.querySelector('#showAddBtn')?.addEventListener('click', () => {
					this.isAdding = true;
					this.render();
					// Focus the first field for keyboard users
					setTimeout(() => {
						this.shadowRoot?.querySelector<HTMLInputElement>('#nameInput')?.focus();
					}, 50);
				});
			}

			this.displayPeople(this.currentPeople);

			// Form submission with validation
			const form = this.shadowRoot.querySelector('#personForm');
			form?.addEventListener('submit', (e) => {
				e.preventDefault();
				this.validateAndSubmit();
			});

			// Clear error styling on input
			this.shadowRoot.querySelectorAll('input, textarea').forEach(el => {
				el.addEventListener('input', () => {
					el.classList.remove('field-error');
					const errorEl = el.id === 'nameInput'
						? this.shadowRoot?.querySelector('#nameError')
						: el.id === 'relInput'
							? this.shadowRoot?.querySelector('#relError')
							: null;
					if (errorEl) {
						errorEl.textContent = '';
						errorEl.classList.remove('visible');
					}
				});
			});

			this.shadowRoot.querySelector('#cancelEditBtn')?.addEventListener('click', () => {
				this.editingId = null;
				this.isAdding = false;
				this.render();
			});

			// Accessibility: Submit on Enter from inputs (not textarea)
			this.shadowRoot.querySelectorAll('input').forEach(el => {
				el.addEventListener('keydown', (e: any) => {
					if (e.key === 'Enter') {
						e.preventDefault();
						this.validateAndSubmit();
					}
				});
			});
		}
	}

	private validateAndSubmit() {
		const nameEl = this.shadowRoot?.querySelector<HTMLInputElement>('#nameInput');
		const relEl = this.shadowRoot?.querySelector<HTMLInputElement>('#relInput');
		const ctxEl = this.shadowRoot?.querySelector<HTMLTextAreaElement>('#ctxInput');
		const bdayEl = this.shadowRoot?.querySelector<HTMLInputElement>('#bdayInput');
		const nameErr = this.shadowRoot?.querySelector('#nameError');
		const relErr = this.shadowRoot?.querySelector('#relError');

		if (!nameEl || !relEl) return;

		let valid = true;
		const name = nameEl.value.trim();
		const rel = relEl.value.trim();
		const ctx = ctxEl?.value.trim() || '';
		const bday = bdayEl?.value.trim() || '';

		// Reset errors
		nameEl.classList.remove('field-error');
		relEl.classList.remove('field-error');
		if (nameErr) { nameErr.textContent = ''; nameErr.classList.remove('visible'); }
		if (relErr) { relErr.textContent = ''; relErr.classList.remove('visible'); }

		if (!name) {
			nameEl.classList.add('field-error');
			if (nameErr) { nameErr.textContent = this.tr('name_required', 'Name is required.'); nameErr.classList.add('visible'); }
			nameEl.focus();
			valid = false;
		}
		if (!rel) {
			relEl.classList.add('field-error');
			if (relErr) { relErr.textContent = this.tr('rel_required', 'Relationship is required.'); relErr.classList.add('visible'); }
			if (valid) relEl.focus(); // focus first error
			valid = false;
		}

		if (!valid) return;

		if (this.editingId) {
			this.updatePerson(this.editingId, name, rel, ctx, bday);
		} else {
			this.addPerson(name, rel, ctx, bday);
		}
	}
}

customElements.define('circle-manager', CircleManager);
