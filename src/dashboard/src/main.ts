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

console.log('🚀 openZero Dashboard Initialized');

// Fetch system status and LLM info to display in the header
// This implicitly calls the backend to warm up the local LLM
async function checkSystemStatus() {
	const modelEl = document.getElementById('status-model');
	const memEl = document.getElementById('status-memory');
	const identEl = document.getElementById('status-identity');
	const latEl = document.getElementById('status-latency');

	const startTime = performance.now();

	try {
		const res = await fetch('/api/dashboard/system');
		if (res.ok) {
			const data = await res.json();
			const latency = Math.round(performance.now() - startTime);

			if (modelEl) modelEl.innerText = `Core: ${data.llm_model}`;
			if (memEl) memEl.innerText = `Memory: ${data.memory_points} points`;
			if (identEl) identEl.innerText = `Identity: ${data.identity_active ? 'Active' : 'Unset'}`;
			if (latEl) latEl.innerText = `Ping: ${latency}ms`;
		} else {
			if (modelEl) modelEl.innerText = 'System Offline';
		}
	} catch (error) {
		if (modelEl) modelEl.innerText = 'Connection Lost';
		console.warn('Could not reach backend system endpoint.', error);
	}
}

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

checkSystemStatus();
setInterval(checkSystemStatus, 10000); // Pulse every 10s
plankaAutoLogin();

// Check for deep-link overlays
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('open') === 'calendar') {
	setTimeout(() => {
		window.dispatchEvent(new CustomEvent('open-calendar'));
	}, 500);
}
