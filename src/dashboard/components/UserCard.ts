import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';

export class UserCard extends HTMLElement {
	private me: any = null;
	private isEditing: boolean = false;
	private t: Record<string, string> = {};
	private languages: Record<string, { native: string, eng: string }> = {
		en: { native: 'English', eng: 'English' },
		de: { native: 'Deutsch', eng: 'German' },
		zh: { native: '中文', eng: 'Mandarin Chinese' },
		ja: { native: '日本語', eng: 'Japanese' },
		ko: { native: '한국어', eng: 'Korean' },
		fr: { native: 'Français', eng: 'French' },
		es: { native: 'Español', eng: 'Spanish' },
		it: { native: 'Italiano', eng: 'Italian' },
		nl: { native: 'Nederlands', eng: 'Dutch' },
		sv: { native: 'Svenska', eng: 'Swedish' },
		da: { native: 'Dansk', eng: 'Danish' },
		no: { native: 'Norsk', eng: 'Norwegian' },
		pl: { native: 'Polski', eng: 'Polish' },
		cs: { native: 'Čeština', eng: 'Czech' },
		el: { native: 'Ελληνικά', eng: 'Greek' },
		tr: { native: 'Türkçe', eng: 'Turkish' },
		ru: { native: 'Русский', eng: 'Russian' },
		pt: { native: 'Português', eng: 'Portuguese' },
		ar: { native: 'العربية', eng: 'Arabic' },
		hi: { native: 'हिन्दी', eng: 'Hindi' },
		bn: { native: 'বাংলা', eng: 'Bengali' },
		id: { native: 'Bahasa Indonesia', eng: 'Indonesian' },
		vi: { native: 'Tiếng Việt', eng: 'Vietnamese' },
		ro: { native: 'Română', eng: 'Romanian' },
	};

