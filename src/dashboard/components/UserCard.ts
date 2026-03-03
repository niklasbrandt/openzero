export class UserCard extends HTMLElement {
	private me: any = null;
	private isEditing: boolean = false;
	private t: Record<string, string> = {};
	private languageNames: Record<string, string> = {
		en: 'English', zh: 'Mandarin Chinese', hi: 'Hindi',
		es: 'Spanish', fr: 'French', ar: 'Arabic',
		pt: 'Portuguese', ru: 'Russian', ja: 'Japanese', de: 'German',
		it: 'Italian', ko: 'Korean', vi: 'Vietnamese', bn: 'Bengali',
		id: 'Indonesian', nl: 'Dutch', pl: 'Polish', sv: 'Swedish',
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
		} catch (_) { }
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
			color_primary: (shadow.querySelector('#color-primary-input') as HTMLInputElement).value,
			color_secondary: (shadow.querySelector('#color-secondary-input') as HTMLInputElement).value,
			color_tertiary: (shadow.querySelector('#color-tertiary-input') as HTMLInputElement).value,
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
					height: 100%;
					display: flex;
					flex-direction: column;
					gap: 1.25rem;
					color: #fff;
					font-family: 'Inter', sans-serif;
				}

				.header { display: flex; justify-content: space-between; align-items: center; }
				.user-info { display: flex; align-items: center; gap: 1rem; }
				.avatar {
					width: 48px; height: 48px;
					background: linear-gradient(135deg, var(--accent-color), var(--accent-secondary));
					border-radius: 0.4rem;
					display: flex; align-items: center; justify-content: center;
					font-weight: 800; font-size: 1.25rem;
				}
				h2 { margin: 0; font-size: 1.1rem; }

				.edit-btn {
					background: rgba(255,255,255,0.05);
					border: 1px solid rgba(255,255,255,0.1);
					color: var(--accent-color);
					padding: 6px 12px;
					font-size: 0.7rem;
					cursor: pointer;
					text-transform: uppercase;
					letter-spacing: 0.05em;
					border-radius: 0.4rem;
					transition: all 0.2s;
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
					border-radius: 0.5rem;
					color: #fff;
					padding: 8px 12px;
					font-size: 0.85rem;
					width: 100%;
					box-sizing: border-box;
					transition: border-color 0.2s;
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
					color: var(--accent-color); 
					text-transform: uppercase; 
					margin: 1rem 0 0.5rem 0;
					display: flex;
					align-items: center;
					gap: 8px;
				}
				.goals-section h3::after {
					content: ''; flex: 1; height: 1px; background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
				}

				ul { list-style: none; padding: 0; margin: 0; }
				li { font-size: 0.85rem; color: rgba(255,255,255,0.7); margin-bottom: 0.5rem; position: relative; padding-left: 1.2rem; }
				li::before { content: '◈'; position: absolute; left: 0; color: var(--accent-color); font-size: 0.7rem; top: 2px; }


				.actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 1rem; }
				.save-btn { background: var(--accent-color); border: none; color: #000; font-weight: 700; padding: 8px 16px; cursor: pointer; border-radius: 0.4rem; text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.75rem; transition: all 0.2s; }
				.cancel-btn { background: transparent; border: 1px solid rgba(255,255,255,0.2); color: #fff; padding: 8px 16px; cursor: pointer; border-radius: 0.4rem; text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.75rem; transition: all 0.2s; }
				button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible { 
					outline: 2px solid var(--accent-color); 
					outline-offset: 2px; 
				}
				button:focus:not(:focus-visible), input:focus:not(:focus-visible), textarea:focus:not(:focus-visible), select:focus:not(:focus-visible) { outline: none; }
				.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
				@media (prefers-reduced-motion: reduce) {
					*, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
				}
			</style>

			<div class="card">
				<div class="header">
					<div class="user-info">
					<div class="avatar" aria-hidden="true">${(me.name || 'U')[0]}</div>
					${this.isEditing
				? `<div style="display:flex;flex-direction:column;gap:2px;"><label class="label" for="name-input" style="margin:0;">${this.tr('name_label', 'Name')}</label><input id="name-input" type="text" placeholder="Full Name" value="${me.name || ''}" aria-label="Your name" autocomplete="name"></div>`
				: `<h2>${me.name || 'User'}</h2>`}
					</div>
					${!this.isEditing ? `<button class="edit-btn" id="edit-trigger" aria-label="Edit personal profile">${this.tr('edit', 'Edit')}</button>` : ''}
				</div>

				<div class="grid">
					<div class="field">
						${this.isEditing
				? `<label class="label" for="bday-input">${this.tr('birthday', 'Birthday')}</label><input id="bday-input" type="text" placeholder="YYYY-MM-DD" value="${me.birthday || ''}" autocomplete="bday" aria-describedby="bday-hint"><span id="bday-hint" style="font-size:0.6rem;color:rgba(255,255,255,0.25);">Format: YYYY-MM-DD (optional)</span>`
				: `<div class="label" aria-hidden="true">${this.tr('birthday', 'Birthday')}</div><div class="value">${me.birthday || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						${this.isEditing
				? `<label class="label" for="gender-input">${this.tr('gender', 'Gender')}</label><input id="gender-input" type="text" placeholder="e.g. Non-binary" value="${me.gender || ''}" autocomplete="sex">`
				: `<div class="label" aria-hidden="true">${this.tr('gender', 'Gender')}</div><div class="value">${me.gender || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						${this.isEditing
				? `<label class="label" for="residency-input">${this.tr('residency', 'Residency')}</label><input id="residency-input" type="text" placeholder="City, Country" value="${me.residency || ''}">`
				: `<div class="label" aria-hidden="true">${this.tr('residency', 'Residency')}</div><div class="value">${me.residency || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						${this.isEditing
				? `<label class="label" for="town-input">${this.tr('town', 'Town')}</label><input id="town-input" type="text" placeholder="Berlin" value="${me.town || ''}">`
				: `<div class="label" aria-hidden="true">${this.tr('town', 'Town')}</div><div class="value">${me.town || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						${this.isEditing
				? `<label class="label" for="country-input">${this.tr('country', 'Country')}</label><input id="country-input" type="text" placeholder="Germany" value="${me.country || ''}" autocomplete="country-name">`
				: `<div class="label" aria-hidden="true">${this.tr('country', 'Country')}</div><div class="value">${me.country || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						${this.isEditing
				? `<label class="label" for="timezone-input">${this.tr('timezone_label', 'Timezone')}</label><input id="timezone-input" type="text" placeholder="Europe/Berlin" value="${me.timezone || ''}" aria-describedby="tz-hint"><span id="tz-hint" style="font-size:0.6rem;color:rgba(255,255,255,0.25);">IANA timezone identifier</span>`
				: `<div class="label" aria-hidden="true">${this.tr('timezone_label', 'Timezone')}</div><div class="value">${me.timezone || this.tr('not_set', 'Not set')}</div>`}
					</div>
					<div class="field">
						${this.isEditing
				? `<label class="label" for="brief-input">${this.tr('briefing_time', 'Briefing Time')}</label><input id="brief-input" type="text" placeholder="08:00" value="${me.briefing_time || ''}" aria-describedby="brief-hint"><span id="brief-hint" style="font-size:0.6rem;color:rgba(255,255,255,0.25);">24h HH:MM format</span>`
				: `<div class="label" aria-hidden="true">${this.tr('briefing_time', 'Briefing Time')}</div><div class="value">${me.briefing_time || '08:00'}</div>`}
					</div>
					<div class="field">
						${this.isEditing
				? `<label class="label" for="language-input">${this.tr('language_label', 'Language')}</label><select id="language-input" aria-label="Select Z\'s response language">${Object.entries(this.languageNames).map(([code, name]) => `<option value="${code}" ${(me.language || 'en') === code ? 'selected' : ''}>${name}</option>`).join('')}</select>`
				: `<div class="label" aria-hidden="true">${this.tr('language_label', 'Language')}</div><div class="value">${this.languageNames[me.language as string] || 'English'}</div>`}
					</div>
					<div class="field" style="grid-column: span 2;">
						${this.isEditing
				? `<label class="label" for="work-input">${this.tr('work_times', 'Typical Work Times')}</label><input id="work-input" type="text" placeholder="e.g. 09:00 - 18:00" value="${me.work_times || ''}">`
				: `<div class="label" aria-hidden="true">${this.tr('work_times', 'Typical Work Times')}</div><div class="value">${me.work_times || this.tr('not_set', 'Not set')}</div>`}
					</div>
					
					<div class="field" style="grid-column: span 2; margin-top: 0.5rem;">
						<div class="label">${this.tr('favorite_colors', 'Favorite Colors / Theme')}</div>
						<div style="display: flex; gap: 0.75rem; align-items: center; margin-top: 0.5rem; flex-wrap: wrap;">
							${this.isEditing ? `
								<select id="theme-preset-select" aria-label="Theme Presets" style="flex: 1; min-width: 140px;">
									<option value="">${this.tr('select_preset', 'Select Preset...')}</option>
									<option value="default" data-colors='["#14B8A6", "#0066FF", "#6366F1"]'>Default Fusion</option>
									<option value="brazil" data-colors='["#009739", "#FEDD00", "#012169"]'>Brazil</option>
									<option value="jamaica" data-colors='["#009B3A", "#FEDD00", "#000000"]'>Jamaica</option>
									<option value="mexico" data-colors='["#006341", "#C8102E", "#FFFFFF"]'>Mexico</option>
									<option value="usa" data-colors='["#B22234", "#3C3B6E", "#FFFFFF"]'>USA</option>
									<option value="uk" data-colors='["#00247D", "#CF142B", "#FFFFFF"]'>UK</option>
									<option value="japan" data-colors='["#BC002D", "#F4F4F4", "#333333"]'>Japan</option>
									<option value="france" data-colors='["#00209F", "#F64242", "#FFFFFF"]'>France</option>
									<option value="germany" data-colors='["#FFCE00", "#DD0000", "#000000"]'>Germany</option>
									<option value="sunrise" data-colors='["#FF8C00", "#FF4500", "#FFD700"]'>Sunrise</option>
									<option value="forest" data-colors='["#2D5A27", "#8B4513", "#DEB887"]'>Forest</option>
									<option value="arctic" data-colors='["#E0FFFF", "#00CED1", "#FFFFFF"]'>Arctic</option>
									<option value="deepsea" data-colors='["#000080", "#00008B", "#4682B4"]'>Deep Sea</option>
									<option value="darkred" data-colors='["#8B0000", "#4B0000", "#000000"]'>Dark Red</option>
									<option value="highcontrast" data-colors='["#00FF00", "#003300", "#FFFFFF"]'>High Contrast</option>
									<option value="grayscale" data-colors='["#333333", "#666666", "#999999"]'>Grayscale</option>
								</select>
								<div style="display: flex; gap: 0.5rem;">
									<input type="color" id="color-primary-input" value="${me.color_primary || '#14B8A6'}" style="width:32px; height:32px; padding:0; border:none; background:none;">
									<input type="color" id="color-secondary-input" value="${me.color_secondary || '#0066FF'}" style="width:32px; height:32px; padding:0; border:none; background:none;">
									<input type="color" id="color-tertiary-input" value="${me.color_tertiary || '#6366F1'}" style="width:32px; height:32px; padding:0; border:none; background:none;">
								</div>
							` : `
								<div style="display: flex; gap: 0.5rem;">
									<div style="width:16px; height:16px; border-radius:4px; background:${me.color_primary || '#14B8A6'}" title="Primary"></div>
									<div style="width:16px; height:16px; border-radius:4px; background:${me.color_secondary || '#0066FF'}" title="Secondary"></div>
									<div style="width:16px; height:16px; border-radius:4px; background:${me.color_tertiary || '#6366F1'}" title="Tertiary"></div>
								</div>
							`}
						</div>
					</div>
				</div>

				<div class="goals-section">
					<h3>${this.tr('life_goals', 'Life Goals & Core Values')}</h3>
					${this.isEditing
				? `<label class="label" for="context-input" style="font-size:0.65rem;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:0.05em;display:block;margin-bottom:0.5rem;">${this.tr('goals_edit_label', 'Goals and Values (one per line)')}</label><textarea id="context-input" placeholder="What drives you? What are your current focus areas?" aria-label="Life goals and core values">${me.context || ''}</textarea>`
				: `<ul aria-label="Your life goals and values">${(me.context || '').split('\n').filter((l: string) => l.trim() && !l.trim().startsWith('<!--') && !l.includes('## Growth Areas')).map((l: string) => `<li>${l.replace(/^#+\s*/, '')}</li>`).join('') || `<li>${this.tr('no_goals', 'No goals set.')}</li>`}</ul>`}
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

		// Global Color Application
		const applyColors = () => {
			const cp = (this.shadowRoot?.querySelector('#color-primary-input') as HTMLInputElement)?.value || me.color_primary || '#14B8A6';
			const cs = (this.shadowRoot?.querySelector('#color-secondary-input') as HTMLInputElement)?.value || me.color_secondary || '#0066FF';
			const ct = (this.shadowRoot?.querySelector('#color-tertiary-input') as HTMLInputElement)?.value || me.color_tertiary || '#6366F1';

			document.documentElement.style.setProperty('--accent-color', cp);
			document.documentElement.style.setProperty('--accent-secondary', cs);
			document.documentElement.style.setProperty('--accent-tertiary', ct);

			// Compute RGB for some glass effects
			const r = parseInt(cp.slice(1, 3), 16), g = parseInt(cp.slice(3, 5), 16), b = parseInt(cp.slice(5, 7), 16);
			document.documentElement.style.setProperty('--accent-color-rgb', `${r}, ${g}, ${b}`);
		};

		if (this.isEditing) {
			const preset = this.shadowRoot?.querySelector('#theme-preset-select');
			preset?.addEventListener('change', (e: any) => {
				const opt = e.target.options[e.target.selectedIndex];
				const colors = JSON.parse(opt.dataset.colors || '[]');
				if (colors.length >= 3) {
					(this.shadowRoot?.querySelector('#color-primary-input') as HTMLInputElement).value = colors[0];
					(this.shadowRoot?.querySelector('#color-secondary-input') as HTMLInputElement).value = colors[1];
					(this.shadowRoot?.querySelector('#color-tertiary-input') as HTMLInputElement).value = colors[2];
					applyColors();
				}
			});

			['#color-primary-input', '#color-secondary-input', '#color-tertiary-input'].forEach(id => {
				this.shadowRoot?.querySelector(id)?.addEventListener('input', applyColors);
			});
		}

		// Apply immediately on load
		applyColors();

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
