import { BUTTON_STYLES } from '../services/buttonStyles';
import { initGoo } from '../services/gooStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';
import { FORM_INPUT_STYLES } from '../services/formInputStyles';
import { FEEDBACK_STYLES } from '../services/feedbackStyles';

export class LifeOverview extends HTMLElement {
	private t: Record<string, string> = {};
	private isSubmitting = false;

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
		initGoo(this);
		window.addEventListener('goo-changed', () => initGoo(this));
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
		const btn = this.shadowRoot?.querySelector<HTMLButtonElement>('#new-board-btn');
		const formWrapper = this.shadowRoot?.querySelector<HTMLDivElement>('#create-board-form');
		const boardForm = this.shadowRoot?.querySelector<HTMLFormElement>('#board-form');
		const cancelBtn = this.shadowRoot?.querySelector('#board-cancel');
		if (!btn || !formWrapper) return;

		btn.addEventListener('click', () => {
			const isOpen = formWrapper.classList.contains('open');
			formWrapper.classList.toggle('open');
			formWrapper.setAttribute('aria-hidden', isOpen ? 'true' : 'false');
			btn.textContent = isOpen
				? this.tr('new_board', '+ New Board')
				: `\u2212 ${this.tr('cancel', 'Cancel')}`;
			btn.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
			btn.setAttribute('aria-label', isOpen
				? this.tr('aria_add_project', 'Add a new project board')
				: this.tr('cancel_add_board', 'Cancel adding new board'));
			if (!isOpen) {
				setTimeout(() => this.shadowRoot?.querySelector<HTMLInputElement>('#board-name')?.focus(), 50);
			}
		});

		boardForm?.addEventListener('submit', (e) => {
			e.preventDefault();
			this.handleCreateBoard();
		});

