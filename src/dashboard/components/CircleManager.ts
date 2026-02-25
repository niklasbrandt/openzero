export class CircleManager extends HTMLElement {
	private circleType: string = 'inner';
	private editingId: number | null = null;
	private isAdding: boolean = false;

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
			this.isAdding = false;
			this.editingId = null;
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
			this.isAdding = false;
			this.render();
			this.fetchPeople();
		} catch (e) {
			console.error('Failed to add person', e);
		}
	}

	async deletePerson(id: number) {
		if (!confirm('Are you sure you want to remove this person from your circle?')) return;
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
						${p.birthday ? `<span class="cal-badge">🎂 ${p.birthday}</span>` : ''}
						<p class="ctx">${p.context || 'No specific focus set.'}</p>
					</div>
					<div class="item-actions" role="group" aria-label="Actions for ${p.name}">
						<button class="edit-btn" data-id="${p.id}" aria-label="Edit details for ${p.name}">Edit</button>
						<button class="delete-btn" data-id="${p.id}" aria-label="Remove ${p.name} from circle">Remove</button>
					</div>
				</div>
			`).join('') || `No people added to this circle.`;

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
			const title = this.circleType === 'inner' ? 'Inner Circle (Family & Care)' : 'Close Circle (Friends & Social)';
			const accent = this.circleType === 'inner' ? '#3b82f6' : '#10b981';

			this.shadowRoot.innerHTML = `
				<style>
					h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1rem 0; color: #fff; letter-spacing: 0.02em; }
					:host { display: block; }
					.add-form { 
						display: grid; 
						gap: 0.5rem; 
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
					.edit-btn {
						background: rgba(255, 255, 255, 0.05);
						color: rgba(255, 255, 255, 0.6);
						border: 1px solid rgba(255, 255, 255, 0.1);
						padding: 0.4rem 0.8rem;
						border-radius: 0.6rem;
						cursor: pointer;
						font-size: 0.8rem;
						margin-right: 0.5rem;
					}
					.edit-btn:hover { background: rgba(255, 255, 255, 0.1); color: #fff; }
					.item-actions { display: flex; align-items: center; }
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
					button:focus-visible, input:focus-visible, textarea:focus-visible { 
						outline: 2px solid #14B8A6; 
						outline-offset: 2px; 
					}
				</style>
				<div class="card">
					<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
						<h2>${title}</h2>
						${!this.isAdding ? `<button id="showAddBtn" style="background: ${accent}; color: #fff; border: none; padding: 0.4rem 1rem; border-radius: 0.6rem; cursor: pointer; font-size: 0.8rem; font-weight: 600;">+ New Person</button>` : ''}
					</div>
					
					${this.isAdding ? `
					<div class="add-form">
						<input type="text" id="nameInput" placeholder="Name">
						<input type="text" id="relInput" placeholder="Relationship (e.g. Son, Friend)">
						<input type="text" id="bdayInput" placeholder="Birthday (e.g. 27.02.19)">
						<textarea id="ctxInput" placeholder="Focus..."></textarea>
						<div style="display: flex; gap: 0.5rem;">
							<button id="addBtn">${this.editingId ? 'Update Person' : 'Add to Circle'}</button>
							<button id="cancelEditBtn" style="background:transparent; border:1px solid rgba(255,255,255,0.2); color:#fff; border-radius:0.6rem; padding:0.4rem 1rem; cursor:pointer; font-size:0.8rem;">Cancel</button>
						</div>
					</div>
					` : ''}
					<div id="people-list">Loading...</div>
				</div>
			`;

			if (!this.isAdding) {
				this.shadowRoot.querySelector('#showAddBtn')?.addEventListener('click', () => {
					this.isAdding = true;
					this.render();
				});
			}

			this.displayPeople(this.currentPeople);

			this.shadowRoot.querySelector('#addBtn')?.addEventListener('click', () => {
				const name = (this.shadowRoot?.querySelector('#nameInput') as HTMLInputElement).value;
				const rel = (this.shadowRoot?.querySelector('#relInput') as HTMLInputElement).value;
				const ctx = (this.shadowRoot?.querySelector('#ctxInput') as HTMLTextAreaElement).value;
				const bday = (this.shadowRoot?.querySelector('#bdayInput') as HTMLInputElement).value;

				if (name && rel) {
					if (this.editingId) {
						this.updatePerson(this.editingId, name, rel, ctx, bday);
					} else {
						this.addPerson(name, rel, ctx, bday);
					}

					(this.shadowRoot?.querySelector('#nameInput') as HTMLInputElement).value = '';
					(this.shadowRoot?.querySelector('#relInput') as HTMLInputElement).value = '';
					(this.shadowRoot?.querySelector('#ctxInput') as HTMLTextAreaElement).value = '';
					(this.shadowRoot?.querySelector('#bdayInput') as HTMLInputElement).value = '';
				}
			});

			this.shadowRoot.querySelector('#cancelEditBtn')?.addEventListener('click', () => {
				this.editingId = null;
				this.isAdding = false;
				this.render();
			});

			// Accessibility: Submit on Enter
			this.shadowRoot.querySelectorAll('input, textarea').forEach(el => {
				el.addEventListener('keydown', (e: any) => {
					if (e.key === 'Enter' && !e.shiftKey) {
						e.preventDefault();
						this.shadowRoot?.querySelector<HTMLButtonElement>('#addBtn')?.click();
					}
				});
			});
		}
	}
}

customElements.define('circle-manager', CircleManager);
