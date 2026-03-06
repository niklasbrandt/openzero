import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { initGoo } from '../services/gooStyles';

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

	private themeOptions: Record<string, { label: string, colors: string[], mode?: string }> = {
		fusion: { label: 'Default Fusion', colors: ["hsla(173, 80%, 40%, 1)", "hsla(216, 100%, 50%, 1)", "hsla(239, 84%, 67%, 1)"] },
		cyberpunk: { label: 'Cyberpunk Neon', colors: ["#FF00FF", "#00FFFF", "#FFFF00"] },
		night_city: { label: 'Night City', colors: ["#F700FF", "#2100A3", "#FEDD00"] },
		forest: { label: 'Deep Forest', colors: ["#22C55E", "#15803D", "#84CC16"] },
		deep_sea: { label: 'Deep Sea', colors: ["hsla(216, 100%, 50%, 1)", "#000080", "#00CED1"] },
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
		paper: { label: 'Light Paper', colors: ["#14B8A6", "#0066FF", "#3B82F6"], mode: 'light' },
		snow: { label: 'Highland Snow', colors: ["#059669", "#2563EB", "#4F46E5"], mode: 'light' },
		latte: { label: 'Morning Latte', colors: ["#D97706", "#2563EB", "#059669"], mode: 'light' },
	};

	private gooMode: boolean = false;
	private themeMode: 'dark' | 'light' | 'auto' = 'dark';

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.loadTranslations().then(() => this.fetchIdentity());
		this.gooMode = localStorage.getItem('goo-mode') === 'true';
		this.themeMode = (localStorage.getItem('theme-mode') as any) || 'dark';
		this.applyGoo();
		this.applyThemeMode();
		initGoo(this);
		window.addEventListener('goo-changed', () => initGoo(this));
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => this.render());
		});
	}

	private applyGoo() {
		if (this.gooMode) {
			document.body.classList.add('oz-goo-container');
		} else {
			document.body.classList.remove('oz-goo-container');
		}
	}

	private applyThemeMode() {
		if (this.themeMode === 'light') {
			document.documentElement.setAttribute('data-theme', 'light');
		} else if (this.themeMode === 'dark') {
			// Explicit dark-mode attribute prevents @media(prefers-color-scheme:light)
			// from overriding a manual dark preference when the OS theme is light.
			document.documentElement.setAttribute('data-theme', 'dark');
		} else {
			// Auto/System: remove attribute so @media handles theme selection.
			document.documentElement.removeAttribute('data-theme');
		}
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
				context: '',
				color_primary: 'hsla(173, 80%, 40%, 1)',
				color_secondary: 'hsla(216, 100%, 50%, 1)',
				color_tertiary: 'hsla(239, 84%, 67%, 1)'
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
				const updatedMe = await response.json();
				this.me = updatedMe;
				this.isEditing = false;
				this.render();
				window.dispatchEvent(new CustomEvent('identity-updated'));
				window.dispatchEvent(new CustomEvent('refresh-data'));
				this.applyToRoot(updatedMe.color_primary, updatedMe.color_secondary, updatedMe.color_tertiary);
			}
		} catch (e) {
			alert('Save failed');
		}
	}

	private applyToRoot(cp: string, cs: string, ct: string) {
		const hexToRgb = (hex: string) => {
			const h = hex.replace('#', '');
			return `${parseInt(h.slice(0, 2), 16)}, ${parseInt(h.slice(2, 4), 16)}, ${parseInt(h.slice(4, 6), 16)}`;
		};
		const hexToHsl = (hex: string) => {
			const h = hex.replace('#', '');
			let r = parseInt(h.slice(0, 2), 16) / 255;
			let g = parseInt(h.slice(2, 4), 16) / 255;
			let b = parseInt(h.slice(4, 6), 16) / 255;
			const max = Math.max(r, g, b), min = Math.min(r, g, b);
			let _h = 0, s = 0, l = (max + min) / 2;
			if (max !== min) {
				const d = max - min;
				s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
				switch (max) {
					case r: _h = (g - b) / d + (g < b ? 6 : 0); break;
					case g: _h = (b - r) / d + 2; break;
					case b: _h = (r - g) / d + 4; break;
				}
				_h /= 6;
			}
			return { h: Math.round(_h * 360), s: Math.round(s * 100), l: Math.round(l * 100) };
		};
		const root = document.documentElement;
		root.classList.add('no-transition');

		const applyColor = (prefix: string, hex: string) => {
			const hsl = hexToHsl(hex);
			root.style.setProperty(`--${prefix}-h`, hsl.h.toString());
			root.style.setProperty(`--${prefix}-s`, `${hsl.s}%`);
			root.style.setProperty(`--${prefix}-l`, `${hsl.l}%`);
			root.style.setProperty(`--${prefix}-rgb`, hexToRgb(hex));
			root.style.setProperty(`--${prefix}`, `hsla(${hsl.h}, ${hsl.s}%, ${hsl.l}%, 1)`);

			if (prefix === 'accent-primary') {
				root.style.setProperty('--accent-color', hex);
				root.style.setProperty('--accent-color-rgb', hexToRgb(hex));
				root.style.setProperty('--accent-glow', `rgba(${hexToRgb(hex)}, 0.4)`);
			} else if (prefix === 'accent-secondary') {
				root.style.setProperty('--accent-secondary', hex);
				root.style.setProperty('--accent-secondary-rgb', hexToRgb(hex));
			} else if (prefix === 'accent-tertiary') {
				root.style.setProperty('--accent-tertiary', hex);
			}
		};

		if (cp) applyColor('accent-primary', cp);
		if (cs) applyColor('accent-secondary', cs);
		if (ct) applyColor('accent-tertiary', ct);

		// Update localStorage cache so next page load paints instantly
		const cache: Record<string, string> = {};
		if (cp) cache.accent = cp;
		if (cs) cache.secondary = cs;
		if (ct) cache.tertiary = ct;
		if (Object.keys(cache).length) {
			localStorage.setItem('z_theme', JSON.stringify(cache));
		}

		requestAnimationFrame(() => {
			requestAnimationFrame(() => {
				root.classList.remove('no-transition');
			});
		});
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
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					font-family: var(--font-sans, 'Inter', sans-serif);
				}

				.header { display: flex; justify-content: space-between; align-items: center; }
				.user-info { display: flex; align-items: center; gap: 1rem; }
				.avatar {
					width: 48px; height: 48px;
					background: linear-gradient(135deg, var(--accent-primary, hsla(173, 80%, 40%, 1)), var(--accent-secondary, hsla(216, 100%, 50%, 1)));
					border-radius: 0.4rem;
					display: flex; align-items: center; justify-content: center;
					font-weight: 800; font-size: 1.25rem;
					box-shadow: 0 4px 12px var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.2));
					color: #fff;
					transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
				}
				:host(:hover) .avatar { transform: scale(1.1) rotate(-5deg); }

				h2 { margin: 0; font-size: 1.1rem; }

				.edit-btn {
					background: var(--surface-card, hsla(0,0%,100%,0.05));
					border: 1px solid var(--border-subtle, hsla(0,0%,100%,0.1));
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					padding: 6px 12px;
					font-size: 0.7rem;
					cursor: pointer;
					text-transform: uppercase;
					letter-spacing: 0.05em;
					border-radius: 0.4rem;
					transition: all var(--duration-fast, 0.2s);
					min-height: 32px;
					display: flex;
					align-items: center;
					font-weight: 700;
				}
				.edit-btn:hover {
					background: var(--surface-card-hover, hsla(0,0%,100%,0.1));
					border-color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					box-shadow: 0 0 15px var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.2));
				}

				.grid {
					display: grid;
					grid-template-columns: 1fr 1fr;
					gap: 1rem;
				}

				.field { display: flex; flex-direction: column; gap: 4px; }
				.label { 
					font-size: 0.65rem; 
					color: var(--text-muted, hsla(0,0%,100%,0.4)); 
					text-transform: uppercase; 
					letter-spacing: 0.05em; 
					font-weight: 600;
				}
				.value { 
					font-size: 0.9rem; 
					color: var(--text-primary, hsla(0, 0%, 100%, 1)); 
					font-weight: 500; 
					min-height: 1.2rem;
				}

				input, textarea, select {
					background: var(--surface-card-subtle, hsla(0,0%,0%,0.3));
					border: 1px solid var(--border-subtle, hsla(0,0%,100%,0.1));
					border-radius: 0.5rem;
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
					padding: 10px 12px;
					font-size: 0.85rem;
					width: 100%;
					box-sizing: border-box;
					transition: border-color var(--duration-fast, 0.2s);
					min-height: 44px;
				}
				input:focus, textarea:focus, select:focus {
					border-color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					outline: none;
				}

				textarea { min-height: 100px; resize: vertical; line-height: 1.5; }

				select {
					cursor: pointer;
					appearance: none;
					background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2314B8A6' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
					background-repeat: no-repeat;
					background-position: right 12px center;
					padding-right: 32px;
				}

				select option {
					background: hsla(240, 28%, 14%, 1);
					color: var(--text-primary, hsla(0, 0%, 100%, 1));
				}

				.theme-cycle-btn {
					background: var(--surface-card, hsla(0, 0%, 100%, 0.05));
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.1));
					color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					width: 32px;
					height: 32px;
					display: flex;
					align-items: center;
					justify-content: center;
					border-radius: 0.4rem;
					cursor: pointer;
					transition: all var(--duration-fast, 0.2s);
					font-size: 0.9rem;
					flex-shrink: 0;
					user-select: none;
				}
				.theme-cycle-btn:hover {
					background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.1));
					border-color: var(--accent-primary, hsla(173, 80%, 40%, 1));
					transform: scale(1.05);
				}
				.theme-cycle-btn:active {
					transform: scale(0.95);
				}

				.goals-section h3 { 
					font-size: 0.7rem; 
					color: var(--accent-primary, hsla(173, 80%, 40%, 1)); 
					text-transform: uppercase; 
					margin: 1rem 0 0.5rem 0;
					display: flex;
					align-items: center;
					gap: 8px;
					font-weight: 700;
					letter-spacing: 0.08em;
				}
				.goals-section h3::after {
					content: ''; flex: 1; height: 1px; background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.2));
				}

				ul { list-style: none; padding: 0; margin: 0; }
				li { 
					font-size: 0.85rem; 
					color: var(--text-secondary, hsla(0,0%,100%,0.8)); 
					margin-bottom: 0.6rem; 
					position: relative; 
					padding-left: 1.35rem; 
					line-height: 1.5;
				}
				li::before { 
					content: '◈'; 
					position: absolute; 
					left: 0; 
					color: var(--accent-primary, hsla(173, 80%, 40%, 1)); 
					font-size: 0.75rem; 
					top: 0.1rem; 
				}

				.actions { display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.25rem; }

				.checkbox-group {
					display: flex;
					align-items: center;
					gap: 0.75rem;
					background: var(--surface-card, hsla(0, 0%, 100%, 0.05));
					padding: 0.75rem 1rem;
					border-radius: 0.5rem;
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.1));
					cursor: pointer;
					transition: all 0.2s ease;
				}
				.checkbox-group:hover {
					background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.08));
					border-color: var(--accent-primary);
				}
				.checkbox-group input { width: auto; min-height: auto; cursor: pointer; }
				.checkbox-group label { cursor: pointer; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); margin: 0; }

				.three-way-toggle {
					display: flex;
					background: var(--surface-card-subtle, hsla(0, 0%, 0%, 0.3));
					padding: 3px;
					border-radius: 0.5rem;
					border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.1));
					margin-bottom: 0.5rem;
				}
				.toggle-opt {
					flex: 1;
					text-align: center;
					padding: 6px;
					font-size: 0.7rem;
					font-weight: 700;
					text-transform: uppercase;
					cursor: pointer;
					border-radius: 0.35rem;
					transition: all 0.2s ease;
					color: var(--text-muted);
				}
				.toggle-opt.active {
					background: var(--accent-primary);
					color: #000;
				}

				button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible { 
					outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); 
					outline-offset: 3px; 
				}

				@media (forced-colors: active) {
					.avatar { background: ButtonFace; border: 2px solid ButtonText; }
					.edit-btn { color: LinkText; }
					.theme-cycle-btn { border: 1px solid ButtonText; }
					li::before { color: Highlight; }
				}
			</style>

			<div class="card">
				<div class="header">
					<div class="user-info">
						<div class="avatar" aria-hidden="true">${(me.name || 'U')[0]}</div>
						${this.isEditing
							? `<div style="display:flex;flex-direction:column;gap:2px;"><label class="label" for="name-input" style="margin:0;">${this.tr('name_label', 'Name')}</label><input id="name-input" type="text" placeholder="Full Name" value="${me.name || ''}" aria-label="Your name" autocomplete="name"></div>`
							: `<div>
									<h2>${me.name || 'User'}</h2>
									<div class="label" style="text-transform: none; margin-top: 2px;">${me.residency || this.tr('resident', 'Resident')}</div>
								</div>`}
					</div>
					<div style="display: flex; gap: 0.5rem;">
						<button class="edit-btn" id="edit-trigger" aria-label="Edit personal profile">${this.tr('edit', 'Edit')}</button>
					</div>
				</div>

				${this.isEditing ? `
					<div class="grid">
						<div class="field">
							<label class="label" for="language-input">${this.tr('fav_lang', 'Language')}</label>
							<select id="language-input">
								${Object.entries(this.languages).map(([code, meta]) => `
									<option value="${code}" ${me.language === code ? 'selected' : ''}>${meta.native}</option>
								`).join('')}
							</select>
						</div>
						<div class="field">
							<label class="label" for="bday-input">${this.tr('birthday', 'Birthday')}</label>
							<input id="bday-input" type="text" placeholder="YYYY-MM-DD" value="${me.birthday || ''}" autocomplete="bday">
						</div>
						<div class="field">
							<label class="label" for="gender-input">${this.tr('gender', 'Gender')}</label>
							<input id="gender-input" type="text" placeholder="e.g. Non-binary" value="${me.gender || ''}" autocomplete="sex">
						</div>
						<div class="field">
							<label class="label" for="residency-input">${this.tr('residency', 'Residency')}</label>
							<input id="residency-input" type="text" placeholder="City, Country" value="${me.residency || ''}">
						</div>
						<div class="field">
							<label class="label" for="town-input">${this.tr('town', 'Town')}</label>
							<input id="town-input" type="text" placeholder="Berlin" value="${me.town || ''}">
						</div>
						<div class="field">
							<label class="label" for="country-input">${this.tr('country', 'Country')}</label>
							<input id="country-input" type="text" placeholder="Germany" value="${me.country || ''}" autocomplete="country-name">
						</div>
						<div class="field">
							<label class="label" for="timezone-input">${this.tr('timezone_label', 'Timezone')}</label>
							<input id="timezone-input" type="text" placeholder="Europe/Berlin" value="${me.timezone || ''}">
						</div>
						<div class="field">
							<label class="label" for="work-input">${this.tr('work_times', 'Work Times')}</label>
							<input id="work-input" type="text" placeholder="e.g. 09:00 - 17:00" value="${me.work_times || ''}">
						</div>
						<div class="field">
							<label class="label" for="brief-input">${this.tr('briefing', 'Briefing')}</label>
							<input id="brief-input" type="time" value="${me.briefing_time || '08:00'}">
						</div>
						
						<div class="field" style="grid-column: span 2;">
							<label class="label">${this.tr('display_settings', 'Display Settings')}</label>
							<div class="three-way-toggle">
								<div class="toggle-opt ${this.themeMode === 'light' ? 'active' : ''}" data-mode="light">${this.tr('light', 'Light')}</div>
								<div class="toggle-opt ${this.themeMode === 'auto' ? 'active' : ''}" data-mode="auto">${this.tr('auto', 'Auto')}</div>
								<div class="toggle-opt ${this.themeMode === 'dark' ? 'active' : ''}" data-mode="dark">${this.tr('dark', 'Dark')}</div>
							</div>
							<div class="checkbox-group" id="goo-toggle-wrapper">
								<input type="checkbox" id="goo-mode-checkbox" ${this.gooMode ? 'checked' : ''}>
								<label for="goo-mode-checkbox">${this.tr('goo_mode', 'I like Goo (Phase 4 Organic Interaction)')}</label>
							</div>
						</div>

						<div class="field" style="grid-column: span 2;">
							<label class="label" for="theme-preset-select">${this.tr('theme_preset', 'Theme Preset')}</label>
							<div style="display: flex; gap: 0.5rem; align-items: center;">
								<button class="theme-cycle-btn" id="theme-prev" title="${this.tr('prev_theme', 'Previous Theme')}" style="width: 32px; height: 44px; font-size: 0.8rem;">◀</button>
								<select id="theme-preset-select" style="flex: 1;">
									<option value="">${this.tr('select_preset', 'Select Preset...')}</option>
									${Object.entries(this.themeOptions).map(([key, opt]) => `
										<option value="${key}">${opt.label}</option>
									`).join('')}
								</select>
								<button class="theme-cycle-btn" id="theme-next" title="${this.tr('next_theme', 'Next Theme')}" style="width: 32px; height: 44px; font-size: 0.8rem;">▶</button>
							</div>
						</div>

						<div class="field" style="grid-column: span 2;">
							<label class="label">${this.tr('accent_colors', 'Accent Colors')}</label>
							<div style="display: flex; gap: 0.5rem;">
								<input type="text" id="color-primary-input" value="${me.color_primary || 'hsla(173, 80%, 40%, 1)'}" title="Primary Accent" style="flex: 1;">
								<input type="text" id="color-secondary-input" value="${me.color_secondary || 'hsla(216, 100%, 50%, 1)'}" title="Secondary Accent" style="flex: 1;">
								<input type="text" id="color-tertiary-input" value="${me.color_tertiary || 'hsla(239, 84%, 67%, 1)'}" title="Tertiary Accent" style="flex: 1;">
							</div>
						</div>

						<div class="field" style="grid-column: span 2;">
							<label class="label" for="context-input">${this.tr('bio', 'Bio / Context')}</label>
							<textarea id="context-input" rows="4">${me.context || ''}</textarea>
						</div>
					</div>

					<div class="actions">
						<button class="oz-btn oz-btn-secondary" id="cancel-trigger">${this.tr('discard', 'Discard')}</button>
						<button class="oz-btn oz-btn-primary" id="save-trigger">${this.tr('save_profile', 'Save Profile')}</button>
					</div>
				` : `
					<div class="grid">
						<div class="field">
							<div class="label">${this.tr('location', 'Location')}</div>
							<div class="value">${me.town || '—'}, ${me.country || '—'}</div>
						</div>
						<div class="field">
							<div class="label">${this.tr('timezone_label', 'Timezone')}</div>
							<div class="value">${me.timezone || 'UTC'}</div>
						</div>
						<div class="field">
							<div class="label">${this.tr('work_times', 'Work Times')}</div>
							<div class="value">${me.work_times || '—'}</div>
						</div>
						<div class="field">
							<div class="label">${this.tr('briefing', 'Briefing')}</div>
							<div class="value">${me.briefing_time || '08:00'}</div>
						</div>
						<div class="goals-section" style="grid-column: span 2;">
							<h3>${this.tr('life_goals', 'Life Goals & Ethics')}</h3>
							<ul aria-label="${this.tr('aria_goals_list', 'Your life goals and values')}">
								${(me.context || '').split('\n').filter((l: string) => l.trim()).map((l: string) => `<li>${l.replace(/^#+\s*/, '')}</li>`).join('') || `<li>${this.tr('no_goals', 'No goals set.')}</li>`}
							</ul>
						</div>
					</div>
				`}
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

		const applyColors = () => {
			const cp = (this.shadowRoot?.querySelector('#color-primary-input') as HTMLInputElement)?.value || me.color_primary || 'hsla(173, 80%, 40%, 1)';
			const cs = (this.shadowRoot?.querySelector('#color-secondary-input') as HTMLInputElement)?.value || me.color_secondary || 'hsla(216, 100%, 50%, 1)';
			const ct = (this.shadowRoot?.querySelector('#color-tertiary-input') as HTMLInputElement)?.value || me.color_tertiary || 'hsla(239, 84%, 67%, 1)';
			this.applyToRoot(cp, cs, ct);
		};

		if (this.isEditing) {
			const gooToggle = this.shadowRoot?.querySelector('#goo-mode-checkbox') as HTMLInputElement;
			gooToggle?.addEventListener('change', () => {
				this.gooMode = gooToggle.checked;
				localStorage.setItem('goo-mode', String(this.gooMode));
				this.applyGoo();
				window.dispatchEvent(new Event('goo-changed'));
			});

			this.shadowRoot?.querySelectorAll('.toggle-opt').forEach(opt => {
				opt.addEventListener('click', () => {
					this.themeMode = (opt as HTMLElement).dataset.mode as any;
					localStorage.setItem('theme-mode', this.themeMode);
					this.applyThemeMode();
					this.render(); // Redraw toggle state
				});
			});

			const presetSelect = this.shadowRoot?.querySelector('#theme-preset-select') as HTMLSelectElement;

			const cycleTheme = (direction: 'next' | 'prev') => {
				const keys = Object.keys(this.themeOptions);
				const currentKey = presetSelect.value || localStorage.getItem('theme-preset') || 'fusion';
				let currentIdx = keys.indexOf(currentKey);
				if (currentIdx === -1) currentIdx = 0;

				const nextIdx = direction === 'next' 
					? (currentIdx + 1) % keys.length 
					: (currentIdx - 1 + keys.length) % keys.length;
				
				const nextKey = keys[nextIdx];
				presetSelect.value = nextKey;
				
				// Trigger the change event logic
				const theme = this.themeOptions[nextKey] as any;
				if (theme) {
					(this.shadowRoot?.querySelector('#color-primary-input') as HTMLInputElement).value = theme.colors[0];
					(this.shadowRoot?.querySelector('#color-secondary-input') as HTMLInputElement).value = theme.colors[1];
					(this.shadowRoot?.querySelector('#color-tertiary-input') as HTMLInputElement).value = theme.colors[2];
					
					if (theme.mode === 'light') {
						this.themeMode = 'light';
						localStorage.setItem('theme-mode', 'light');
						this.applyThemeMode();
					} else {
						this.themeMode = 'dark';
						localStorage.setItem('theme-mode', 'dark');
						this.applyThemeMode();
					}
					
					applyColors();
				}
			};

			this.shadowRoot?.querySelector('#theme-next')?.addEventListener('click', (e) => {
				e.preventDefault();
				cycleTheme('next');
			});

			this.shadowRoot?.querySelector('#theme-prev')?.addEventListener('click', (e) => {
				e.preventDefault();
				cycleTheme('prev');
			});

			presetSelect?.addEventListener('change', () => {
				const opt = presetSelect.value;
				const theme = this.themeOptions[opt] as any;
				if (theme) {
					(this.shadowRoot?.querySelector('#color-primary-input') as HTMLInputElement).value = theme.colors[0];
					(this.shadowRoot?.querySelector('#color-secondary-input') as HTMLInputElement).value = theme.colors[1];
					(this.shadowRoot?.querySelector('#color-tertiary-input') as HTMLInputElement).value = theme.colors[2];
					
					if (theme.mode === 'light') {
						document.documentElement.setAttribute('data-theme', 'light');
					} else {
						document.documentElement.removeAttribute('data-theme');
					}
					
					applyColors();
				}
			});

			['#color-primary-input', '#color-secondary-input', '#color-tertiary-input'].forEach(id => {
				this.shadowRoot?.querySelector(id)?.addEventListener('input', applyColors);
			});
		}

		applyColors();

		this.shadowRoot.querySelectorAll('input').forEach(el => {
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
