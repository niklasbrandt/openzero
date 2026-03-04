import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { FORM_INPUT_STYLES } from '../services/formInputStyles';
import { FEEDBACK_STYLES } from '../services/feedbackStyles';

export class LifeOverview extends HTMLElement {
	private t: Record<string, string> = {};
	private projectFormOpen = false;

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.loadTranslations().then(() => {
			this.render();
			this.fetchData();
			this.setupListeners();
		});
		window.addEventListener('refresh-data', () => {
			this.fetchData();
		});
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => {
				this.render();
				this.fetchData();
				this.setupListeners();
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
		} catch (_) { /* fallback to empty -- render() uses defaults */ }
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] || fallback;
	}

	private setupListeners() {
		const newProjectBtn = this.shadowRoot?.querySelector('#new-project-btn');
		newProjectBtn?.addEventListener('click', () => this.toggleProjectForm());

		const projectForm = this.shadowRoot?.querySelector('#inline-project-form');
		projectForm?.addEventListener('submit', (e) => {
			e.preventDefault();
			this.handleCreateProject();
		});

		const cancelBtn = this.shadowRoot?.querySelector('#cancel-project-btn');
		cancelBtn?.addEventListener('click', () => this.toggleProjectForm(false));
	}

	private toggleProjectForm(forceState?: boolean) {
		this.projectFormOpen = forceState !== undefined ? forceState : !this.projectFormOpen;
		const formWrap = this.shadowRoot?.querySelector('.project-form-wrap') as HTMLElement;
		if (formWrap) {
			formWrap.classList.toggle('open', this.projectFormOpen);
		}
		if (!this.projectFormOpen) {
			const nameInput = this.shadowRoot?.querySelector<HTMLInputElement>('#new-project-name');
			if (nameInput) nameInput.value = '';
		}
	}

	private async handleCreateProject() {
		const nameInput = this.shadowRoot?.querySelector<HTMLInputElement>('#new-project-name');
		const name = nameInput?.value.trim();
		if (!name) return;

		const submitBtn = this.shadowRoot?.querySelector<HTMLButtonElement>('#submit-project-btn');
		if (submitBtn) {
			submitBtn.disabled = true;
			submitBtn.textContent = this.tr('creating', 'Creating...');
		}

		try {
			const resp = await fetch('/api/dashboard/projects', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name }),
			});
			if (!resp.ok) throw new Error('Failed');

			this.toggleProjectForm(false);
			this.fetchData();
			window.dispatchEvent(new CustomEvent('refresh-data'));
		} catch (e) {
			const feedback = this.shadowRoot?.querySelector('#project-feedback');
			if (feedback) {
				feedback.textContent = this.tr('project_create_error', 'Failed to create project.');
				feedback.className = 'feedback error visible';
				setTimeout(() => feedback.className = 'feedback error', 4000);
			}
		} finally {
			if (submitBtn) {
				submitBtn.disabled = false;
				submitBtn.textContent = this.tr('create', 'Create');
			}
		}
	}

	async fetchData() {
		try {
			const response = await fetch('/api/dashboard/life-tree');
			if (!response.ok) throw new Error('API error');
			const data = await response.json();
			this.updateUI(data);
			this.setupListeners();
		} catch (e) {
			console.error('Failed to fetch life tree', e);
			this.showError();
		}
	}

	showError() {
		const container = this.shadowRoot?.querySelector('#overview-container');
		if (container) {
			container.innerHTML = `<div class="error">${this.tr('api_error_life', 'Unable to load Life Overview. Check backend connection.')}</div>`;
		}
	}

	updateUI(data: any) {
		const container = this.shadowRoot?.querySelector('#overview-container');
		if (!container) return;

		const innerHtml = data.social_circles.inner.length > 0
			? data.social_circles.inner.map((p: any) => `<li>${p.name} <span class="rel">(${p.relationship})</span></li>`).join('')
			: `<li class="empty-li">${this.tr('no_family', 'No family connections.')}</li>`;

		const closeHtml = data.social_circles.close.length > 0
			? data.social_circles.close.map((p: any) => `<li>${p.name} <span class="rel">(${p.relationship})</span></li>`).join('')
			: `<li class="empty-li">${this.tr('no_social', 'No social circle added.')}</li>`;

		const timelineHtml = data.timeline.length > 0
			? data.timeline.map((e: any) => {
				const isBirthday = e.summary && (e.summary.includes('Birthday') || e.summary.includes('Geburtstag'));
				return `
					<div class="timeline-item${isBirthday ? ' birthday-item' : ''}" role="listitem">
						<span class="time">${e.time}</span>
						<span class="summary">${isBirthday ? '<span class="birthday-tag" aria-label="' + this.tr('aria_birthday_badge', 'Birthday') + '">&#127874;</span> ' : ''}${e.summary} ${!e.is_local ? '<small class="google-tag">(Google)</small>' : ''}</span>
					</div>
				`;
			}).join('')
			: `<div class="empty-state">${this.tr('no_events', 'No upcoming events for the next 3 days.')}</div>`;

		container.innerHTML = `
			<div class="overview-grid">
				<section class="mission-control" aria-label="${this.tr('aria_boards_section', 'Project boards')}">
					<div class="section-header">
						<h3>${this.tr('boards_heading', 'Boards')}</h3>
						<div class="header-actions">
							<button class="action-btn" id="new-project-btn" aria-label="${this.tr('aria_new_project', 'Create new project')}">${this.tr('new_project', '+ New Project')}</button>
							<button class="action-btn" onclick="this.closest('life-overview').parentElement.querySelector('create-project').toggle()">${this.tr('new_board', '+ New Board')}</button>
						</div>
					</div>
					<div class="project-form-wrap${this.projectFormOpen ? ' open' : ''}">
						<form id="inline-project-form">
							<div class="form-row">
								<input type="text" id="new-project-name" placeholder="${this.tr('project_name_placeholder', 'Project name...')}" autocomplete="off" />
								<button type="submit" id="submit-project-btn" class="btn-primary btn-sm">${this.tr('create', 'Create')}</button>
								<button type="button" id="cancel-project-btn" class="btn-ghost btn-sm">${this.tr('cancel', 'Cancel')}</button>
							</div>
							<div id="project-feedback" class="feedback" role="status" aria-live="polite"></div>
						</form>
					</div>
					<div class="tree-content">${data.projects_tree || this.tr('initializing_projects', 'Initializing projects...')}</div>
				</section>
				
				<div class="side-panel">
					<section class="social-section" aria-label="${this.tr('aria_social_circles', 'Social circles')}">
						<div class="circle-group">
								<h3>${this.tr('inner_circle', 'Inner Circle')} <small>(${this.tr('inner_subtitle', 'Family & Care')})</small></h3>
								<ul>${innerHtml}</ul>
						</div>
						<div class="circle-group" style="margin-top: 1.5rem;">
								<h3>${this.tr('close_circle', 'Close Circle')} <small>(${this.tr('close_subtitle', 'Friends & Social')})</small></h3>
								<ul>${closeHtml}</ul>
						</div>
					</section>

					<section class="timeline" aria-label="${this.tr('aria_upcoming_timeline', 'Upcoming timeline')}">
						<h3>${this.tr('timeline_heading', 'Timeline (Next 3 Days)')}</h3>
						<div class="timeline-list" role="list">${timelineHtml}</div>
					</section>
				</div>
			</div>
		`;
	}

	render() {
		if (this.shadowRoot) {
			this.shadowRoot.innerHTML = `
				<style>
					${BUTTON_STYLES}
					${ACCESSIBILITY_STYLES}
					${SECTION_HEADER_STYLES}
					${EMPTY_STATE_STYLES}
					${FORM_INPUT_STYLES}
					${FEEDBACK_STYLES}
					/* Override icon gradient */
					h2 .h-icon {
						background: linear-gradient(135deg, var(--accent-color, hsla(173, 80%, 40%, 1)) 0%, var(--accent-tertiary, hsla(239, 84%, 67%, 1)) 100%);
					}
					:host { display: block; }
					h3 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-muted, rgba(255, 255, 255, 0.4)); margin-bottom: 1rem; }
					h3 small { font-size: 0.65rem; text-transform: none; letter-spacing: 0.02em; opacity: 0.8; margin-left: 0.4rem; font-weight: 400; }
					
					.overview-grid {
						display: grid;
						grid-template-columns: 1.5fr 1fr;
						gap: 2rem;
					}

					@media (max-width: 900px) {
						.overview-grid { grid-template-columns: 1fr; }
					}

					pre, .tree-content {
						background: rgba(0, 0, 0, 0.2);
						padding: 1.25rem;
						border-radius: var(--radius-md, 0.75rem);
						font-family: var(--font-mono, 'Fira Code', monospace);
						font-size: 0.9rem;
						line-height: 1.6;
						color: var(--text-secondary, rgba(255, 255, 255, 0.85));
						margin: 0;
						overflow-x: auto;
						border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.03));
						white-space: pre-wrap;
					}

					.tree-content b { color: var(--accent-color, hsla(173, 80%, 40%, 1)); font-weight: 600; }
					.tree-content a { color: inherit; text-decoration: none; border-bottom: 1px solid rgba(255,255,255,0.1); transition: all var(--duration-fast, 0.2s); }
					.tree-content a:hover { color: hsla(216, 100%, 50%, 1); border-bottom-color: hsla(216, 100%, 50%, 1); }

					.section-header {
						display: flex;
						justify-content: space-between;
						align-items: center;
						margin-bottom: 1rem;
					}

					.header-actions {
						display: flex;
						gap: 0.5rem;
						align-items: center;
					}

					.action-btn {
						padding: 0.25rem 0.75rem;
						font-size: 0.75rem;
					}

					.project-form-wrap {
						max-height: 0;
						overflow: hidden;
						opacity: 0;
						transition: max-height 0.35s ease, opacity 0.25s ease, margin-bottom 0.25s ease;
						margin-bottom: 0;
					}

					.project-form-wrap.open {
						max-height: 120px;
						opacity: 1;
						margin-bottom: 1rem;
					}

					.form-row {
						display: flex;
						gap: 0.5rem;
						align-items: center;
					}

					.form-row input {
						flex: 1;
						margin-bottom: 0;
					}

					.side-panel { display: flex; flex-direction: column; gap: 2rem; }

					ul { list-style: none; padding: 0; margin: 0; }
					li { 
						font-size: 0.95rem; 
						line-height: 1.4;
						color: #fff; 
						margin-bottom: 0.5rem; 
						display: flex;
						align-items: center;
						gap: 0.5rem;
					}
					.rel { color: rgba(255, 255, 255, 0.4); font-size: 0.8rem; }
					.empty-li { font-size: 0.85rem; color: rgba(255, 255, 255, 0.25); font-style: italic; }

					.timeline-list { display: flex; flex-direction: column; gap: 0.75rem; }
					.timeline-item {
						display: flex;
						gap: 1rem;
						background: rgba(255, 255, 255, 0.02);
						padding: 0.75rem;
						border-radius: 0.6rem;
						font-size: 0.85rem;
					}
					.time { color: var(--accent-color, hsla(173, 80%, 40%, 1)); font-weight: 600; min-width: 70px; }
					.summary { color: var(--text-secondary, rgba(255, 255, 255, 0.8)); }
					.summary small { color: var(--color-info, hsla(217, 91%, 60%, 1)); opacity: 0.7; font-size: 0.7rem; margin-left: 0.3rem; }
					.google-tag { color: var(--accent-color, hsla(173, 80%, 40%, 1)); opacity: 0.85; }

					.birthday-item {
						background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.06);
						border: 1px solid rgba(var(--accent-color-rgb, 20, 184, 166), 0.12);
					}
					.birthday-tag { font-size: 1rem; }


					.error { color: var(--color-danger, hsla(0, 84%, 60%, 1)); text-align: center; padding: 2rem; }
				.action-btn:focus-visible { outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1)); outline-offset: 3px; }
				.tree-content a:focus-visible { outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1)); outline-offset: 2px; }
				</style>
				<div class="card">
					<h2>
					<span class="h-icon" aria-hidden="true">
						<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
							<circle cx="12" cy="12" r="10"></circle>
							<line x1="2" y1="12" x2="22" y2="12"></line>
							<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
						</svg>
					</span>
					${this.tr('life_overview', 'Life')}
					</h2>
					<div id="overview-container" aria-live="polite" aria-label="${this.tr('aria_life_overview', 'Life overview')}">
						<div style="text-align: center; padding: 2rem; color: rgba(255,255,255,0.3);">${this.tr('mapping_world', 'Mapping your world...')}</div>
					</div>
				</div>
			`;
		}
	}
}

customElements.define('life-overview', LifeOverview);
