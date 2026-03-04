import 'normalize.css'
import '../style.css'
import '../components/ProjectTree'
import '../components/MemorySearch'
import '../components/BriefingHistory'
import '../components/EmailRules'
import '../components/CircleManager'
import '../components/ChatPrompt'
import '../components/CreateProject'
import '../components/CalendarAgenda'
import '../components/CalendarManager'
import '../components/LifeOverview'
import '../components/WelcomeOnboarding'
import '../components/UserCard'
import '../components/HardwareMonitor'
import '../components/SoftwareStatus'
import '../components/SystemBenchmark'
import '../components/ZPersonality'

console.log('openZero Dashboard Initialized');

// ── Dashboard Auth Token Injection (C3) ──
// All /api/ requests automatically carry the bearer token stored in localStorage.
// On first load (or after token is cleared) a 401 from any API call prompts the user.

const AUTH_TOKEN_KEY = 'z_auth_token';

// On page load: if ?token= is in the URL, save it to localStorage and strip
// it from the address bar so it never appears in browser history or logs.
// This lets you bookmark http://open.zero/home?token=xxx once on any device.
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
	const token = window.prompt(
		'openZero: Enter your dashboard access token (set via DASHBOARD_TOKEN in .env):'
	) || '';
	if (token) {
		localStorage.setItem(AUTH_TOKEN_KEY, token);
	}
	return token;
}

