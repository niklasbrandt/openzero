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

console.log('🚀 OpenZero Dashboard Initialized');

// Fetch system status and LLM info to display in the header
// This implicitly calls the backend to warm up the local LLM
async function checkSystemStatus() {
    const badge = document.getElementById('status-badge');
    if (!badge) return;

    try {
        const res = await fetch('/api/dashboard/system');
        if (res.ok) {
            const data = await res.json();
            // E.g., "System Online • llama3.2:3b"
            badge.innerText = `System Online • ${data.llm_model}`;
        } else {
            badge.innerText = 'System Offline';
            badge.classList.remove('status-online');
            badge.style.background = 'rgba(239, 68, 68, 0.15)';
            badge.style.color = '#ef4444';
        }
    } catch (error) {
        badge.innerText = 'System Offline';
        badge.classList.remove('status-online');
        badge.style.background = 'rgba(239, 68, 68, 0.15)';
        badge.style.color = '#ef4444';
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
        // IMPORTANT: Must load from port 1337 to set LocalStorage for that origin
        const plankaUrl = `${window.location.protocol}//${window.location.hostname}:1337/api/dashboard/planka-redirect?background=true`;
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
plankaAutoLogin();
