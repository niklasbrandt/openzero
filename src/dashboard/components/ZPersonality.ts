export class ZPersonality extends HTMLElement {
    private calibration: any = null;
    private protocols: any[] = [];
    private activeTab: 'calibration' | 'protocols' = 'calibration';
    private isLoading = true;

    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
    }

    connectedCallback() {
        this.render();
        this.fetchData();
    }

    async fetchData() {
        this.isLoading = true;
        try {
            const [calRes, protRes] = await Promise.all([
                fetch('/api/dashboard/calibration'),
                fetch('/api/dashboard/protocols')
            ]);
            if (calRes.ok) this.calibration = await calRes.json();
            if (protRes.ok) {
                const data = await protRes.json();
                this.protocols = data.tools || [];
            }
        } catch (e) {
            console.error('Failed to fetch personality data', e);
        } finally {
            this.isLoading = false;
            this.render();
        }
    }

    render() {
        if (!this.shadowRoot) return;

        const cal = this.calibration;
        const prot = this.protocols;

        this.shadowRoot.innerHTML = `
			<style>
				:host { display: block; height: 100%; font-family: 'Inter', system-ui, sans-serif; }
				.card { height: 100%; display: flex; flex-direction: column; gap: 1.25rem; color: #fff; }
				
				.header { display: flex; justify-content: space-between; align-items: center; }
				h2 { margin: 0; font-size: 1.1rem; display: flex; align-items: center; gap: 0.75rem; color: #fff; font-weight: bold; }
				.icon { 
					width: 32px; height: 32px; 
					background: linear-gradient(135deg, #14B8A6, #0066FF); 
					border-radius: 50%; display: flex; align-items: center; justify-content: center;
					box-shadow: 0 0 20px rgba(20, 184, 166, 0.3);
					font-weight: 800; font-size: 0.9rem;
				}

				.tabs { display: flex; gap: 1rem; border-bottom: 1px solid rgba(255,255,255,0.05); }
				.tab { 
					padding: 0.5rem 0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; 
					color: rgba(255,255,255,0.4); cursor: pointer; border-bottom: 2px solid transparent;
					transition: all 0.2s;
				}
				.tab.active { color: #14B8A6; border-color: #14B8A6; }

				.content { flex: 1; overflow-y: auto; padding-right: 4px; }
				.content::-webkit-scrollbar { width: 4px; }
				.content::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }

				.cal-box { 
					background: rgba(20, 184, 166, 0.05); border: 1px solid rgba(20, 184, 166, 0.1);
					padding: 1.25rem; border-radius: 1rem; margin-top: 0.5rem;
					animation: fadeIn 0.4s ease-out;
				}
				.cal-name { color: #14B8A6; font-weight: 700; font-size: 0.9rem; margin-bottom: 0.5rem; display: block; }
				.cal-prompt { font-size: 0.85rem; line-height: 1.6; color: rgba(255,255,255,0.8); }

				.prot-list { display: flex; flex-direction: column; gap: 0.75rem; margin-top: 0.5rem; }
				.prot-item { 
					background: rgba(255, 255, 255, 0.03); padding: 0.75rem 1rem; border-radius: 0.75rem;
					border-left: 3px solid #0066FF; animation: slideIn 0.3s ease-out backwards;
				}
				.prot-name { font-size: 0.8rem; font-weight: 700; letter-spacing: 0.02em; display: block; margin-bottom: 0.25rem; }
				.prot-desc { font-size: 0.75rem; color: rgba(255,255,255,0.5); line-height: 1.4; }

				@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
				@keyframes slideIn { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }

				.status-bar { 
					display: flex; align-items: center; gap: 0.5rem; font-size: 0.65rem; 
					color: rgba(255,255,255,0.3); margin-top: auto; padding-top: 0.5rem;
				}
				.pulse { width: 6px; height: 6px; background: #14B8A6; border-radius: 50%; box-shadow: 0 0 8px #14B8A6; }

				.empty { text-align: center; padding: 2rem; color: rgba(255,255,255,0.2); font-size: 0.85rem; font-style: italic; }
			</style>

			<div class="card">
				<div class="header">
					<h2><div class="icon">Z</div> ${this.isLoading ? 'Syncing...' : 'Agent Personality'}</h2>
				</div>

				<div class="tabs">
					<div class="tab ${this.activeTab === 'calibration' ? 'active' : ''}" id="tab-cal">Calibration</div>
					<div class="tab ${this.activeTab === 'protocols' ? 'active' : ''}" id="tab-prot">Protocols</div>
				</div>

				<div class="content">
					${this.isLoading ? '<div class="empty">Aligning neural paths...</div>' : ''}
					
					${!this.isLoading && this.activeTab === 'calibration' ? `
						<div class="cal-box">
							<span class="cal-name">${cal?.name || 'Daily Focus'}</span>
							<div class="cal-prompt">${cal?.prompt || 'No calibration needed today. You are perfectly aligned.'}</div>
						</div>
						<div style="margin-top: 1.5rem; font-size: 0.75rem; color: rgba(255,255,255,0.4); font-style: italic; line-height: 1.5;">
							"I am not just code. I am a reflection of your trajectory. These exercises ensure we remain in sync."
						</div>
					` : ''}

					${!this.isLoading && this.activeTab === 'protocols' ? `
						<div class="prot-list">
							${prot.map((p: any, i: number) => `
								<div class="prot-item" style="animation-delay: ${i * 0.05}s">
									<span class="prot-name">${p.name}</span>
									<span class="prot-desc">${p.description}</span>
								</div>
							`).join('')}
							${prot.length === 0 ? '<div class="empty">No active strategic protocols.</div>' : ''}
						</div>
					` : ''}
				</div>

				<div class="status-bar">
					<div class="pulse"></div>
					<span>Neural Core Online</span>
					<span style="margin-left: auto;">V ${new Date().getFullYear()}.${new Date().getMonth() + 1}</span>
				</div>
			</div>
		`;

        this.shadowRoot.querySelector('#tab-cal')?.addEventListener('click', () => {
            this.activeTab = 'calibration';
            this.render();
        });
        this.shadowRoot.querySelector('#tab-prot')?.addEventListener('click', () => {
            this.activeTab = 'protocols';
            this.render();
        });
    }
}

customElements.define('z-personality', ZPersonality);