// Patch window.fetch to inject Authorization header for all /api/ requests.
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
		}
	}

	const response = await _originalFetch(input, init);

	// On 401, prompt once for the token and offer to reload
	if (response.status === 401 && url.startsWith('/api/')) {
		const newToken = promptForToken();
		if (newToken) {
			window.location.reload();
		}
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

plankaAutoLogin();

// ── Theme Management ──
function hexToRgb(hex: string) {
	const h = hex.replace('#', '');
	const r = parseInt(h.slice(0, 2), 16);
	const g = parseInt(h.slice(2, 4), 16);
	const b = parseInt(h.slice(4, 6), 16);
	return `${r}, ${g}, ${b}`;
}

async function initTheme() {
	try {
		const res = await fetch('/api/dashboard/personality');
		if (res.ok) {
			const data = await res.json();
			const root = document.documentElement;
			const cache: Record<string, string> = {};
			if (data.color_primary) {
				root.style.setProperty('--accent-color', data.color_primary);
				root.style.setProperty('--accent-color-rgb', hexToRgb(data.color_primary));
				root.style.setProperty('--accent-glow', `rgba(${hexToRgb(data.color_primary)}, 0.4)`);
				cache.accent = data.color_primary;
			}
			if (data.color_secondary) {
				root.style.setProperty('--accent-secondary', data.color_secondary);
				root.style.setProperty('--accent-secondary-rgb', hexToRgb(data.color_secondary));
				cache.secondary = data.color_secondary;
			}
			if (data.color_tertiary) {
				root.style.setProperty('--accent-tertiary', data.color_tertiary);
				cache.tertiary = data.color_tertiary;
			}
			// Persist so the next page load applies the palette instantly
			// without waiting for the API round-trip (eliminates theme flash).
			if (Object.keys(cache).length) {
				localStorage.setItem('z_theme', JSON.stringify(cache));
			}
		}
	} catch (e) {
		console.warn('Theme initialization failed:', e);
	}
}
initTheme();

// ── Page loader dismissal ──
// DOMContentLoaded fires after all deferred module scripts have run and all
// custom elements in the document have been upgraded (connectedCallback done).
// Fading out here guarantees widgets are fully rendered before content appears.
document.addEventListener('DOMContentLoaded', () => {
	const loader = document.getElementById('page-loader');
	if (!loader) return;
	loader.classList.add('hidden');
	// Remove from DOM after the fade completes
	loader.addEventListener('transitionend', () => loader.remove(), { once: true });
});

// ── Header CTA Translations ──
// Fetches translations and applies localised labels, aria-label, and
// data-tooltip values to the three header action buttons.
async function initHeaderTranslations() {
	try {
		const res = await fetch('/api/dashboard/translations');
		if (!res.ok) return;
		const t: Record<string, string> = await res.json();

		const tr = (key: string, fallback: string) => t[key] || fallback;

		// Operator Board button
		const opBtn = document.getElementById('header-operator-btn');
		if (opBtn) {
			opBtn.setAttribute('aria-label', tr('aria_open_operator_board', 'Open Operator Board — centralized overview of tasks (opens in new tab)'));
			opBtn.setAttribute('data-tooltip', tr('header_operator_board_tooltip', 'Centralized overview of tasks across all your boards'));
			const opSpan = opBtn.querySelector('span');
			if (opSpan) opSpan.textContent = tr('header_operator_board_label', 'Operator Board');
		}

		// Projects button
		const projBtn = document.getElementById('header-projects-btn');
		if (projBtn) {
			projBtn.setAttribute('aria-label', tr('aria_open_projects', 'Open Projects board (opens in new tab)'));
			projBtn.setAttribute('data-tooltip', tr('header_projects_tooltip', 'Access individual project boards and spaces'));
			const projSpan = projBtn.querySelector('span');
			if (projSpan) projSpan.textContent = tr('header_projects_label', 'Projects');
		}

		// Calendar button
		const calBtn = document.getElementById('open-calendar-btn');
		if (calBtn) {
			calBtn.setAttribute('aria-label', tr('aria_open_calendar_btn', 'Open Calendar manager'));
			calBtn.setAttribute('data-tooltip', tr('header_calendar_tooltip', 'Open your integrated Google or Local Calendar'));
			const calSpan = calBtn.querySelector('span');
			if (calSpan) calSpan.textContent = tr('header_calendar_label', 'Calendar');
		}

		// Nav labels — apply translations to all [data-tr] spans across
		// sidebar-nav, top-marquee-nav, and mobile-nav-drawer.
		document.querySelectorAll<HTMLElement>('[data-tr]').forEach(el => {
			const key = el.getAttribute('data-tr')!;
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
	function setActive(sectionId: string) {
		allNavContainers.forEach(sel => {
			const container = document.querySelector(sel);
			if (!container) return;
			container.querySelectorAll<HTMLAnchorElement>('a[data-section]').forEach(a => {
				a.classList.toggle('active', a.dataset.section === sectionId);
			});
		});

		// Auto-scroll the marquee nav pill into view so the active item is visible
		const marqueeLink = document.querySelector<HTMLAnchorElement>(
			`.top-marquee-nav a[data-section="${sectionId}"]`
		);
		marqueeLink?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
	}

	const observer = new IntersectionObserver((entries) => {
		entries.forEach(entry => {
			if (entry.isIntersecting) {
				setActive(entry.target.id);
			}
		});
	}, {
		rootMargin: '-20% 0px -60% 0px',
		threshold: 0
	});

	sections.forEach(section => observer.observe(section));

	// Smooth scroll + highlight on any nav link click
	allNavLinks.forEach(link => {
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
	// Focus the close button for keyboard accessibility
	(drawer.querySelector('.mobile-nav-drawer-close') as HTMLButtonElement | null)?.focus();
}

function closeMobileDrawer() {
	const drawer = document.getElementById('mobile-nav-drawer');
	const toggle = document.getElementById('mobile-nav-open');
	if (!drawer || !drawerOpen) return;
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

// ── Header calendar button ──
document.getElementById('open-calendar-btn')?.addEventListener('click', () => {
	window.dispatchEvent(new CustomEvent('open-calendar'));
});

// Check for deep-link overlays
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('open') === 'calendar') {
	setTimeout(() => {
		window.dispatchEvent(new CustomEvent('open-calendar'));
	}, 500);
}
