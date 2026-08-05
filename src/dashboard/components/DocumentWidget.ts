import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';

type UploadState = 'idle' | 'uploading' | 'summarizing' | 'done' | 'error';

interface ProcessResult {
	filename: string;
	char_count: number;
	truncated: boolean;
	summary: string | null;
	learned: boolean;
}

export class DocumentWidget extends HTMLElement {
	private t: Record<string, string> = {};
	private state: UploadState = 'idle';
	private result: ProcessResult | null = null;
	private errorMsg: string = '';
	private dragActive: boolean = false;
	private learnChecked: boolean = false;
	private progress: number = 0;
	private _dragEnterCount: number = 0;

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	private async loadTranslations() {
		if ((window as any).__z_translations) { this.t = (window as any).__z_translations; return; }
		try {
			await (window as any).__z_translations_ready;
			if ((window as any).__z_translations) { this.t = (window as any).__z_translations; return; }
			const res = await fetch('/api/dashboard/translations');
			if (res.ok) this.t = await res.json();
		} catch (_) { }
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] || fallback;
	}

	private esc(s: string | undefined | null): string {
		if (!s) return '';
		return String(s)
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#39;');
	}

	connectedCallback() {
		this.loadTranslations().then(() => this.render());
	}

	// ── Drag & Drop ────────────────────────────────────────────────────────

	private onDragEnter = (e: DragEvent) => {
		e.preventDefault();
		this._dragEnterCount++;
		if (this._dragEnterCount === 1) {
			this.dragActive = true;
			this.render();
		}
	};

	private onDragLeave = (e: DragEvent) => {
		e.preventDefault();
		this._dragEnterCount--;
		if (this._dragEnterCount === 0) {
			this.dragActive = false;
			this.render();
		}
	};

	private onDragOver = (e: DragEvent) => {
		e.preventDefault();
		if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
	};

	private onDrop = (e: DragEvent) => {
		e.preventDefault();
		this._dragEnterCount = 0;
		this.dragActive = false;
		const file = e.dataTransfer?.files[0];
		if (file) this.processFile(file);
		else this.render();
	};

	private onFileInput = (e: Event) => {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (file) this.processFile(file);
		input.value = '';
	};

	private onLearnToggle = (e: Event) => {
		this.learnChecked = (e.target as HTMLInputElement).checked;
	};

	private onReset = () => {
		this.state = 'idle';
		this.result = null;
		this.errorMsg = '';
		this.progress = 0;
		this.learnChecked = false;
		this._dragEnterCount = 0;
		this.dragActive = false;
		this.render();
	};

	// ── Upload & Process ───────────────────────────────────────────────────

	private async processFile(file: File): Promise<void> {
		const ALLOWED = ['application/pdf',
			'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
			'text/plain', 'text/markdown'];
		const ALLOWED_EXT = ['.pdf', '.docx', '.txt', '.md'];

		const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
		if (!ALLOWED_EXT.includes(ext) && !ALLOWED.includes(file.type)) {
			this.state = 'error';
			this.errorMsg = this.tr('doc_unsupported_type', 'Unsupported file type. Allowed: PDF, DOCX, TXT, MD.');
			this.render();
			return;
		}
		if (file.size > 10 * 1024 * 1024) {
			this.state = 'error';
			this.errorMsg = this.tr('doc_too_large', 'File exceeds the 10 MB limit.');
			this.render();
			return;
		}

		this.state = 'uploading';
		this.progress = 0;
		this.result = null;
		this.errorMsg = '';
		this.render();

		const AUTH_TOKEN_KEY = 'z_auth_token';
		const token = localStorage.getItem(AUTH_TOKEN_KEY) || '';
		const form = new FormData();
		form.append('file', file);

		const params = new URLSearchParams({
			token,
			summarize: 'true',
			learn: String(this.learnChecked),
		});

		try {
			// Simulate progress for UX (real upload progress via XHR would require
			// dropping fetch — for simplicity we animate to 80% then wait for response)
			const prog = setInterval(() => {
				if (this.progress < 80) { this.progress += 10; this.render(); }
			}, 150);

			const res = await fetch(`/api/dashboard/documents/process?${params}`, {
				method: 'POST',
				body: form,
			});

			clearInterval(prog);
			this.progress = 90;
			this.state = 'summarizing';
			this.render();

			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: res.statusText }));
				throw new Error(err.detail || res.statusText);
			}

			this.result = await res.json() as ProcessResult;
			this.progress = 100;
			this.state = 'done';
		} catch (e: any) {
			this.state = 'error';
			this.errorMsg = e?.message || this.tr('doc_upload_error', 'Upload failed. Please try again.');
		}

		this.render();
	}

	// ── Render ─────────────────────────────────────────────────────────────

	private render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
			<style>
				${ACCESSIBILITY_STYLES}
				${SECTION_HEADER_STYLES}
				${BUTTON_STYLES}

				:host {
					display: block;
					container-type: inline-size;
				}

				.card {
					background: var(--surface-card, rgba(255,255,255,0.04));
					border: 1px solid var(--border, rgba(255,255,255,0.08));
					border-radius: 1rem;
					padding: 1.5rem;
					display: flex;
					flex-direction: column;
					gap: 1.25rem;
				}

				/* ── Drop Zone ─────────────────────────────────── */
				.drop-zone {
					border: 2px dashed var(--border, rgba(255,255,255,0.12));
					border-radius: 0.75rem;
					padding: 2.5rem 1.5rem;
					display: flex;
					flex-direction: column;
					align-items: center;
					justify-content: center;
					gap: 0.75rem;
					text-align: center;
					cursor: pointer;
					transition: border-color 0.2s ease, background 0.2s ease;
					outline: none;
				}

				.drop-zone:focus-visible {
					outline: 2px solid #14B8A6;
					outline-offset: 2px;
				}

				.drop-zone.active,
				.drop-zone:hover {
					border-color: #14B8A6;
					background: rgba(20, 184, 166, 0.06);
				}

				.drop-icon {
					font-size: 2.5rem;
					opacity: 0.6;
					line-height: 1;
				}

				.drop-label {
					font-size: 0.95rem;
					color: var(--text-secondary, rgba(255,255,255,0.55));
					margin: 0;
				}

				.drop-hint {
					font-size: 0.78rem;
					color: var(--text-tertiary, rgba(255,255,255,0.35));
					margin: 0;
				}

				.file-input {
					display: none;
				}

				/* ── Learn toggle ──────────────────────────────── */
				.learn-row {
					display: flex;
					align-items: center;
					gap: 0.6rem;
					font-size: 0.875rem;
					color: var(--text-secondary, rgba(255,255,255,0.55));
					cursor: pointer;
					user-select: none;
				}

				.learn-row input[type="checkbox"] {
					width: 1rem;
					height: 1rem;
					accent-color: #14B8A6;
					cursor: pointer;
					flex-shrink: 0;
				}

				/* ── Progress ──────────────────────────────────── */
				.progress-bar-wrap {
					height: 4px;
					border-radius: 2px;
					background: var(--border, rgba(255,255,255,0.08));
					overflow: hidden;
				}

				.progress-bar {
					height: 100%;
					border-radius: 2px;
					background: linear-gradient(90deg, #14B8A6, #0ea5e9);
					transition: width 0.15s ease;
				}

				.status-text {
					font-size: 0.85rem;
					color: var(--text-secondary, rgba(255,255,255,0.55));
					text-align: center;
					animation: pulse 1.6s ease-in-out infinite;
				}

				@keyframes pulse {
					0%, 100% { opacity: 1; }
					50% { opacity: 0.5; }
				}

				/* ── Result ────────────────────────────────────── */
				.result-box {
					background: rgba(20, 184, 166, 0.06);
					border: 1px solid rgba(20, 184, 166, 0.2);
					border-radius: 0.75rem;
					padding: 1.25rem;
					display: flex;
					flex-direction: column;
					gap: 0.75rem;
				}

				.result-filename {
					font-size: 0.8rem;
					color: var(--text-tertiary, rgba(255,255,255,0.35));
					font-family: monospace;
				}

				.result-summary {
					font-size: 0.9rem;
					color: var(--text-primary, rgba(255,255,255,0.88));
					line-height: 1.65;
					white-space: pre-wrap;
				}

				.badge {
					display: inline-flex;
					align-items: center;
					gap: 0.35rem;
					font-size: 0.75rem;
					padding: 0.2rem 0.6rem;
					border-radius: 999px;
					border: 1px solid rgba(20, 184, 166, 0.3);
					color: #14B8A6;
					width: fit-content;
				}

				.truncated-notice {
					font-size: 0.75rem;
					color: var(--text-tertiary, rgba(255,255,255,0.35));
				}

				/* ── Error ─────────────────────────────────────── */
				.error-box {
					background: rgba(239, 68, 68, 0.06);
					border: 1px solid rgba(239, 68, 68, 0.25);
					border-radius: 0.75rem;
					padding: 1rem 1.25rem;
					font-size: 0.875rem;
					color: #f87171;
					line-height: 1.5;
				}

				/* ── Reduced motion ────────────────────────────── */
				@media (prefers-reduced-motion: reduce) {
					.drop-zone, .progress-bar { transition: none; }
					.status-text { animation: none; opacity: 0.7; }
				}

				/* ── Forced colours ────────────────────────────── */
				@media (forced-colors: active) {
					.drop-zone { border-color: ButtonText; }
					.drop-zone.active { border-color: Highlight; }
					.badge { border-color: Highlight; color: Highlight; }
				}
			</style>

			<div class="card" role="region" aria-label="${this.esc(this.tr('aria_document_widget', 'Document processing panel'))}">

				<div class="section-header">
					<span class="h-icon" aria-hidden="true">&#128196;</span>
					${this.esc(this.tr('doc_widget_title', 'Read a Document'))}
				</div>

				${this.renderBody()}
			</div>
		`;

		this.bindEvents();
	}

	private renderBody(): string {
		if (this.state === 'uploading' || this.state === 'summarizing') {
			const label = this.state === 'uploading'
				? this.tr('doc_uploading', 'Uploading...')
				: this.tr('doc_summarizing', 'Z is reading the document...');
			return `
				<div class="progress-bar-wrap" role="progressbar" aria-valuenow="${this.progress}" aria-valuemin="0" aria-valuemax="100">
					<div class="progress-bar" style="width: ${this.progress}%"></div>
				</div>
				<p class="status-text" role="status" aria-live="polite">${this.esc(label)}</p>
			`;
		}

		if (this.state === 'done' && this.result) {
			return `
				<div class="result-box" role="region" aria-label="${this.esc(this.tr('aria_doc_result', 'Document processing result'))}">
					<p class="result-filename">${this.esc(this.result.filename)}</p>
					${this.result.summary
						? `<p class="result-summary">${this.esc(this.result.summary)}</p>`
						: `<p class="result-summary">${this.esc(this.tr('doc_no_summary', 'Summary not available.'))}</p>`
					}
					${this.result.learned
						? `<span class="badge">&#10003; ${this.esc(this.tr('doc_learned', 'Stored in memory'))}</span>`
						: ''
					}
					${this.result.truncated
						? `<p class="truncated-notice">${this.esc(this.tr('doc_truncated', 'Document was truncated to 16 000 characters for processing.'))}</p>`
						: ''
					}
				</div>
				<button class="btn btn-secondary" id="doc-reset-btn" aria-label="${this.esc(this.tr('aria_doc_reset', 'Process another document'))}">
					${this.esc(this.tr('doc_reset', 'Process another document'))}
				</button>
			`;
		}

		if (this.state === 'error') {
			return `
				<div class="error-box" role="alert" aria-live="assertive">
					${this.esc(this.errorMsg || this.tr('doc_upload_error', 'Upload failed. Please try again.'))}
				</div>
				<button class="btn btn-secondary" id="doc-reset-btn" aria-label="${this.esc(this.tr('aria_doc_retry', 'Try again'))}">
					${this.esc(this.tr('doc_retry', 'Try again'))}
				</button>
			`;
		}

		// Idle state — show drop zone
		return `
			<div
				class="drop-zone${this.dragActive ? ' active' : ''}"
				id="doc-drop-zone"
				tabindex="0"
				role="button"
				aria-label="${this.esc(this.tr('aria_doc_drop_zone', 'Click or drop a file to process. Supported types: PDF, DOCX, TXT, MD.'))}"
			>
				<span class="drop-icon" aria-hidden="true">&#128196;</span>
				<p class="drop-label">
					${this.esc(this.dragActive
						? this.tr('doc_drop_now', 'Drop to process')
						: this.tr('doc_drop_idle', 'Drop a file here, or click to choose')
					)}
				</p>
				<p class="drop-hint">${this.esc(this.tr('doc_drop_hint', 'PDF · DOCX · TXT · MD — max 10 MB'))}</p>
			</div>
			<input
				type="file"
				id="doc-file-input"
				class="file-input"
				accept=".pdf,.docx,.txt,.md"
				aria-label="${this.esc(this.tr('aria_doc_file_input', 'Choose a file'))}"
			/>
			<label class="learn-row" for="doc-learn-checkbox">
				<input
					type="checkbox"
					id="doc-learn-checkbox"
					${this.learnChecked ? 'checked' : ''}
					aria-describedby="doc-learn-desc"
				/>
				${this.esc(this.tr('doc_learn_label', 'Also store in Z\'s memory (Qdrant)'))}
			</label>
			<p id="doc-learn-desc" class="sr-only">
				${this.esc(this.tr('doc_learn_desc', 'If checked, the PII-stripped text will be stored as a long-term memory point in Qdrant so Z can reference it in future conversations.'))}
			</p>
		`;
	}

	private bindEvents() {
		if (!this.shadowRoot) return;

		const dropZone = this.shadowRoot.getElementById('doc-drop-zone');
		if (dropZone) {
			dropZone.addEventListener('dragenter', this.onDragEnter as any);
			dropZone.addEventListener('dragleave', this.onDragLeave as any);
			dropZone.addEventListener('dragover', this.onDragOver as any);
			dropZone.addEventListener('drop', this.onDrop as any);
			dropZone.addEventListener('click', () => {
				this.shadowRoot?.getElementById('doc-file-input')?.click();
			});
			dropZone.addEventListener('keydown', (e: KeyboardEvent) => {
				if (e.key === 'Enter' || e.key === ' ') {
					e.preventDefault();
					this.shadowRoot?.getElementById('doc-file-input')?.click();
				}
			});
		}

		const fileInput = this.shadowRoot.getElementById('doc-file-input') as HTMLInputElement | null;
		fileInput?.addEventListener('change', this.onFileInput);

		const learnCb = this.shadowRoot.getElementById('doc-learn-checkbox');
		learnCb?.addEventListener('change', this.onLearnToggle);

		const resetBtn = this.shadowRoot.getElementById('doc-reset-btn');
		resetBtn?.addEventListener('click', this.onReset);
	}
}

customElements.define('document-widget', DocumentWidget);