		cancelBtn?.addEventListener('click', () => this.resetBoardForm());
	}

	private async handleCreateBoard() {
		if (this.isSubmitting) return;
		const name = this.shadowRoot?.querySelector<HTMLInputElement>('#board-name')?.value.trim();
		const description = this.shadowRoot?.querySelector<HTMLTextAreaElement>('#board-desc')?.value.trim();
		const tagsRaw = this.shadowRoot?.querySelector<HTMLInputElement>('#board-tags')?.value.trim();
		if (!name) {
			this.showBoardFeedback(this.tr('project_name_required', 'Please enter a name.'), 'error');
			return;
		}
		const tags = tagsRaw ? tagsRaw.split(',').map((t: string) => t.trim()).filter(Boolean) : [];
		this.isSubmitting = true;
		this.updateBoardSubmitBtn(true);
		try {
			const response = await fetch('/api/dashboard/projects', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name, description, tags }),
			});
			if (!response.ok) throw new Error('Failed to create project');
			this.showBoardFeedback(this.tr('board_created', 'Board created successfully!'), 'success');
			this.resetBoardForm();
			// Close form
			const fw = this.shadowRoot?.querySelector<HTMLDivElement>('#create-board-form');
			const b = this.shadowRoot?.querySelector<HTMLButtonElement>('#new-board-btn');
			fw?.classList.remove('open');
			fw?.setAttribute('aria-hidden', 'true');
			if (b) {
				b.textContent = this.tr('new_board', '+ New Board');
				b.setAttribute('aria-expanded', 'false');
				b.setAttribute('aria-label', this.tr('aria_add_project', 'Add a new project board'));
			}
			window.dispatchEvent(new CustomEvent('refresh-data', { detail: { actions: ['project', 'board'] } }));
		} catch (_e) {
			this.showBoardFeedback(this.tr('board_create_failed', 'Failed to create board. Please try again.'), 'error');
		} finally {
			this.isSubmitting = false;
			this.updateBoardSubmitBtn(false);
		}
	}

	private showBoardFeedback(message: string, type: 'success' | 'error') {
		const el = this.shadowRoot?.querySelector('#board-feedback');
		if (!el) return;
		el.textContent = message;
		el.className = `feedback ${type}`;
		el.classList.add('visible');
		setTimeout(() => el.classList.remove('visible'), 4000);
	}

	private resetBoardForm() {
		const name = this.shadowRoot?.querySelector<HTMLInputElement>('#board-name');
		const desc = this.shadowRoot?.querySelector<HTMLTextAreaElement>('#board-desc');
		const tags = this.shadowRoot?.querySelector<HTMLInputElement>('#board-tags');
		if (name) name.value = '';
		if (desc) desc.value = '';
		if (tags) tags.value = '';
	}

	private updateBoardSubmitBtn(loading: boolean) {
		const btn = this.shadowRoot?.querySelector<HTMLButtonElement>('#board-submit');
		if (!btn) return;
		btn.disabled = loading;
		btn.innerHTML = loading
			? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinner" aria-hidden="true"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"/><path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/></svg> ${this.tr('creating', 'Creating...')}`
			: this.tr('add_board', 'Add Board');
	}

	async fetchData() {
		try {
			const response = await fetch('/api/dashboard/life-tree');
			if (!response.ok) throw new Error('API error');
			const data = await response.json();
			this.updateUI(data);
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
					<h3 class="boards-sub-heading">${this.tr('boards_heading', 'Boards')}</h3>
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
						<div class="timeline-list"${data.timeline.length > 0 ? ' role="list"' : ''}>${timelineHtml}</div>
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

					:host { display: block; }

					.bg-glow {
						position: absolute;
						top: -20px; right: 10px; width: 150px; height: 150px;
						background: radial-gradient(circle at center, var(--accent-glow) 0%, transparent 70%);
						opacity: 0.1;
						pointer-events: none;
						z-index: 0;
					}

					h3 { 
						font-size: 0.85rem; 
						text-transform: uppercase; 
						letter-spacing: 0.1em; 
						color: var(--text-muted, hsla(0, 0%, 100%, 0.4)); 
						margin-bottom: 1rem; 
						position: relative;
						z-index: 1;
					}
					
					/* Override icon gradient and add Parallax */
					h2 .h-icon {
						background: linear-gradient(135deg, var(--accent-color, hsla(173, 80%, 40%, 1)) 0%, var(--accent-tertiary, hsla(239, 84%, 67%, 1)) 100%);
					}
					
					h3 small { 
						font-size: 0.65rem; 
						text-transform: none; 
						letter-spacing: 0.02em; 
						opacity: 0.8; 
						margin-left: 0.4rem; 
						font-weight: 400; 
					}
					
					.overview-grid {
						display: grid;
						grid-template-columns: 1.5fr 1fr;
						gap: 2rem;
						position: relative;
					}

					@media (max-width: 900px) {
						.overview-grid { grid-template-columns: 1fr; }
					}

					pre, .tree-content {
						background: var(--surface-card-subtle, hsla(0, 0%, 0%, 0.2));
						padding: 1.25rem;
						border-radius: var(--radius-md, 0.75rem);
						font-family: var(--font-mono, 'Fira Code', monospace);
						font-size: 0.9rem;
						line-height: 1.6;
						color: var(--text-secondary, hsla(0, 0%, 100%, 0.85));
						margin: 0;
						overflow-x: auto;
						border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.03));
						white-space: pre-wrap;
					}

					.tree-content b { color: var(--accent-primary, hsla(173, 80%, 40%, 1)); font-weight: 600; }
					.tree-content a { 
						color: inherit; 
						text-decoration: none; 
						border-bottom: 1px solid var(--border-subtle, hsla(0,0%,100%,0.1)); 
						transition: all var(--duration-fast, 0.2s); 
					}
					.tree-content a:hover { 
						color: var(--accent-secondary, hsla(216, 100%, 50%, 1)); 
						border-bottom-color: var(--accent-secondary, hsla(216, 100%, 50%, 1)); 
					}

/* card-top-row: life heading + + New Board button */
				.card-top-row {
					display: flex;
					justify-content: space-between;
					align-items: center;
					margin-bottom: 0.5rem;
				}

				#new-board-btn {
					background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.12));
					color: var(--accent-color, hsla(173, 80%, 40%, 1));
					border: 1px solid var(--border-accent, hsla(173, 80%, 40%, 0.2));
					padding: 0.4rem 1rem;
					border-radius: var(--radius-md, 0.6rem);
					font-size: 0.8rem;
					font-weight: 600;
					font-family: var(--font-sans, 'Inter', system-ui, sans-serif);
					cursor: pointer;
					transition: all var(--duration-base, 0.25s) ease;
					letter-spacing: 0.02em;
					min-height: 44px;
					flex-shrink: 0;
				}
				#new-board-btn:hover {
					background: var(--surface-accent-hover, hsla(173, 80%, 40%, 0.22));
					border-color: var(--border-accent-focus, hsla(173, 80%, 40%, 0.4));
				}

				/* Inline create-board form (slides in just below the heading row) */
				.create-form {
					max-height: 0;
					overflow: hidden;
					opacity: 0;
					pointer-events: none;
					transition: max-height 0.4s ease, opacity 0.3s ease, margin 0.3s ease, padding 0.3s ease, border-color 0.3s ease;
					padding-top: 0;
					margin-bottom: 0;
					border-top: 1px solid transparent;
				}
				.create-form.open {
					max-height: 650px;
					opacity: 1;
					pointer-events: auto;
					margin-bottom: 1.5rem;
					padding-top: 1.25rem;
					border-top-color: rgba(255, 255, 255, 0.06);
				}
				.form-hint {
					font-size: 0.75rem;
					color: rgba(255, 255, 255, 0.25);
					margin: -0.65rem 0 1rem;
				}
				.form-actions {
					display: flex;
					gap: 0.75rem;
					align-items: center;
					margin-top: 0.25rem;
				}
				.spinner { animation: spin 0.8s linear infinite; }
				@keyframes spin { to { transform: rotate(360deg); } }
				.feedback {
					font-size: 0.85rem;
					padding: 0.6rem 1rem;
					border-radius: 0.75rem;
					margin-top: 0.75rem;
					opacity: 0;
					transform: translateY(4px);
					transition: opacity 0.35s ease, transform 0.35s ease;
					pointer-events: none;
				}
				.feedback.visible { opacity: 1; transform: translateY(0); }
				.feedback.success {
					background: rgba(34, 197, 94, 0.1);
					border: 1px solid rgba(34, 197, 94, 0.2);
					color: var(--color-success, hsla(142, 69%, 58%, 1));
				}
				.feedback.error {
					background: rgba(239, 68, 68, 0.1);
					border: 1px solid rgba(239, 68, 68, 0.2);
					color: var(--color-danger, hsla(0, 91%, 71%, 1));
				}
				.boards-sub-heading { margin-bottom: 0.75rem; }

					.side-panel { display: flex; flex-direction: column; gap: 2rem; }

					ul { list-style: none; padding: 0; margin: 0; }
					li { 
						font-size: 0.95rem; 
						line-height: 1.4;
						color: var(--text-primary, hsla(0, 0%, 100%, 1)); 
						margin-bottom: 0.6rem; 
						display: flex;
						align-items: center;
						gap: 0.5rem;
						min-height: 24px;
					}
					.rel { color: var(--text-muted, hsla(0, 0%, 100%, 0.4)); font-size: 0.8rem; }
					.empty-li { font-size: 0.85rem; color: var(--text-muted, hsla(0, 0%, 100%, 0.25)); font-style: italic; }

					.timeline-list { display: flex; flex-direction: column; gap: 0.75rem; }
					.timeline-item {
						display: flex;
						gap: 1rem;
						background: var(--surface-card, hsla(0, 0%, 100%, 0.02));
						padding: 0.75rem 1rem;
						border-radius: 0.6rem;
						font-size: 0.85rem;
						min-height: 48px;
						border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.03));
					}
					.time { color: var(--accent-primary, hsla(173, 80%, 40%, 1)); font-weight: 600; min-width: 75px; }
					.summary { color: var(--text-secondary, hsla(0, 0%, 100%, 0.8)); line-height: 1.4; }
					.summary small { color: var(--status-info, hsla(217, 91%, 60%, 1)); opacity: 0.7; font-size: 0.7rem; margin-left: 0.3rem; }
					.google-tag { color: var(--accent-primary, hsla(173, 80%, 40%, 1)); opacity: 0.85; }

					.birthday-item {
						background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.06));
						border: 1px solid var(--border-accent-subtle, hsla(173, 80%, 40%, 0.12));
					}
					.birthday-tag { font-size: 1rem; }


					.error { color: var(--color-danger, hsla(0, 84%, 42%, 1)); text-align: center; padding: 2rem; }
				#new-board-btn:focus-visible { outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); outline-offset: 2px; }
				#board-name:focus-visible, #board-desc:focus-visible, #board-tags:focus-visible { outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1)); outline-offset: 2px; }
				.tree-content a:focus-visible { outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); outline-offset: 2px; }
				@media (prefers-reduced-motion: reduce) {
					.create-form { transition: none; }
					.spinner { animation: none; }
					.feedback { transition: none; }
				}
				@media (forced-colors: active) {
					.h-icon { background: ButtonFace; border: 1px solid ButtonText; }
					.time { color: LinkText; }
					.google-tag { color: LinkText; }
					.birthday-tag { border: 1px solid ButtonText; }
					#new-board-btn { border: 1px solid ButtonText; }
					#board-name, #board-desc, #board-tags { border: 1px solid ButtonText; }
				}
				</style>
				<div class="card">
					<div class="card-top-row">
						<h2>
							<span class="h-icon" aria-hidden="true">
								<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
									<circle cx="12" cy="12" r="10"></circle>
									<line x1="2" y1="12" x2="22" y2="12"></line>
									<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
								</svg>
							</span>
							${this.tr('life_overview', 'Life')}
						</h2>
						<button id="new-board-btn" aria-expanded="false" aria-label="${this.tr('aria_add_project', 'Add a new project board')}">${this.tr('new_board', '+ New Board')}</button>
					</div>
					<div id="create-board-form" class="create-form" aria-hidden="true">
						<form id="board-form" novalidate>
							<label for="board-name">${this.tr('name_label', 'Name')}</label>
							<input type="text" id="board-name" placeholder="${this.tr('project_placeholder', 'E.g. Daily Missions')}" autocomplete="off" required aria-required="true" />
							<label for="board-desc">${this.tr('description_label', 'Description')}</label>
							<textarea id="board-desc" rows="3" placeholder="${this.tr('project_desc_placeholder', 'What is this project about?')}"></textarea>
							<label for="board-tags">${this.tr('tags_label', 'Tags')}</label>
							<input type="text" id="board-tags" placeholder="${this.tr('tags_placeholder', 'ai, automation, backend')}" />
							<p class="form-hint">${this.tr('tags_hint', 'Comma-separated, optional')}</p>
							<div class="form-actions">
								<button type="submit" id="board-submit" class="btn-primary">${this.tr('add_board', 'Add Board')}</button>
								<button type="button" id="board-cancel" class="btn-ghost">${this.tr('cancel', 'Cancel')}</button>
							</div>
						</form>
						<div id="board-feedback" class="feedback" role="status" aria-live="polite" aria-atomic="true"></div>
					</div>
					<div id="overview-container" aria-live="polite" aria-label="${this.tr('aria_life_overview', 'Life overview')}">
						<div style="text-align: center; padding: 2rem; color: var(--text-muted, hsla(0,0%,100%,0.3));">${this.tr('mapping_world', 'Mapping your world...')}</div>
					</div>
				</div>
			`;
		}
	}
}

customElements.define('life-overview', LifeOverview);
