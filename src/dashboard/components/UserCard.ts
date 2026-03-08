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

	private themeOptions: Record<string, { label: string, colors: string[] }> = {
		// Default
		fusion: { label: 'Default Fusion', colors: ["hsla(196, 78%, 40%, 1)", "hsla(216, 100%, 50%, 1)", "hsla(239, 84%, 67%, 1)"] },
		// Natural Elements
		wind: { label: 'Wind', colors: ["hsla(200, 40%, 58%, 1)", "hsla(195, 45%, 66%, 1)", "hsla(208, 35%, 48%, 1)"] },
		water: { label: 'Water', colors: ["hsla(207, 90%, 35%, 1)", "hsla(195, 85%, 43%, 1)", "hsla(215, 96%, 28%, 1)"] },
		fire: { label: 'Fire', colors: ["hsla(5, 94%, 47%, 1)", "hsla(0, 86%, 43%, 1)", "hsla(20, 92%, 50%, 1)"] },
		earth: { label: 'Earth', colors: ["hsla(36, 70%, 30%, 1)", "hsla(82, 27%, 38%, 1)", "hsla(25, 58%, 43%, 1)"] },
		// Natural Environments
		polar: { label: 'Polar', colors: ["hsla(183, 37%, 75%, 1)", "hsla(207, 36%, 44%, 1)", "hsla(215, 52%, 22%, 1)"] },
		mountain: { label: 'Mountain', colors: ["hsla(208, 7%, 43%, 1)", "hsla(209, 7%, 34%, 1)", "hsla(218, 10%, 59%, 1)"] },
		forest: { label: 'Forest', colors: ["hsla(154, 40%, 28%, 1)", "hsla(153, 37%, 37%, 1)", "hsla(143, 46%, 51%, 1)"] },
		desert: { label: 'Desert', colors: ["hsla(30, 41%, 56%, 1)", "hsla(34, 46%, 63%, 1)", "hsla(22, 36%, 49%, 1)"] },
		coast: { label: 'Coast', colors: ["hsla(199, 99%, 38%, 1)", "hsla(193, 89%, 61%, 1)", "hsla(27, 87%, 65%, 1)"] },
		sky: { label: 'Sky', colors: ["hsla(213, 83%, 61%, 1)", "hsla(192, 95%, 60%, 1)", "hsla(45, 95%, 69%, 1)"] },
		// Natural Phenomena
		aurora: { label: 'Aurora', colors: ["hsla(142, 71%, 45%, 1)", "hsla(271, 80%, 62%, 1)", "hsla(187, 93%, 42%, 1)"] },
		storm: { label: 'Storm', colors: ["hsla(209, 16%, 37%, 1)", "hsla(198, 92%, 59%, 1)", "hsla(0, 0%, 90%, 1)"] },
		jungle: { label: 'Jungle', colors: ["hsla(138, 68%, 29%, 1)", "hsla(77, 81%, 54%, 1)", "hsla(44, 92%, 43%, 1)"] },
		// IDE Palettes
		solarized: { label: 'Solarized', colors: ["hsla(18, 80%, 44%, 1)", "hsla(205, 69%, 49%, 1)", "hsla(175, 60%, 41%, 1)"] },
		monokai: { label: 'Monokai', colors: ["hsla(338, 95%, 56%, 1)", "hsla(32, 98%, 56%, 1)", "hsla(80, 75%, 55%, 1)"] },
		dracula: { label: 'Dracula', colors: ["hsla(265, 89%, 78%, 1)", "hsla(320, 100%, 73%, 1)", "hsla(191, 97%, 77%, 1)"] },
		gruvbox: { label: 'Gruvbox', colors: ["hsla(40, 94%, 57%, 1)", "hsla(25, 98%, 55%, 1)", "hsla(75, 40%, 53%, 1)"] },
		nord: { label: 'Nord', colors: ["hsla(193, 43%, 67%, 1)", "hsla(210, 34%, 63%, 1)", "hsla(213, 32%, 52%, 1)"] },
		catppuccin: { label: 'Catppuccin', colors: ["hsla(267, 84%, 81%, 1)", "hsla(217, 92%, 76%, 1)", "hsla(115, 54%, 76%, 1)"] },
		tokyo_night: { label: 'Tokyo Night', colors: ["hsla(217, 92%, 76%, 1)", "hsla(267, 84%, 81%, 1)", "hsla(199, 97%, 74%, 1)"] },
		// Monochromatic
		mono_silver: { label: 'Monochrome Silver', colors: ["hsla(210, 11%, 71%, 1)", "hsla(208, 7%, 44%, 1)", "hsla(210, 15%, 82%, 1)"] },
		mono_teal: { label: 'Monochrome Teal', colors: ["hsla(173, 80%, 40%, 1)", "hsla(174, 76%, 33%, 1)", "hsla(172, 66%, 63%, 1)"] },
		mono_violet: { label: 'Monochrome Violet', colors: ["hsla(262, 83%, 58%, 1)", "hsla(263, 70%, 50%, 1)", "hsla(263, 89%, 66%, 1)"] },
		// Pure Colors
		color_red: { label: 'Red', colors: ["hsla(0, 72%, 51%, 1)", "hsla(0, 64%, 39%, 1)", "hsla(0, 91%, 71%, 1)"] },
		color_blue: { label: 'Blue', colors: ["hsla(217, 91%, 60%, 1)", "hsla(221, 83%, 53%, 1)", "hsla(213, 94%, 68%, 1)"] },
		color_green: { label: 'Green', colors: ["hsla(142, 71%, 45%, 1)", "hsla(142, 76%, 36%, 1)", "hsla(142, 69%, 58%, 1)"] },
		color_purple: { label: 'Purple', colors: ["hsla(271, 91%, 65%, 1)", "hsla(271, 81%, 56%, 1)", "hsla(270, 95%, 75%, 1)"] },
		color_orange: { label: 'Orange', colors: ["hsla(25, 95%, 53%, 1)", "hsla(21, 90%, 48%, 1)", "hsla(27, 96%, 61%, 1)"] },
		color_cyan: { label: 'Cyan', colors: ["hsla(187, 85%, 53%, 1)", "hsla(189, 94%, 43%, 1)", "hsla(186, 94%, 82%, 1)"] },
		color_gold: { label: 'Gold', colors: ["hsla(45, 93%, 47%, 1)", "hsla(40, 96%, 40%, 1)", "hsla(48, 96%, 53%, 1)"] },
		color_indigo: { label: 'Indigo', colors: ["hsla(239, 84%, 67%, 1)", "hsla(243, 75%, 59%, 1)", "hsla(234, 89%, 74%, 1)"] },
		// Glassmorphism
		glass_frost: { label: 'Glass Frost', colors: ["hsla(187, 97%, 72%, 1)", "hsla(186, 100%, 80%, 1)", "hsla(196, 94%, 66%, 1)"] },
		glass_ember: { label: 'Glass Ember', colors: ["hsla(28, 96%, 61%, 1)", "hsla(38, 96%, 72%, 1)", "hsla(24, 94%, 53%, 1)"] },
		// Style
		neon: { label: 'Neon', colors: ["hsla(300, 100%, 50%, 1)", "hsla(180, 100%, 50%, 1)", "hsla(60, 100%, 50%, 1)"] },
		// High Contrast
		hc_1: { label: 'High Contrast I', colors: ["hsla(198, 93%, 60%, 1)", "hsla(28, 96%, 61%, 1)", "hsla(267, 84%, 81%, 1)"] },
		hc_2: { label: 'High Contrast II', colors: ["hsla(48, 96%, 53%, 1)", "hsla(322, 91%, 68%, 1)", "hsla(152, 68%, 52%, 1)"] },
		hc_3: { label: 'High Contrast III', colors: ["hsla(0, 0%, 100%, 1)", "hsla(60, 100%, 50%, 1)", "hsla(180, 100%, 50%, 1)"] },
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
		} catch (_e) {
			alert('Save failed');
		}
	}

	private parseColor(color: string): { h: number, s: number, l: number, a: number } {
		const m = /hsla?\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%(?:\s*,\s*([\d.]+))?\s*\)/.exec(color);
		if (m) return { h: Math.round(+m[1]), s: Math.round(+m[2]), l: Math.round(+m[3]), a: m[4] !== undefined ? +m[4] : 1 };
		const h = color.replace('#', '');
		const r = parseInt(h.slice(0, 2), 16) / 255, g = parseInt(h.slice(2, 4), 16) / 255, b = parseInt(h.slice(4, 6), 16) / 255;
		const max = Math.max(r, g, b), min = Math.min(r, g, b);
		let _h = 0, s = 0;
		const l = (max + min) / 2;
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
		return { h: Math.round(_h * 360), s: Math.round(s * 100), l: Math.round(l * 100), a: 1 };
	}

	private hslToRgb(h: number, s: number, l: number): string {
		s /= 100; l /= 100;
		const k = (n: number) => (n + h / 30) % 12;
		const a = s * Math.min(l, 1 - l);
		const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
		return `${Math.round(f(0) * 255)}, ${Math.round(f(8) * 255)}, ${Math.round(f(4) * 255)}`;
	}

	private applyToRoot(cp: string, cs: string, ct: string) {
		const root = document.documentElement;
		root.classList.add('no-transition');

		const applyColor = (prefix: string, color: string) => {
			const { h, s, l, a } = this.parseColor(color);
			const rgb = this.hslToRgb(h, s, l);
			root.style.setProperty(`--${prefix}-h`, h.toString());
			root.style.setProperty(`--${prefix}-s`, `${s}%`);
			root.style.setProperty(`--${prefix}-l`, `${l}%`);
			root.style.setProperty(`--${prefix}-rgb`, rgb);
			root.style.setProperty(`--${prefix}`, `hsla(${h}, ${s}%, ${l}%, ${a})`);

			if (prefix === 'accent-primary') {
				root.style.setProperty('--accent-color', `hsla(${h}, ${s}%, ${l}%, ${a})`);
				root.style.setProperty('--accent-color-rgb', rgb);
				root.style.setProperty('--accent-glow', `rgba(${rgb}, 0.4)`);
			} else if (prefix === 'accent-secondary') {
				root.style.setProperty('--accent-secondary', `hsla(${h}, ${s}%, ${l}%, ${a})`);
				root.style.setProperty('--accent-secondary-rgb', rgb);
			} else if (prefix === 'accent-tertiary') {
				root.style.setProperty('--accent-tertiary', `hsla(${h}, ${s}%, ${l}%, ${a})`);
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
					color: var(--accent-text, var(--accent-primary, hsla(173, 80%, 40%, 1)));
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
					color: var(--accent-text, var(--accent-primary, hsla(173, 80%, 40%, 1))); 
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

				/* Color swatch buttons */
				.color-swatches { display: flex; gap: 0.5rem; }
				.color-swatch {
					flex: 1;
					display: flex;
					align-items: center;
					gap: 0.5rem;
					background: var(--surface-card, hsla(0,0%,100%,0.05));
					border: 1px solid var(--border-subtle, hsla(0,0%,100%,0.1));
					border-radius: 0.5rem;
					padding: 8px 10px;
					cursor: pointer;
					transition: all 0.2s ease;
					color: var(--text-secondary, hsla(0,0%,100%,0.7));
					font-size: 0.7rem;
					font-weight: 600;
					text-transform: uppercase;
					letter-spacing: 0.04em;
					min-height: 44px;
				}
				.color-swatch:hover {
					background: var(--surface-card-hover, hsla(0,0%,100%,0.1));
					border-color: var(--accent-primary, hsla(173,80%,40%,1));
				}
				.swatch-dot {
					width: 18px; height: 18px;
					border-radius: 50%;
					flex-shrink: 0;
					border: 2px solid hsla(0,0%,100%,0.2);
					display: inline-block;
				}
				/* HSLA picker overlay */
				.picker-wrap { position: relative; grid-column: span 2; }
				.hsla-picker {
					position: absolute;
					z-index: 100;
					top: 0; left: 0; right: 0;
					background: var(--surface-overlay, hsla(240,28%,10%,0.97));
					border: 1px solid var(--border-subtle, hsla(0,0%,100%,0.15));
					border-radius: 0.75rem;
					padding: 1rem;
					box-shadow: 0 16px 48px hsla(0,0%,0%,0.5);
					backdrop-filter: blur(20px);
					display: flex;
					flex-direction: column;
					gap: 0.75rem;
				}
				.hsla-picker[hidden] { display: none; }
				.picker-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.25rem; }
				.picker-title { font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted, hsla(0,0%,100%,0.4)); }
				.picker-preview { width: 32px; height: 32px; border-radius: 50%; border: 2px solid hsla(0,0%,100%,0.3); flex-shrink: 0; }
				.picker-row { display: flex; align-items: center; gap: 0.5rem; }
				.picker-row-label { font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted, hsla(0,0%,100%,0.4)); width: 72px; flex-shrink: 0; }
				.picker-range {
					flex: 1; height: 6px; border-radius: 3px; cursor: pointer;
					min-height: auto; padding: 0; border: none;
					-webkit-appearance: none; appearance: none; width: auto;
				}
				.picker-range::-webkit-slider-thumb {
					-webkit-appearance: none; width: 16px; height: 16px; border-radius: 50%;
					background: #fff; cursor: pointer; border: 2px solid hsla(0,0%,0%,0.3); box-shadow: 0 1px 4px hsla(0,0%,0%,0.4);
				}
				.picker-range-h { background: linear-gradient(to right, hsl(0,100%,50%), hsl(60,100%,50%), hsl(120,100%,50%), hsl(180,100%,50%), hsl(240,100%,50%), hsl(300,100%,50%), hsl(360,100%,50%)); }
				.picker-range-s { background: linear-gradient(to right, hsl(0,0%,50%), hsl(180,100%,50%)); }
				.picker-range-l { background: linear-gradient(to right, #000, hsl(180,100%,50%), #fff); }
				.picker-range-a { background: linear-gradient(to right, transparent, currentColor); }
				.picker-num { width: 52px; min-height: auto; padding: 4px 6px; font-size: 0.75rem; text-align: center; flex-shrink: 0; }
				.picker-actions { display: flex; gap: 0.5rem; justify-content: flex-end; }

				@media (prefers-reduced-motion: reduce) { .color-swatch { transition: none; } }

				@media (forced-colors: active) {
					.avatar { background: ButtonFace; border: 2px solid ButtonText; }
					.edit-btn { color: LinkText; }
					.theme-cycle-btn { border: 1px solid ButtonText; }
					li::before { color: Highlight; }
					.color-swatch { border: 1px solid ButtonText; }
					.hsla-picker { border: 1px solid ButtonText; }
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
										<option value="${key}">${this.tr('theme_' + key, opt.label)}</option>
									`).join('')}
								</select>
								<button class="theme-cycle-btn" id="theme-next" title="${this.tr('next_theme', 'Next Theme')}" style="width: 32px; height: 44px; font-size: 0.8rem;">▶</button>
							</div>
						</div>

						<div class="field picker-wrap" style="grid-column: span 2;">
							<label class="label">${this.tr('accent_colors', 'Accent Colors')}</label>
							<input type="hidden" id="color-primary-input" value="${me.color_primary || 'hsla(173, 80%, 40%, 1)'}">
							<input type="hidden" id="color-secondary-input" value="${me.color_secondary || 'hsla(216, 100%, 50%, 1)'}">
							<input type="hidden" id="color-tertiary-input" value="${me.color_tertiary || 'hsla(239, 84%, 67%, 1)'}">
							<div class="color-swatches">
								<button class="color-swatch" id="swatch-primary" data-target="color-primary-input" aria-label="${this.tr('primary_label', 'Primary Accent')}">
									<span class="swatch-dot" id="swatch-dot-primary" style="background:${me.color_primary || 'hsla(173,80%,40%,1)'}"></span>
									<span>${this.tr('primary_label', 'Primary')}</span>
								</button>
								<button class="color-swatch" id="swatch-secondary" data-target="color-secondary-input" aria-label="${this.tr('secondary_label', 'Secondary Accent')}">
									<span class="swatch-dot" id="swatch-dot-secondary" style="background:${me.color_secondary || 'hsla(216,100%,50%,1)'}"></span>
									<span>${this.tr('secondary_label', 'Secondary')}</span>
								</button>
								<button class="color-swatch" id="swatch-tertiary" data-target="color-tertiary-input" aria-label="${this.tr('tertiary_label', 'Tertiary Accent')}">
									<span class="swatch-dot" id="swatch-dot-tertiary" style="background:${me.color_tertiary || 'hsla(239,84%,67%,1)'}"></span>
									<span>${this.tr('tertiary_label', 'Tertiary')}</span>
								</button>
							</div>
							<div class="hsla-picker" id="hsla-picker" role="dialog" aria-modal="true" aria-label="${this.tr('picker_title', 'HSLA Color Picker')}" hidden>
								<div class="picker-header">
									<span class="picker-title">${this.tr('picker_title', 'HSLA Color Picker')}</span>
									<span class="picker-preview" id="picker-preview" aria-hidden="true"></span>
								</div>
								<div class="picker-row">
									<span class="picker-row-label">${this.tr('color_hue', 'Hue')}</span>
									<input type="range" id="picker-h" min="0" max="360" step="1" class="picker-range picker-range-h" aria-label="${this.tr('color_hue', 'Hue')}">
									<input type="number" id="picker-h-num" min="0" max="360" step="1" class="picker-num" aria-label="${this.tr('color_hue', 'Hue')} value">
								</div>
								<div class="picker-row">
									<span class="picker-row-label">${this.tr('color_saturation', 'Saturation')}</span>
									<input type="range" id="picker-s" min="0" max="100" step="1" class="picker-range picker-range-s" aria-label="${this.tr('color_saturation', 'Saturation')}">
									<input type="number" id="picker-s-num" min="0" max="100" step="1" class="picker-num" aria-label="${this.tr('color_saturation', 'Saturation')} value">
								</div>
								<div class="picker-row">
									<span class="picker-row-label">${this.tr('color_lightness', 'Lightness')}</span>
									<input type="range" id="picker-l" min="0" max="100" step="1" class="picker-range picker-range-l" aria-label="${this.tr('color_lightness', 'Lightness')}">
									<input type="number" id="picker-l-num" min="0" max="100" step="1" class="picker-num" aria-label="${this.tr('color_lightness', 'Lightness')} value">
								</div>
								<div class="picker-row">
									<span class="picker-row-label">${this.tr('color_opacity', 'Opacity')}</span>
									<input type="range" id="picker-a" min="0" max="1" step="0.01" class="picker-range picker-range-a" aria-label="${this.tr('color_opacity', 'Opacity')}">
									<input type="number" id="picker-a-num" min="0" max="1" step="0.01" class="picker-num" aria-label="${this.tr('color_opacity', 'Opacity')} value">
								</div>
								<div class="picker-actions">
									<button class="oz-btn oz-btn-secondary" id="picker-cancel">${this.tr('color_cancel', 'Cancel')}</button>
									<button class="oz-btn oz-btn-primary" id="picker-apply">${this.tr('color_apply', 'Apply')}</button>
								</div>
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
			const cp = (this.shadowRoot?.querySelector('#color-primary-input') as HTMLInputElement)?.value || me.color_primary || 'hsla(196, 78%, 40%, 1)';
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

					applyColors();
				}
			});

			// HSLA picker setup
			let _pickerTarget: string | null = null;
			const picker = this.shadowRoot?.querySelector('#hsla-picker') as HTMLElement;
			const preview = this.shadowRoot?.querySelector('#picker-preview') as HTMLElement;
			const pH = this.shadowRoot?.querySelector('#picker-h') as HTMLInputElement;
			const pS = this.shadowRoot?.querySelector('#picker-s') as HTMLInputElement;
			const pL = this.shadowRoot?.querySelector('#picker-l') as HTMLInputElement;
			const pA = this.shadowRoot?.querySelector('#picker-a') as HTMLInputElement;
			const pHn = this.shadowRoot?.querySelector('#picker-h-num') as HTMLInputElement;
			const pSn = this.shadowRoot?.querySelector('#picker-s-num') as HTMLInputElement;
			const pLn = this.shadowRoot?.querySelector('#picker-l-num') as HTMLInputElement;
			const pAn = this.shadowRoot?.querySelector('#picker-a-num') as HTMLInputElement;

			const updatePickerPreview = () => {
				const h = pH.value, s = pS.value, l = pL.value, a = pA.value;
				const col = `hsla(${h}, ${s}%, ${l}%, ${a})`;
				if (preview) preview.style.background = col;
			};

			const syncSliderNum = (slider: HTMLInputElement, num: HTMLInputElement) => {
				slider.addEventListener('input', () => { num.value = slider.value; updatePickerPreview(); });
				num.addEventListener('input', () => { slider.value = num.value; updatePickerPreview(); });
			};
			syncSliderNum(pH, pHn);
			syncSliderNum(pS, pSn);
			syncSliderNum(pL, pLn);
			syncSliderNum(pA, pAn);

			const openPicker = (targetId: string) => {
				_pickerTarget = targetId;
				const hidden = this.shadowRoot?.querySelector(`#${targetId}`) as HTMLInputElement;
				const val = hidden?.value || 'hsla(173, 80%, 40%, 1)';
				const parsed = this.parseColor(val);
				pH.value = pHn.value = String(parsed.h);
				pS.value = pSn.value = String(parsed.s);
				pL.value = pLn.value = String(parsed.l);
				pA.value = pAn.value = String(parsed.a);
				updatePickerPreview();
				picker?.removeAttribute('hidden');
				pH.focus();
			};

			['swatch-primary', 'swatch-secondary', 'swatch-tertiary'].forEach(id => {
				const btn = this.shadowRoot?.querySelector(`#${id}`) as HTMLButtonElement;
				btn?.addEventListener('click', (e) => {
					e.preventDefault();
					const targetId = btn.getAttribute('data-target') || '';
					openPicker(targetId);
				});
			});

			this.shadowRoot?.querySelector('#picker-apply')?.addEventListener('click', () => {
				if (!_pickerTarget) return;
				const h = pH.value, s = pS.value, l = pL.value, a = pA.value;
				const col = `hsla(${h}, ${s}%, ${l}%, ${a})`;
				const hidden = this.shadowRoot?.querySelector(`#${_pickerTarget}`) as HTMLInputElement;
				if (hidden) hidden.value = col;
				// Update swatch dot
				const dotMap: Record<string, string> = {
					'color-primary-input': 'swatch-dot-primary',
					'color-secondary-input': 'swatch-dot-secondary',
					'color-tertiary-input': 'swatch-dot-tertiary',
				};
				const dot = this.shadowRoot?.querySelector(`#${dotMap[_pickerTarget]}`) as HTMLElement;
				if (dot) dot.style.background = col;
				picker?.setAttribute('hidden', '');
				_pickerTarget = null;
				applyColors();
			});

			this.shadowRoot?.querySelector('#picker-cancel')?.addEventListener('click', () => {
				picker?.setAttribute('hidden', '');
				_pickerTarget = null;
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
