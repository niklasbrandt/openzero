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

console.log('🚀 openZero Dashboard Initialized');

// Background auto-login for Planka
// This ensures that when the user opens Planka (separately or via link), 
// they are already authenticated via the dashboard session.
async function plankaAutoLogin() {
	console.log('🔐 Initializing Planka background login...');
	try {
		// Trigger the redirect bridge in a hidden iframe.
		// The bridge sets the httpOnlyToken and accessToken cookies.
		const iframe = document.createElement('iframe');
		const plankaUrl = `/api/dashboard/planka-redirect?background=true`;
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
			if (data.color_primary) {
				root.style.setProperty('--accent-color', data.color_primary);
				root.style.setProperty('--accent-color-rgb', hexToRgb(data.color_primary));
			}
			if (data.color_secondary) root.style.setProperty('--accent-secondary', data.color_secondary);
			if (data.color_tertiary) root.style.setProperty('--accent-tertiary', data.color_tertiary);
		}
	} catch (e) {
		console.warn('Theme initialization failed:', e);
	}
}
initTheme();

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
