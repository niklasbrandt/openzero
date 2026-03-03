export class UserCard extends HTMLElement {
	private me: any = null;
	private isEditing: boolean = false;
	private t: Record<string, string> = {};
	private languageNames: Record<string, string> = {
		en: 'English', zh: 'Mandarin Chinese', hi: 'Hindi',
		es: 'Spanish', fr: 'French', ar: 'Arabic',
		pt: 'Portuguese', ru: 'Russian', ja: 'Japanese', de: 'German',
		it: 'Italian', nl: 'Dutch', pl: 'Polish', sv: 'Swedish',
		el: 'Greek', ro: 'Romanian', tr: 'Turkish', cs: 'Czech',
		da: 'Danish', no: 'Norwegian',
	};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.loadTranslations().then(() => this.fetchIdentity());
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => this.render());
		});
	}

	private async loadTranslations() {
		try {
			const res = await fetch('/api/dashboard/translations');
			if (res.ok) this.t = await res.json();
		} catch (_) {}
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] || fallback;
	}

	async fetchIdentity() {
		try {
			const response = await fetch('/api/dashboard/people?circle_type=identity');
			if (!response.ok) throw new Error('API error');
			const data = await response.json();
			// Ensure default structure if empty
			this.me = data[0] || {
				name: 'User',
				birthday: '',
				gender: '',
				residency: '',
				town: '',
				country: '',
				timezone: '',
				work_times: '',
				briefing_time: '08:00',
				context: ''
			};
			this.render();
		} catch (e) {
			console.error('Failed to fetch identity:', e);
			this.render();
		}
	}

	async saveIdentity() {
		const shadow = this.shadowRoot!;
		const payload = {
			name: (shadow.querySelector('#name-input') as HTMLInputElement).value,
			birthday: (shadow.querySelector('#bday-input') as HTMLInputElement).value,
			gender: (shadow.querySelector('#gender-input') as HTMLInputElement).value,
			residency: (shadow.querySelector('#residency-input') as HTMLInputElement).value,
			town: (shadow.querySelector('#town-input') as HTMLInputElement).value,
			country: (shadow.querySelector('#country-input') as HTMLInputElement).value,
			timezone: (shadow.querySelector('#timezone-input') as HTMLInputElement).value,
			work_times: (shadow.querySelector('#work-input') as HTMLInputElement).value,
			briefing_time: (shadow.querySelector('#brief-input') as HTMLInputElement).value,
			context: (shadow.querySelector('#context-input') as HTMLTextAreaElement).value,
			language: (shadow.querySelector('#language-input') as HTMLSelectElement).value,
			circle_type: 'identity',
			relationship: 'Self'
		};

		try {
			const response = await fetch('/api/dashboard/people/identity', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(payload)
			});
			if (response.ok) {
				this.me = await response.json();
				this.isEditing = false;
				this.render();
				window.dispatchEvent(new CustomEvent('identity-updated'));
				window.dispatchEvent(new CustomEvent('refresh-data'));
			}
		} catch (e) {
			alert('Save failed');
		}
	}

	render() {
		if (!this.shadowRoot) return;

		const me = this.me || {};

		this.shadowRoot.innerHTML = `
			<style>
				:host { display: block; height: 100%; }
				.card {
					background: rgba(10, 15, 30, 0.4);
					border: 1px solid rgba(20, 184, 166, 0.15);
					padding: 1.5rem;
					height: 100%;
					display: flex;
					flex-direction: column;
					gap: 1.25rem;
					color: #fff;
					font-family: 'Inter', sans-serif;
					overflow-y: auto;
				}

				.header { display: flex; justify-content: space-between; align-items: center; }
				.user-info { display: flex; align-items: center; gap: 1rem; }
				.avatar {
					width: 48px; height: 48px;
					background: #14B8A6;
					display: flex; align-items: center; justify-content: center;
					font-weight: 800; font-size: 1.25rem;
					box-shadow: 0 0 20px rgba(20, 184, 166, 0.3);
				}
				h2 { margin: 0; font-size: 1.1rem; }

				.edit-btn {
					background: rgba(255,255,255,0.05);
					border: 1px solid rgba(255,255,255,0.1);
					color: #14B8A6;
					padding: 6px 12px;
					font-size: 0.7rem;
					cursor: pointer;
					text-transform: uppercase;
				}

				.grid {
					display: grid;
					grid-template-columns: 1fr 1fr;
					gap: 1rem;
				}

				.field { display: flex; flex-direction: column; gap: 4px; }
				.label { font-size: 0.65rem; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.05em; }
				.value { font-size: 0.9rem; color: #fff; font-weight: 500; }

				input, textarea, select {
					background: rgba(0,0,0,0.3);
					border: 1px solid rgba(255,255,255,0.1);
					color: #fff;
					padding: 8px;
					font-size: 0.85rem;
					width: 100%;
					box-sizing: border-box;
				}

				select {
					cursor: pointer;
					appearance: none;
					background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2314B8A6' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
					background-repeat: no-repeat;
					background-position: right 8px center;
					padding-right: 28px;
				}

				select option {
					background: #1a1a2e;
					color: #fff;
				}

				.goals-section h3 { 
					font-size: 0.7rem; 
					color: #14B8A6; 
					text-transform: uppercase; 
					margin: 1rem 0 0.5rem 0;
					display: flex;
					align-items: center;
					gap: 8px;
				}
				.goals-section h3::after {
					content: ''; flex: 1; height: 1px; background: rgba(20, 184, 166, 0.2);
				}

				ul { list-style: none; padding: 0; margin: 0; }
				li { font-size: 0.85rem; color: rgba(255,255,255,0.7); margin-bottom: 0.5rem; position: relative; padding-left: 1.2rem; }
				li::before { content: '◈'; position: absolute; left: 0; color: #14B8A6; font-size: 0.7rem; top: 2px; }


				.actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 1rem; }
				.save-btn { background: #14B8A6; border: none; color: #000; font-weight: 700; padding: 8px 16px; cursor: pointer; }
				.cancel-btn { background: transparent; border: 1px solid rgba(255,255,255,0.2); color: #fff; padding: 8px 16px; cursor: pointer; }
				button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible { 
					outline: 2px solid #14B8A6; 
					outline-offset: 2px; 
				}
			</style>

			<div class="card">
				<div class="header">
					<div class="user-info">
						<div class="avatar">${(me.name || 'U')[0]}</div>
						${this.isEditing
				? `<input id="name-input" type="text" placeholder="Full Name" value="${me.name || ''}">`
				: `<h2>${me.name || 'User'}</h2>`}
					</div>
					${!this.isEditing ? `<button class="edit-btn" id="edit-trigger" aria-label="Edit personal profile">${this.tr('edit', 'Edit')}</button>` : ''}
				</div>

				<div class="grid">
					<div class="field">
						<div class="label">${this.tr('birthday', 'Birthday')}</div>
						${this.isEditing
				? `<input id="bday-input" type="text" placeholder="YYYY-MM-DD" value="${me.birthday || ''}">`
				: `<div class="value">${me.birthday || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						<div class="label">${this.tr('gender', 'Gender')}</div>
						${this.isEditing
				? `<input id="gender-input" type="text" placeholder="e.g. Non-binary" value="${me.gender || ''}">`
				: `<div class="value">${me.gender || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						<div class="label">${this.tr('residency', 'Residency')}</div>
						${this.isEditing
				? `<input id="residency-input" type="text" placeholder="City, Country" value="${me.residency || ''}">`
				: `<div class="value">${me.residency || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						<div class="label">${this.tr('town', 'Town')}</div>
						${this.isEditing
				? `<input id="town-input" type="text" placeholder="Berlin" value="${me.town || ''}">`
				: `<div class="value">${me.town || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						<div class="label">${this.tr('country', 'Country')}</div>
						${this.isEditing
				? `<input id="country-input" type="text" placeholder="Germany" value="${me.country || ''}">`
				: `<div class="value">${me.country || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						<div class="label">${this.tr('timezone_label', 'Timezone')}</div>
						${this.isEditing
				? `<input id="timezone-input" type="text" placeholder="Europe/Berlin" value="${me.timezone || ''}">`
				: `<div class="value">${me.timezone || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						<div class="label">${this.tr('briefing_time', 'Briefing Time')}</div>
						${this.isEditing
				? `<input id="brief-input" type="text" placeholder="08:00" value="${me.briefing_time || ''}">`
				: `<div class="value">${me.briefing_time || '08:00'}</div>`}
					</div>
					<div class="field">
						<div class="label">${this.tr('language_label', 'Language')}</div>
						${this.isEditing
				? `<select id="language-input" aria-label="Select Z's response language">${Object.entries(this.languageNames).map(([code, name]) => `<option value="${code}" ${(me.language || 'en') === code ? 'selected' : ''}>${name}</option>`).join('')}</select>`
				: `<div class="value">${this.languageNames[me.language as string] || 'English'}</div>`}
					</div>
					<div class="field" style="grid-column: span 2;">
						<div class="label">${this.tr('work_times', 'Typical Work Times')}</div>
						${this.isEditing
				? `<input id="work-input" type="text" placeholder="e.g. 09:00 - 18:00" value="${me.work_times || ''}">`
				: `<div class="value">${me.work_times || this.tr('not_set', 'Not set')}</div>`}
					</div>
				</div>

				<div class="goals-section">
					<h3>${this.tr('life_goals', 'Life Goals & Core Values')}</h3>
					${this.isEditing
				? `<textarea id="context-input" placeholder="What drives you? What are your current focus areas?">${me.context || ''}</textarea>`
				: `<ul>${(me.context || '').split('\n').filter((l: string) => l.trim() && !l.trim().startsWith('<!--') && !l.includes('## Growth Areas')).map((l: string) => `<li>${l.replace(/^#+\s*/, '')}</li>`).join('') || `<li>${this.tr('no_goals', 'No goals set.')}</li>`}</ul>`}
				</div>

				${this.isEditing ? `
					<div class="actions">
						<button class="cancel-btn" id="cancel-trigger">${this.tr('discard', 'Discard')}</button>
						<button class="save-btn" id="save-trigger">${this.tr('save_profile', 'Save Profile')}</button>
					</div>
				` : ''}
			</div>
		`;

		this.shadowRoot.querySelector('#edit-trigger')?.addEventListener('click', () => {
			this.isEditing = true;
			this.render();
		});
		this.shadowRoot.querySelector('#cancel-trigger')?.addEventListener('click', () => {
			this.isEditing = false;
			this.render();
		});
		this.shadowRoot.querySelector('#save-trigger')?.addEventListener('click', () => this.saveIdentity());

		// Accessibility: Submit on Enter
		this.shadowRoot.querySelectorAll('input, textarea').forEach(el => {
			el.addEventListener('keydown', (e: any) => {
				if (e.key === 'Enter' && !e.shiftKey) {
					e.preventDefault();
					this.saveIdentity();
				}
			});
		});
	}
}
customElements.define('user-card', UserCard);
