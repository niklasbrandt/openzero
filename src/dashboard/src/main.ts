import 'normalize.css'
import '../style.css'

// ── Critical components: loaded synchronously so the above-fold UI paints
//    without a flash of unregistered custom elements.
import '../components/ChatPrompt'
import '../components/ProjectTree'
import '../components/UserCard'

// ── Lazy components: deferred until the browser is idle so the main thread
//    is free for first paint (reduces TBT / long-tasks significantly).
function loadLazyComponents(): void {
	import('../components/MemorySearch')
	import('../components/BriefingHistory')
	import('../components/EmailRules')
	import('../components/CircleManager')
	import('../components/CreateProject')
	import('../components/CalendarAgenda')
	import('../components/CalendarManager')
	import('../components/WelcomeOnboarding')
	import('../components/DiagnosticsWidget')
	import('../components/ZProtocols')
}

if ('requestIdleCallback' in window) {
	(window as Window & typeof globalThis).requestIdleCallback(loadLazyComponents, { timeout: 3000 });
} else {
	setTimeout(loadLazyComponents, 200);
}

console.log('openZero Dashboard Initialized');

// ── Dashboard Auth Token Injection (C3) ──
// All /api/ requests automatically carry the bearer token stored in localStorage.
// On first load (or after token is cleared) a 401 from any API call prompts the user.

const AUTH_TOKEN_KEY = 'z_auth_token';

// On page load: if ?token= is in the URL, save it to localStorage and strip
// it from the address bar so it never appears in browser history or logs.
// This lets you bookmark http://open.zero/dashboard?token=xxx once on any device.
(function captureTokenFromUrl() {
	const params = new URLSearchParams(window.location.search);
	const urlToken = params.get('token');
	if (urlToken) {
		localStorage.setItem(AUTH_TOKEN_KEY, urlToken);
		params.delete('token');
		const newSearch = params.toString();
		const newUrl = window.location.pathname + (newSearch ? '?' + newSearch : '');
		window.history.replaceState({}, '', newUrl);
	}
})();

function getAuthToken(): string {
	// localStorage takes priority
	const localToken = localStorage.getItem(AUTH_TOKEN_KEY);
	if (localToken) return localToken;
	// Fall back to cookie set by /api/auth redirect
	// (iOS SFSafariViewController and Android Chrome Custom Tab share cookies
	// with the system browser, but NOT localStorage — cookie is the reliable path)
	const match = document.cookie.match(/(?:^|;\s*)z_auth_token=([^;]+)/);
	if (match) {
		const cookieToken = decodeURIComponent(match[1]);
		localStorage.setItem(AUTH_TOKEN_KEY, cookieToken); // migrate to localStorage
		return cookieToken;
	}
	return '';
}

function promptForToken(): string {
	// navigator.webdriver is true in automated environments (Lighthouse,
	// Puppeteer, Playwright). The blocking window.prompt() has no human to
	// answer it and would hang the main thread forever, causing NO_FCP.
	if (navigator.webdriver) return '';
	const token = window.prompt(
		'openZero: Enter your dashboard access token (set via DASHBOARD_TOKEN in .env):'
	) || '';
	if (token) {
		localStorage.setItem(AUTH_TOKEN_KEY, token);
	}
	return token;
}

// Patch window.fetch to inject Authorization header for all /api/ requests.
// When no token is stored, API calls are short-circuited with a synthetic
// 401 response -- this avoids ~14 network round-trips that would all fail
// and prevents the "network busy" state that blocks Lighthouse scoring.
let _authPromptPending = false;
const _originalFetch = window.fetch.bind(window);
window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
	const url = typeof input === 'string' ? input : input instanceof Request ? input.url : input.toString();

	if (url.startsWith('/api/')) {
		const token = getAuthToken();
		if (token) {
			init = init ?? {};
			init.headers = {
				...(init.headers instanceof Headers
					? Object.fromEntries((init.headers as Headers).entries())
					: (init.headers as Record<string, string> ?? {})),
				'Authorization': `Bearer ${token}`,
			};
		} else {
			// No token stored — every /api/ call will 401 anyway.
			// Return a synthetic 401 without touching the network.
			if (!_authPromptPending) {
				_authPromptPending = true;
				setTimeout(() => {
					const newToken = promptForToken();
					_authPromptPending = false;
					if (newToken) {
						window.location.reload();
					}
				}, 200);
			}
			return new Response(JSON.stringify({ error: 'Unauthorized' }), {
				status: 401,
				headers: { 'Content-Type': 'application/json' },
			});
		}
	}

	const response = await _originalFetch(input, init);

	// Handle expired/invalid tokens -- the server returned 401 despite us
	// sending a token.  Prompt once so the user can re-enter.
	if (response.status === 401 && url.startsWith('/api/') && !_authPromptPending) {
		_authPromptPending = true;
		setTimeout(() => {
			const newToken = promptForToken();
			_authPromptPending = false;
			if (newToken) {
				window.location.reload();
			}
		}, 200);
	}

	return response;
};

