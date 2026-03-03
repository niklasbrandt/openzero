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

// ── Sidebar Scroll Spy ──
function initScrollSpy() {
	const navLinks = document.querySelectorAll<HTMLAnchorElement>('.sidebar-nav a[data-section]');
	if (!navLinks.length) return;

	const sectionIds = Array.from(navLinks).map(a => a.dataset.section!);
	const sections = sectionIds.map(id => document.getElementById(id)).filter(Boolean) as HTMLElement[];

	const observer = new IntersectionObserver((entries) => {
		entries.forEach(entry => {
			const link = document.querySelector(`.sidebar-nav a[data-section="${entry.target.id}"]`);
			if (entry.isIntersecting) {
				navLinks.forEach(a => a.classList.remove('active'));
				link?.classList.add('active');
			}
		});
	}, {
		rootMargin: '-20% 0px -60% 0px',
		threshold: 0
	});

	sections.forEach(section => observer.observe(section));

	// Smooth scroll on click
	navLinks.forEach(link => {
		link.addEventListener('click', (e) => {
			e.preventDefault();
			const id = link.dataset.section!;
			document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
		});
	});
}

initScrollSpy();

// Check for deep-link overlays
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('open') === 'calendar') {
	setTimeout(() => {
		window.dispatchEvent(new CustomEvent('open-calendar'));
	}, 500);
}