	private themeOptions: Record<string, { label: string, colors: string[] }> = {
		fusion: { label: 'Default Fusion', colors: ["#14B8A6", "#0066FF", "#6366F1"] },
		cyberpunk: { label: 'Cyberpunk Neon', colors: ["#FF00FF", "#00FFFF", "#FFFF00"] },
		night_city: { label: 'Night City', colors: ["#F700FF", "#2100A3", "#FEDD00"] },
		forest: { label: 'Deep Forest', colors: ["#22C55E", "#15803D", "#84CC16"] },
		deep_sea: { label: 'Deep Sea', colors: ["#0066FF", "#000080", "#00CED1"] },
		ember: { label: 'Ember Glass', colors: ["#F97316", "#EF4444", "#F59E0B"] },
		aurora: { label: 'Aurora Borealis', colors: ["#A855F7", "#EC4899", "#06B6D4"] },
		midnight: { label: 'Midnight Blue', colors: ["#3B82F6", "#1D4ED8", "#60A5FA"] },
		void: { label: 'The Void', colors: ["#7C3AED", "#4F46E5", "#2D1B69"] },
		matrix: { label: 'Digital Matrix', colors: ["#00FF41", "#008F11", "#003B00"] },
		outrun: { label: 'Outrun 84', colors: ["#FF2E63", "#08D9D6", "#EAEAEA"] },
		synthwave: { label: 'Synthwave Glow', colors: ["#FF71CE", "#01CDFE", "#05FFA1"] },
		plasma: { label: 'Plasma Strike', colors: ["#9D50BB", "#6E48AA", "#FF4B2B"] },
		volcanic: { label: 'Volcanic Flow', colors: ["#FF416C", "#FF4B2B", "#42275A"] },
		frost: { label: 'Glacier Frost', colors: ["#00B4DB", "#0083B0", "#FFFFFF"] },
		sakura: { label: 'Sakura Petals', colors: ["#F9A8D4", "#EC4899", "#DB2777"] },
		copper: { label: 'Antique Copper', colors: ["#FB923C", "#D97706", "#92400E"] },
		carbon: { label: 'Carbon Fiber', colors: ["#E5E7EB", "#374151", "#6B7280"] },
		jade: { label: 'Imperial Jade', colors: ["#10B981", "#059669", "#6EE7B7"] },
		sunset: { label: 'Venice Sunset', colors: ["#FF512F", "#DD2476", "#F09819"] },
		oceanic: { label: 'Oceanic Depth', colors: ["#2193b0", "#6dd5ed", "#2C3E50"] },
		nebula: { label: 'Deep Nebula', colors: ["#4e54c8", "#8f94fb", "#243B55"] },
		royal: { label: 'Royal Gold', colors: ["#f9ca24", "#f0932b", "#4834d4"] },
		lava: { label: 'Molten Lava', colors: ["#eb4d4b", "#ff7979", "#130f40"] },
		emerald: { label: 'Emerald City', colors: ["#2ecc71", "#27ae60", "#f1c40f"] },
		amethyst: { label: 'Amethyst Spark', colors: ["#9b59b6", "#8e44ad", "#34495e"] },
		sunflower: { label: 'Sunflower Field', colors: ["#f1c40f", "#f39c12", "#27ae60"] },
		asphalt: { label: 'Wet Asphalt', colors: ["#34495e", "#2c3e50", "#7f8c8d"] },
		clouds: { label: 'Silver Clouds', colors: ["#ecf0f1", "#bdc3c7", "#95a5a6"] },
		concrete: { label: 'Polished Concrete', colors: ["#95a5a6", "#7f8c8d", "#2c3e50"] },
		pumpkin: { label: 'Pumpkin Spice', colors: ["#e67e22", "#d35400", "#2c3e50"] },
		alizarin: { label: 'Alizarin Crimson', colors: ["#e74c3c", "#c0392b", "#8e44ad"] },
		turquoise: { label: 'Turquoise Dream', colors: ["#1abc9c", "#16a085", "#2980b9"] },
		belize: { label: 'Belize Hole', colors: ["#2980b9", "#3498db", "#8e44ad"] },
		wisteria: { label: 'Blooming Wisteria', colors: ["#8e44ad", "#9b59b6", "#2c3e50"] },
		orange: { label: 'Zesty Orange', colors: ["#f39c12", "#e67e22", "#d35400"] },
		grenadier: { label: 'Grenadier Fire', colors: ["#d35400", "#e67e22", "#c0392b"] },
		midnight_bloom: { label: 'Midnight Bloom', colors: ["#a29bfe", "#6c5ce7", "#fd79a8"] },
		mint: { label: 'Fresh Mint', colors: ["#55efc4", "#00b894", "#81ecec"] },
		robins_egg: { label: 'Robins Egg', colors: ["#81ecec", "#00cec9", "#74b9ff"] },
		sour_lemon: { label: 'Sour Lemon', colors: ["#ffeaa7", "#fdcb6e", "#fab1a0"] },
		peach: { label: 'First Peach', colors: ["#fab1a0", "#ff7675", "#d63031"] },
		chi_gong: { label: 'Chi-Gong', colors: ["#d63031", "#ff7675", "#6c5ce7"] },
		pristine: { label: 'Pristine White', colors: ["#dfe6e9", "#b2bec3", "#636e72"] },
		shale: { label: 'Shale Gray', colors: ["#636e72", "#2d3436", "#00b894"] },
		dracula: { label: 'Dracula Castle', colors: ["#bd93f9", "#ff79c6", "#8be9fd"] },
		gruvbox: { label: 'Retro Gruvbox', colors: ["#fabd2f", "#fe8019", "#b8bb26"] },
		nord: { label: 'Arctic Nord', colors: ["#88c0d0", "#81a1c1", "#5e81ac"] },
		monokai_pro: { label: 'Monokai Pro', colors: ["#ffd866", "#fc9867", "#ff6188"] },
		solarized: { label: 'Solarized Fire', colors: ["#cb4b16", "#dc322f", "#268bd2"] },
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
				window.location.reload();
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
				${BUTTON_STYLES}
				${ACCESSIBILITY_STYLES}
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

				.theme-cycle-btn {
					background: rgba(255, 255, 255, 0.05);
					border: 1px solid rgba(255, 255, 255, 0.1);
					color: var(--accent-color);
					width: 34px;
					height: 34px;
					display: flex;
					align-items: center;
					justify-content: center;
					border-radius: 0.5rem;
					cursor: pointer;
					transition: all 0.2s;
					font-size: 1.1rem;
					flex-shrink: 0;
					user-select: none;
				}
				.theme-cycle-btn:hover {
					background: rgba(255, 255, 255, 0.1);
					border-color: var(--accent-color);
					transform: scale(1.05);
				}
				.theme-cycle-btn:active {
					transform: scale(0.95);
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
				.save-btn { text-transform: uppercase; letter-spacing: 0.05em; }
				.cancel-btn { text-transform: uppercase; letter-spacing: 0.05em; }
				button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible { 
					outline: 2px solid var(--accent-color, #14B8A6); 
					outline-offset: 2px; 
				}
				button:focus:not(:focus-visible), input:focus:not(:focus-visible), textarea:focus:not(:focus-visible), select:focus:not(:focus-visible) { outline: none; }
				/* Additional reduced-motion overrides beyond shared module */
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
				? `<label class="label" for="language-input">${this.tr('language_label', 'Language')}</label><select id="language-input" aria-label="Select Z\'s response language">${Object.entries(this.languages).map(([code, lang]) => `<option value="${code}" ${(me.language || 'en') === code ? 'selected' : ''}>${lang.native} · ${this.tr('lang_' + code, lang.eng)}</option>`).join('')}</select>`
				: `<div class="label" aria-hidden="true">${this.tr('language_label', 'Language')}</div><div class="value">${this.languages[me.language as string]?.native || 'English'} · ${this.tr('lang_' + (me.language || 'en'), this.languages[me.language as string]?.eng || 'English')}</div>`}
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
								<div style="display: flex; gap: 0.5rem; align-items: center; flex: 1;">
									<button id="theme-prev" class="theme-cycle-btn" title="Previous Theme" aria-label="Previous theme">‹</button>
									<select id="theme-preset-select" aria-label="${this.tr('aria_theme_presets', 'Theme Presets')}" style="flex: 1; min-width: 140px;">
										<option value="">${this.tr('select_preset', 'Select Preset...')}</option>
										${Object.entries(this.themeOptions).map(([val, opt]) => `
											<option value="${val}" data-colors='${JSON.stringify(opt.colors)}'>${this.tr('theme_' + val, opt.label)}</option>
										`).join('')}
									</select>
									<button id="theme-next" class="theme-cycle-btn" title="Next Theme" aria-label="Next theme">›</button>
								</div>
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

			const toRgb = (hex: string) => {
				const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
				return `${r}, ${g}, ${b}`;
			};
			document.documentElement.style.setProperty('--accent-color-rgb', toRgb(cp));
			document.documentElement.style.setProperty('--accent-secondary-rgb', toRgb(cs));
			document.documentElement.style.setProperty('--accent-tertiary-rgb', toRgb(ct));
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

			const cycle = (dir: number) => {
				const select = this.shadowRoot?.querySelector('#theme-preset-select') as HTMLSelectElement;
				if (!select) return;
				let idx = select.selectedIndex + dir;
				if (idx < 1) idx = select.options.length - 1;
				if (idx >= select.options.length) idx = 1;
				select.selectedIndex = idx;
				select.dispatchEvent(new Event('change'));
			};

			this.shadowRoot?.querySelector('#theme-prev')?.addEventListener('click', () => cycle(-1));
			this.shadowRoot?.querySelector('#theme-next')?.addEventListener('click', () => cycle(1));
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