// Background auto-login for Planka
// This ensures that when the user opens Planka (separately or via link), 
// they are already authenticated via the dashboard session.
async function plankaAutoLogin() {
	console.log('🔐 Initializing Planka background login...');
	try {
		// Trigger the redirect bridge in a hidden iframe.
		// The bridge sets the httpOnlyToken and accessToken cookies.
		// Iframes cannot send custom headers, so the token is appended as a query param.
		const iframe = document.createElement('iframe');
		const token = getAuthToken();
		const plankaUrl = `/api/dashboard/planka-redirect?background=true${token ? `&token=${encodeURIComponent(token)}` : ''}`;
		iframe.src = plankaUrl;
		iframe.setAttribute('style', 'display:none; width:0; height:0; border:0; position:absolute; visibility:hidden;');
		iframe.setAttribute('aria-hidden', 'true');
		document.body.appendChild(iframe);

		// Remove after 10 seconds to keep the DOM clean
		// after the redirect cycle has likely finished.
		setTimeout(() => {
			if (document.body.contains(iframe)) {
				document.body.removeChild(iframe);
				console.log('✅ Planka background login cycle complete');
			}
		}, 10000);
	} catch (error) {
		console.warn('Planka background login failed:', error);
	}
}

// Defer Planka SSO until after the page load event so the hidden iframe
// (and its nested Planka React app iframe) cannot block the main page's
// load event.  This is purely background work — no visible impact.
if (document.readyState === 'complete') {
	setTimeout(plankaAutoLogin, 2000);
} else {
	window.addEventListener('load', () => setTimeout(plankaAutoLogin, 2000), { once: true });
}

