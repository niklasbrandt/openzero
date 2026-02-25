export class CreateProject extends HTMLElement {
	private isSubmitting = false;

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
		this.setupListeners();
	}

	public toggle() {
		const isOpen = this.getAttribute('data-open') === 'true';
		this.setAttribute('data-open', (!isOpen).toString());
	}

	private setupListeners() {
		const form = this.shadowRoot?.querySelector('#project-form');
		const cancelBtn = this.shadowRoot?.querySelector('#cancel-btn');

		form?.addEventListener('submit', (e) => {
			e.preventDefault();
			this.handleCreate();
		});

		cancelBtn?.addEventListener('click', () => this.resetForm());
	}

	private async handleCreate() {
		if (this.isSubmitting) return;

		const name = this.shadowRoot?.querySelector<HTMLInputElement>('#project-name')?.value.trim();
		const description = this.shadowRoot?.querySelector<HTMLTextAreaElement>('#project-desc')?.value.trim();
		const tagsRaw = this.shadowRoot?.querySelector<HTMLInputElement>('#project-tags')?.value.trim();

		if (!name) {
			this.showFeedback('Please enter a project name.', 'error');
			return;
		}

		const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

		this.isSubmitting = true;
		this.updateSubmitButton(true);

		try {
			const response = await fetch('/api/dashboard/projects', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name, description, tags }),
			});

			if (!response.ok) throw new Error('Failed to create project');

			this.showFeedback(`Project "${name}" created successfully!`, 'success');
			this.resetForm();

			// Notify other components (e.g. ProjectTree) to refresh
			this.dispatchEvent(new CustomEvent('project-created', {
				bubbles: true,
				composed: true,
				detail: { name, description, tags },
			}));
		} catch (e) {
			this.showFeedback('⚠ Failed to create project. Please try again.', 'error');
		} finally {
			this.isSubmitting = false;
			this.updateSubmitButton(false);
		}
	}

	private resetForm() {
		const name = this.shadowRoot?.querySelector<HTMLInputElement>('#project-name');
		const desc = this.shadowRoot?.querySelector<HTMLTextAreaElement>('#project-desc');
		const tags = this.shadowRoot?.querySelector<HTMLInputElement>('#project-tags');
		if (name) name.value = '';
		if (desc) desc.value = '';
		if (tags) tags.value = '';
	}

	private showFeedback(message: string, type: 'success' | 'error') {
		const el = this.shadowRoot?.querySelector('#feedback');
		if (!el) return;
		el.textContent = message;
		el.className = `feedback ${type}`;
		el.classList.add('visible');
		setTimeout(() => el.classList.remove('visible'), 4000);
	}

	private updateSubmitButton(loading: boolean) {
		const btn = this.shadowRoot?.querySelector<HTMLButtonElement>('#submit-btn');
		if (!btn) return;
		btn.disabled = loading;
		btn.innerHTML = loading
			? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinner"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"/><path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/></svg> Creating…`
			: `${this.plusSVG()} Create Project`;
	}

	private plusSVG(): string {
		return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
	}

	private folderSVG(): string {
		return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
	}

	render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
		<style>
					h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1rem 0; color: #fff; letter-spacing: 0.02em; }
			:host {
				display: block;
				max-height: 0;
				overflow: hidden;
				opacity: 0;
				margin-top: 0;
				padding-top: 0;
				border-top: 1px solid transparent;
				pointer-events: none;
				transition: max-height 0.4s ease, opacity 0.3s ease, margin-top 0.3s ease, padding-top 0.3s ease, border-color 0.3s ease;
			}

			:host([data-open="true"]) {
				max-height: 600px;
				opacity: 1;
				margin-top: 1.5rem;
				padding-top: 1.5rem;
				border-top-color: rgba(255, 255, 255, 0.06);
				pointer-events: auto;
			}

			

			h2 svg { color: rgba(255,255,255,0.4); }

			label {
				display: block;
				font-size: 0.8rem;
				font-weight: 500;
				color: rgba(255, 255, 255, 0.5);
				text-transform: uppercase;
				letter-spacing: 0.06em;
				margin-bottom: 0.4rem;
			}

			input, textarea {
				width: 100%;
				box-sizing: border-box;
				background: rgba(0, 0, 0, 0.2);
				backdrop-filter: blur(8px);
				-webkit-backdrop-filter: blur(8px);
				border: 1px solid rgba(255, 255, 255, 0.08);
				border-radius: 0.75rem;
				padding: 0.6rem 1rem;
				color: #fff;
				font-family: 'Inter', system-ui, sans-serif;
				font-size: 0.9rem;
				outline: none;
				transition: border-color 0.3s ease, background 0.3s ease, box-shadow 0.3s ease;
				margin-bottom: 1rem;
			}

			textarea {
				resize: vertical;
				min-height: 72px;
				line-height: 1.5;
			}

			input::placeholder, textarea::placeholder {
				color: rgba(255,255,255,0.2);
			}

			input:focus, textarea:focus {
				border-color: rgba(20, 184, 166, 0.4);
				background: rgba(0, 0, 0, 0.28);
				box-shadow: 0 0 20px rgba(20, 184, 166, 0.08);
			}

			.hint {
				font-size: 0.75rem;
				color: rgba(255,255,255,0.25);
				margin-top: -0.65rem;
				margin-bottom: 1rem;
			}

			.actions {
				display: flex;
				gap: 0.75rem;
				align-items: center;
			}

			button {
				font-family: 'Inter', system-ui, sans-serif;
				font-weight: 600;
				font-size: 0.8rem;
				border: 1px solid rgba(20, 184, 166, 0.2);
				border-radius: 0.6rem;
				padding: 0.4rem 1rem;
				cursor: pointer;
				display: inline-flex;
				align-items: center;
				gap: 0.4rem;
				background: rgba(20, 184, 166, 0.12);
				color: #14B8A6;
				letter-spacing: 0.02em;
				transition: all 0.25s ease;
			}

			button:hover:not(:disabled) {
				background: rgba(20, 184, 166, 0.22);
				border-color: rgba(20, 184, 166, 0.4);
			}

			#submit-btn:disabled {
				opacity: 0.5;
				cursor: not-allowed;
			}

			#cancel-btn {
				background: rgba(255, 255, 255, 0.06);
				color: rgba(255,255,255,0.5);
				border-color: rgba(255, 255, 255, 0.08);
			}

			#cancel-btn:hover {
				background: rgba(255, 255, 255, 0.1);
				color: rgba(255,255,255,0.7);
				border-color: rgba(255, 255, 255, 0.15);
			}

			/* ── Feedback toast ── */
			.feedback {
				font-size: 0.85rem;
				padding: 0.6rem 1rem;
				border-radius: 0.75rem;
				margin-top: 1rem;
				opacity: 0;
				transform: translateY(4px);
				transition: all 0.35s ease;
				pointer-events: none;
			}

			.feedback.visible {
				opacity: 1;
				transform: translateY(0);
			}

			.feedback.success {
				background: rgba(34, 197, 94, 0.1);
				border: 1px solid rgba(34, 197, 94, 0.2);
				color: #4ade80;
			}

			.feedback.error {
				background: rgba(239, 68, 68, 0.1);
				border: 1px solid rgba(239, 68, 68, 0.2);
				color: #f87171;
			}

			/* ── Spinner ── */
			.spinner { animation: spin 0.8s linear infinite; }
			@keyframes spin { to { transform: rotate(360deg); } }
		</style>

		<h2>${this.folderSVG()} Create Project</h2>

		<form id="project-form">
			<label for="project-name">Project Name</label>
			<input type="text" id="project-name" placeholder="my-new-project" autocomplete="off" />

			<label for="project-desc">Description</label>
			<textarea id="project-desc" rows="3" placeholder="What is this project about?"></textarea>

			<label for="project-tags">Tags</label>
			<input type="text" id="project-tags" placeholder="ai, automation, backend" />
			<p class="hint">Comma-separated, optional</p>

			<div class="actions">
				<button type="submit" id="submit-btn">${this.plusSVG()} Create Project</button>
				<button type="button" id="cancel-btn">Clear</button>
			</div>
		</form>

		<div id="feedback" class="feedback"></div>
		`;
	}
}

customElements.define('create-project', CreateProject);
