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

// Check for deep-link overlays
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('open') === 'calendar') {
	setTimeout(() => {
		window.dispatchEvent(new CustomEvent('open-calendar'));
	}, 500);
}
