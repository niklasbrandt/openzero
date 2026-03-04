import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';

export class ProjectTree extends HTMLElement {
	private t: Record<string, string> = {};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.loadTranslations().then(() => {
			this.render();
			this.fetchData();
			this.setupToggle();
		});
		window.addEventListener('refresh-data', (e: any) => {
			if (e.detail && e.detail.actions && (e.detail.actions.includes('project') || e.detail.actions.includes('board'))) {
				this.fetchData();
			}
		});
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => {
				this.render();
				this.setupToggle();
			});
		});
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

	private setupToggle() {
		this.shadowRoot?.querySelector('#new-project-btn')?.addEventListener('click', () => {
			// Toggle the sibling <create-project> element in the light DOM
			const createProject = this.parentElement?.querySelector('create-project') as HTMLElement | null;
			if (createProject) {
				const isOpen = createProject.getAttribute('data-open') === 'true';
				createProject.setAttribute('data-open', isOpen ? 'false' : 'true');

				const btn = this.shadowRoot?.querySelector('#new-project-btn');
				if (btn) {
					btn.textContent = isOpen ? this.tr('new_board', '+ New Board') : `\u2212 ${this.tr('cancel', 'Cancel')}`;
					btn.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
					btn.setAttribute('aria-label', isOpen ? this.tr('aria_add_project', 'Add a new project board') : this.tr('cancel_add_board', 'Cancel adding new board'));
				}
			}
		});
	}

	async fetchData() {
		try {
			const response = await fetch('/api/dashboard/projects');
			if (!response.ok) throw new Error('API error');
			const text = await response.text();
			if (!text) throw new Error('Empty response');
			const data = JSON.parse(text);
			if (data.tree) {
				this.updateTree(data.tree);
			} else {
				this.showEmpty();
			}
		} catch (e) {
			this.showEmpty();
		}
	}

	showEmpty() {
		const pre = this.shadowRoot?.querySelector('pre');
		if (pre) {
			pre.textContent = this.tr('no_boards', 'No boards found.');
			pre.style.color = 'rgba(255, 255, 255, 0.3)';
			pre.style.fontFamily = "'Inter', system-ui, sans-serif";
			pre.style.textAlign = 'center';
			pre.style.padding = '2rem';
		}
	}

	updateTree(treeData: string) {
		const pre = this.shadowRoot?.querySelector('pre');
		if (pre) {
			pre.innerHTML = treeData;
		}
	}

	render() {
		if (this.shadowRoot) {
			this.shadowRoot.innerHTML = `
				<style>
					${ACCESSIBILITY_STYLES}
					${SECTION_HEADER_STYLES}
					/* Override icon gradient for boards */
					h2 .h-icon {
						background: linear-gradient(135deg, var(--accent-color, hsla(173, 80%, 40%, 1)) 0%, hsla(216, 100%, 50%, 1) 100%);
					}
					:host { display: block; }
					.header {
						display: flex;
						justify-content: space-between;
						align-items: center;
						margin-bottom: 1rem;
					}
					
					#new-project-btn {
						background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.12);
						color: var(--accent-color, hsla(173, 80%, 40%, 1));
						border: 1px solid rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
						padding: 0.4rem 1rem;
						border-radius: var(--radius-md, 0.6rem);
						font-size: 0.8rem;
						font-weight: 600;
						font-family: 'Inter', system-ui, sans-serif;
						cursor: pointer;
						transition: all var(--duration-base, 0.25s) ease;
						letter-spacing: 0.02em;
					}
					#new-project-btn:hover {
						background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.22);
						border-color: rgba(var(--accent-color-rgb, 20, 184, 166), 0.4);
					}
					pre {
						background: rgba(0, 0, 0, 0.3);
						padding: 1.5rem;
						border-radius: var(--radius-lg, 1rem);
						font-family: var(--font-mono, 'Fira Code', monospace);
						font-size: 0.95rem;
						line-height: 1.6;
						color: var(--accent-color, hsla(173, 80%, 40%, 1));
						border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
						overflow-x: auto;
						margin: 0;
					}
					pre a {
						transition: color var(--duration-fast, 0.2s) ease, text-shadow var(--duration-fast, 0.2s) ease;
					}
					pre a:hover {
						color: hsla(216, 100%, 50%, 1) !important;
						text-shadow: 0 0 8px rgba(0, 102, 255, 0.4);
					}
					#new-project-btn:focus-visible, pre a:focus-visible { 
						outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1)); 
						outline-offset: 2px; 
					}
				</style>
				<div class="card">
					<div class="header">
						<h2>
							<span class="h-icon" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg></span>
							${this.tr('boards_heading', 'Boards')}
						</h2>
						<button id="new-project-btn" aria-expanded="false" aria-label="${this.tr('aria_add_project', 'Add a new project board')}">${this.tr('new_board', '+ New Board')}</button>
					</div>
					<pre tabindex="0" aria-label="${this.tr('aria_project_tree', 'Project board structure tree')}">${this.tr('loading_tree', 'Loading tree...')}</pre>
				</div>
			`;
		}
	}
}

customElements.define('project-tree', ProjectTree);