// ── Theme Management ──
function parseColor(color: string): { h: number, s: number, l: number, a: number } {
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

function hslToRgb(h: number, s: number, l: number): string {
	s /= 100; l /= 100;
	const k = (n: number) => (n + h / 30) % 12;
	const a = s * Math.min(l, 1 - l);
	const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
	return `${Math.round(f(0) * 255)}, ${Math.round(f(8) * 255)}, ${Math.round(f(4) * 255)}`;
}

// Resolved once the palette API call settles (success or failure).
// Used to gate the page-loader so content is never revealed mid-flash.

async function initTheme() {
	try {
		const res = await fetch('/api/dashboard/personality');
		if (res.ok) {
			const data = await res.json();
			const root = document.documentElement;
			// Suppress transitions so CSS var updates paint in one frame,
			// with no visible colour transition even if the page is already
			// partially visible behind a fading loader.
			root.classList.add('no-transition');
			const cache: Record<string, string> = {};

			const applyColor = (prefix: string, color: string) => {
				const { h, s, l, a } = parseColor(color);
				const rgb = hslToRgb(h, s, l);
				root.style.setProperty(`--${prefix}-h`, h.toString());
				root.style.setProperty(`--${prefix}-s`, `${s}%`);
				root.style.setProperty(`--${prefix}-l`, `${l}%`);
				root.style.setProperty(`--${prefix}-rgb`, rgb);
				root.style.setProperty(`--${prefix}`, `hsla(${h}, ${s}%, ${l}%, ${a})`);

				// Legacy/Direct mappings
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

			if (data.color_primary) {
				applyColor('accent-primary', data.color_primary);
				cache.accent = data.color_primary;
			}
			if (data.color_secondary) {
				applyColor('accent-secondary', data.color_secondary);
				cache.secondary = data.color_secondary;
			}
			if (data.color_tertiary) {
				applyColor('accent-tertiary', data.color_tertiary);
				cache.tertiary = data.color_tertiary;
			}

			// Persist so the next page load applies the palette instantly
			if (Object.keys(cache).length) {
				localStorage.setItem('z_theme', JSON.stringify(cache));
			}
			// Re-enable transitions after the browser has committed the paint.
			requestAnimationFrame(() => {
				requestAnimationFrame(() => {
					root.classList.remove('no-transition');
				});
			});
		}
	} catch (e) {
		console.warn('Theme initialization failed:', e);
	}
}
const themeReady = initTheme();

// ── Centralized Translation Fetch ──
// Fetches translations ONCE and exposes them to all components via
// window.__z_translations. Components read from this cache in their
// loadTranslations() instead of making independent /api/ calls.
// This eliminates ~14 duplicate HTTP requests and the staggered
// "popcorn" re-render effect where widgets pop in one by one.
declare global {
	interface Window {
		__z_translations: Record<string, string> | null;
		__z_translations_ready: Promise<void>;
		__z_lang: string;
	}
}
window.__z_translations = null;
window.__z_lang = 'en';

const translationsReady = (async () => {
	try {
		const res = await fetch('/api/dashboard/translations');
		if (res.ok) {
			const data = await res.json();
			window.__z_translations = data.keys;
			window.__z_lang = data.lang || 'en';
			// Sync the <html> lang attribute for screen readers and SEO
			document.documentElement.lang = window.__z_lang;
		}
	} catch (_) { /* components fall back to English defaults */ }
})();
window.__z_translations_ready = translationsReady;

// ── Page loader dismissal ──
// Wait for DOMContentLoaded, theme palette, translations, AND critical
// above-the-fold Web Components to be defined before revealing content.
// A 2.5 s hard timeout prevents a slow API from blocking the page
// indefinitely. The :not(:defined) CSS hides components anyway, so even
// if the loader fades early there is no visible flash.
// The double-rAF before removing the hidden class ensures the browser
// commits the final colour paint first.
function dismissLoader() {
	const loader = document.getElementById('page-loader');
	if (!loader) return;
	requestAnimationFrame(() => {
		requestAnimationFrame(() => {
			loader.classList.add('hidden');
			loader.addEventListener('transitionend', () => loader.remove(), { once: true });
			// Safety net: remove after transition duration even if event misfires
			setTimeout(() => loader.remove(), 300);
		});
	});
}

const domReady = new Promise<void>(resolve => {
	if (document.readyState !== 'loading') resolve();
	else document.addEventListener('DOMContentLoaded', () => resolve(), { once: true });
});

// Wait for critical above-the-fold components to register their Custom
// Element definition so the :not(:defined) -> :defined CSS transition
// happens behind the loader, not in front of the user's eyes.
const criticalComponents = Promise.all([
	customElements.whenDefined('chat-prompt'),
	customElements.whenDefined('project-tree'),
	customElements.whenDefined('user-card'),
]);

// Race ALL readiness signals against a 2.5 s timeout so a slow backend
// never leaves the loader up indefinitely.
const loaderTimeout = new Promise<void>(resolve => setTimeout(resolve, 2500));

Promise.all([
	domReady,
	Promise.race([
		Promise.all([themeReady, translationsReady, criticalComponents]),
		loaderTimeout,
	]),
]).then(dismissLoader);

// ── Header CTA Translations ──
// Applies localised labels, aria-label, and data-tooltip values 
// to structural elements using the global translations cache.
async function initHeaderTranslations() {
	try {
		await window.__z_translations_ready;
		const t = window.__z_translations;
		if (!t) return;



		// Nav labels — apply translations to all [data-tr] spans across
		// sidebar-nav, top-marquee-nav, and mobile-nav-drawer.
		document.querySelectorAll<HTMLElement>('[data-tr]').forEach(el => {
			const key = el.getAttribute('data-tr')!;
			const localised = t[key];
			if (localised) el.textContent = localised;
		});

		// Sync aria-label on nav links from their child [data-tr] span text.
		// This ensures screen readers announce the translated section name.
		document.querySelectorAll<HTMLAnchorElement>('a[data-section]').forEach(a => {
			const span = a.querySelector<HTMLElement>('[data-tr]');
			if (span && span.textContent) {
				a.setAttribute('aria-label', span.textContent);
			}
		});

		// Translate aria-label on structural elements via [data-tr-aria].
		document.querySelectorAll<HTMLElement>('[data-tr-aria]').forEach(el => {
			const key = el.getAttribute('data-tr-aria')!;
			const localised = t[key];
			if (localised) el.setAttribute('aria-label', localised);
		});

		// Translate visible text on structural elements via [data-tr-text].
		document.querySelectorAll<HTMLElement>('[data-tr-text]').forEach(el => {
			const key = el.getAttribute('data-tr-text')!;
			const localised = t[key];
			if (localised) el.textContent = localised;
		});
	} catch (e) {
		console.warn('Header translations init failed:', e);
	}
}
initHeaderTranslations();

// ── Sidebar + Marquee + Drawer Scroll Spy ──
function initScrollSpy() {
	const allNavContainers = [
		'.sidebar-nav',
		'.top-marquee-nav',
		'.mobile-nav-drawer',
	];

	const allNavLinks = document.querySelectorAll<HTMLAnchorElement>(
		'[data-section]'
	);
	if (!allNavLinks.length) return;

	const sectionIds = Array.from(
		new Set(Array.from(allNavLinks).map(a => a.dataset.section!))
	);
	const sections = sectionIds
		.map(id => document.getElementById(id))
		.filter(Boolean) as HTMLElement[];

	// Mark the active link in ALL nav containers simultaneously
	let marqueeScrollTimer: ReturnType<typeof setTimeout> | null = null;
	function setActive(sectionId: string) {
		allNavContainers.forEach(sel => {
			const container = document.querySelector(sel);
			if (!container) return;
			container.querySelectorAll<HTMLAnchorElement>('a[data-section]').forEach(a => {
				a.classList.toggle('active', a.dataset.section === sectionId);
			});
		});

		// Defer marquee scrollIntoView so it never runs during the user's active
		// scroll — triggering scrollIntoView mid-scroll fights the browser's
		// momentum and causes visible jank. Fire 150 ms after the last section
		// change so it only runs once the scroll has likely settled.
		if (marqueeScrollTimer !== null) clearTimeout(marqueeScrollTimer);
		marqueeScrollTimer = setTimeout(() => {
			const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
			const marqueeLink = document.querySelector<HTMLAnchorElement>(
				`.top-marquee-nav a[data-section="${sectionId}"]`
			);
			marqueeLink?.scrollIntoView({
				behavior: prefersReducedMotion ? 'instant' : 'smooth',
				block: 'nearest',
				inline: 'center',
			});
			marqueeScrollTimer = null;
		}, 150);
	}

	// Scroll-spy: pick the section whose visual centre is closest to
	// the viewport centre band (35%-65% of viewport height). Among
	// sections sharing the same vertical band, the one closest to the
	// horizontal centre wins — important for column-count masonry layout
	// where two cards sit side-by-side at the same Y position.
	let currentActive = '';
	let rafPending = false;

	function pickActive() {
		const vh = window.innerHeight;
		const vw = window.innerWidth;
		const bandTop = vh * 0.35;
		const bandBot = vh * 0.65;
		const vcx = vw / 2;
		const vcy = vh / 2;

		let bestId = '';
		let bestDist = Infinity;

		for (const sec of sections) {
			const r = sec.getBoundingClientRect();
			// Section must overlap the centre band vertically
			if (r.bottom < bandTop || r.top > bandBot) continue;

			const cx = (r.left + r.right) / 2;
			const cy = (r.top + r.bottom) / 2;
			// Euclidean distance from section centre to viewport centre;
			// horizontal distance acts as natural tiebreaker for same-row cards
			const dist = Math.hypot(cx - vcx, cy - vcy);
			if (dist < bestDist) {
				bestDist = dist;
				bestId = sec.id;
			}
		}

		// Fallback: nothing in the centre band — pick nearest to viewport centre
		if (!bestId) {
			for (const sec of sections) {
				const r = sec.getBoundingClientRect();
				const cy = (r.top + r.bottom) / 2;
				const dist = Math.abs(cy - vcy);
				if (dist < bestDist) {
					bestDist = dist;
					bestId = sec.id;
				}
			}
		}

		if (bestId && bestId !== currentActive) {
			currentActive = bestId;
			setActive(bestId);
		}
		rafPending = false;
	}

	function onScroll() {
		if (!rafPending) {
			rafPending = true;
			requestAnimationFrame(pickActive);
		}
	}

	window.addEventListener('scroll', onScroll, { passive: true });
	// Initial highlight on page load
	pickActive();

	// Smooth scroll + highlight on any nav link click
	allNavLinks.forEach((link, idx) => {
		link.addEventListener('click', (e) => {
			e.preventDefault();
			const id = link.dataset.section!;
			const el = document.getElementById(id);
			if (el) {
				el.scrollIntoView({ behavior: 'smooth', block: 'start' });
				el.classList.add('widget-highlight');
				setTimeout(() => el.classList.remove('widget-highlight'), 1500);
			}
			// Close drawer if a drawer link was clicked
			closeMobileDrawer();
		});

		// Arrow key navigation (roving focus support for landmarks)
		link.addEventListener('keydown', (e) => {
			const { key } = e;
			let target = -1;

			if (key === 'ArrowDown' || key === 'ArrowRight') {
				e.preventDefault();
				target = (idx + 1) % allNavLinks.length;
			} else if (key === 'ArrowUp' || key === 'ArrowLeft') {
				e.preventDefault();
				target = (idx - 1 + allNavLinks.length) % allNavLinks.length;
			} else if (key === 'Home') {
				e.preventDefault();
				target = 0;
			} else if (key === 'End') {
				e.preventDefault();
				target = allNavLinks.length - 1;
			}

			if (target !== -1) {
				// We map indices differently across 3 navs, so find the target 
				// by section index within the SAME container.
				const container = link.closest('nav, .mobile-nav-drawer');
				if (container) {
					const linksInContainer = Array.from(container.querySelectorAll<HTMLAnchorElement>('a[data-section]'));
					const currentInC = linksInContainer.indexOf(link);
					let nextInC = -1;
					if (key === 'ArrowDown' || key === 'ArrowRight') nextInC = (currentInC + 1) % linksInContainer.length;
					else if (key === 'ArrowUp' || key === 'ArrowLeft') nextInC = (currentInC - 1 + linksInContainer.length) % linksInContainer.length;
					else if (key === 'Home') nextInC = 0;
					else if (key === 'End') nextInC = linksInContainer.length - 1;

					if (nextInC !== -1) linksInContainer[nextInC]?.focus();
				}
			}
		});
	});
}

// ── Mobile drawer open / close ──
let drawerOpen = false;

function openMobileDrawer() {
	const drawer = document.getElementById('mobile-nav-drawer');
	const toggle = document.getElementById('mobile-nav-open');
	if (!drawer) return;
	drawerOpen = true;
	drawer.classList.add('open');
	toggle?.setAttribute('aria-expanded', 'true');
	document.body.style.overflow = 'hidden';

	// Focus trap: identify first and last focusable elements
	const focusable = drawer.querySelectorAll<HTMLElement>(
		'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
	);
	const first = focusable[0];
	const last = focusable[focusable.length - 1];

	function handleTrap(e: KeyboardEvent) {
		if (e.key !== 'Tab' || !drawerOpen) return;
		if (e.shiftKey) { // Shift + Tab
			if (document.activeElement === first) {
				e.preventDefault();
				last?.focus();
			}
		} else { // Tab
			if (document.activeElement === last) {
				e.preventDefault();
				first?.focus();
			}
		}
	}

	drawer.addEventListener('keydown', handleTrap as EventListener);
	// Store ref to remove later if needed, though we reload/re-add on open
	(drawer as any)._trapHandler = handleTrap;

	// Focus the close button for keyboard accessibility
	(drawer.querySelector('.mobile-nav-drawer-close') as HTMLButtonElement | null)?.focus();
}

function closeMobileDrawer() {
	const drawer = document.getElementById('mobile-nav-drawer');
	const toggle = document.getElementById('mobile-nav-open');
	if (!drawer || !drawerOpen) return;

	if ((drawer as any)._trapHandler) {
		drawer.removeEventListener('keydown', (drawer as any)._trapHandler);
	}

	drawerOpen = false;
	drawer.classList.remove('open');
	toggle?.setAttribute('aria-expanded', 'false');
	document.body.style.overflow = '';
	toggle?.focus();
}

function initMobileNav() {
	document.getElementById('mobile-nav-open')?.addEventListener('click', openMobileDrawer);
	document.getElementById('mobile-nav-close')?.addEventListener('click', closeMobileDrawer);

	// Close on Escape key
	document.addEventListener('keydown', (e) => {
		if (e.key === 'Escape' && drawerOpen) closeMobileDrawer();
	});
}

initScrollSpy();
initMobileNav();

// Check for deep-link overlays
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('open') === 'calendar') {
	setTimeout(() => {
		window.dispatchEvent(new CustomEvent('open-calendar'));
	}, 500);
}
