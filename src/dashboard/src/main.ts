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

checkSystemStatus();
