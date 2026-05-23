import { BUTTON_STYLES } from '../services/buttonStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';

type Stage = 'preview' | 'passphrase' | 'import';
type ConflictMode = 'skip' | 'merge' | 'replace';
type StrengthLevel = 0 | 1 | 2;

interface PreviewItem {
	path?: string;
	id?: string;
	text?: string;
	label?: string;
	name?: string;
	title?: string;
	type?: string;
	description?: string;
	summary?: string;
	dtstart?: string;
	location?: string;
	stored_at?: string;
	confidence?: number;
	rationale?: string;
	size?: number;
	[key: string]: unknown;
}

interface SectionState {
	loaded: boolean;
	loading: boolean;
	items: PreviewItem[];
	total: number;
	nextCursor: number | null;
	error: string | null;
}

interface ImportReport {
	created: Record<string, number>;
	skipped: Record<string, number>;
	errors: Array<{ path: string; kind: string; reason: string }>;
	dry_run: boolean;
	conflict: string;
	duration_ms: number;
}

const SECTIONS = ['planka', 'calendar', 'memory', 'atlas', 'preferences', 'redis', 'files'] as const;

export class BackupCard extends HTMLElement {
	private t: Record<string, string> = {};
	private stage: Stage = 'preview';
	private expandedSections: Set<string> = new Set();
	private sectionState: Record<string, SectionState> = {};
	private excluded_paths: Set<string> = new Set();

	// Passphrase stage
	private passphraseStrength: StrengthLevel = 0;
	private exportError: string = '';
	private exportGenerating: boolean = false;
	private exportDone: boolean = false;

	// Import stage
	private importFile: File | null = null;
	private importConflict: ConflictMode = 'skip';
	private importPrefsOpt: boolean = false;
	private dryRunReport: ImportReport | null = null;
	private importGenerating: boolean = false;
	private importError: string = '';
	private importResult: ImportReport | null = null;
	private importDone: boolean = false;
	private _importDialogTrigger: HTMLElement | null = null;
	private _strengthDebounce: ReturnType<typeof setTimeout> | null = null;

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
		for (const s of SECTIONS) {
			this.sectionState[s] = { loaded: false, loading: false, items: [], total: 0, nextCursor: null, error: null };
		}
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

	disconnectedCallback() {
		if (this._strengthDebounce) clearTimeout(this._strengthDebounce);
	}

	// ── Helpers ──────────────────────────────────────────────────────────────

	private _getItemKey(section: string, item: PreviewItem): string {
		return item.path || `${section}/${item.id || item.label || item.name || String(Math.random())}`;
	}

	private _computeStrength(passphrase: string): StrengthLevel {
		if (passphrase.length < 12) return 0;
		const hasMixed = /[a-z]/.test(passphrase) && /[A-Z]/.test(passphrase)
			&& (/\d/.test(passphrase) || /[^a-zA-Z0-9]/.test(passphrase));
		if (passphrase.length >= 16 && hasMixed) return 2;
		return 1;
	}

	private _selectedCount(): number {
		let total = 0;
		for (const s of SECTIONS) {
			for (const item of this.sectionState[s].items) {
				if (!this.excluded_paths.has(this._getItemKey(s, item))) total++;
			}
		}
		return total;
	}

	private _sectionsWithItems(): number {
		return SECTIONS.filter(s => this.sectionState[s].items.length > 0).length;
	}

	private _estimateSizeKb(): number {
		let total = 0;
		for (const s of SECTIONS) {
			for (const item of this.sectionState[s].items) {
				if (!this.excluded_paths.has(this._getItemKey(s, item))) {
					total += (item.size as number | undefined) || JSON.stringify(item).length;
				}
			}
		}
		return Math.ceil(total / 1024);
	}

	private _sectionLabel(section: string): string {
		const map: Record<string, [string, string]> = {
			planka:      ['backup_section_planka', 'Projects & Boards'],
			calendar:    ['backup_section_calendar', 'Calendar'],
			memory:      ['backup_section_memory', 'Memory'],
			atlas:       ['backup_section_atlas', 'Atlas'],
			preferences: ['backup_section_preferences', 'Preferences'],
			redis:       ['backup_section_redis', 'System'],
			files:       ['backup_section_files', 'Files'],
		};
		const entry = map[section];
		return entry ? this.tr(entry[0], entry[1]) : section;
	}

	private _renderItemText(section: string, item: PreviewItem): string {
		switch (section) {
			case 'planka': {
				const name = String(item.name || item.title || item.label || item.path || '\u2014');
				const desc = item.description ? String(item.description).slice(0, 80) : '';
				return desc ? `${name} \u2014 ${desc}` : name;
			}
			case 'calendar': {
				const parts = [String(item.summary || item.title || item.path || '\u2014')];
				if (item.dtstart) parts.push(String(item.dtstart));
				if (item.location) parts.push(String(item.location));
				return parts.join(' \u2022 ');
			}
			case 'memory': {
				const text = String(item.text || item.label || item.path || '\u2014').slice(0, 120);
				return item.stored_at ? `${text} \u2022 ${String(item.stored_at)}` : text;
			}
			case 'atlas': {
				if (item.rationale) {
					const title = String(item.title || item.label || '\u2014');
					return `${title} \u2014 ${String(item.rationale).slice(0, 80)}`;
				}
				const label = String(item.label || item.name || item.path || '\u2014');
				const conf = item.confidence !== undefined ? ` \u2022 confidence: ${item.confidence}` : '';
				const typeStr = item.type ? `[${item.type}] ` : '';
				return `${typeStr}${label}${conf}`;
			}
			case 'files': {
				const filePath = String(item.path || item.name || '\u2014');
				const sizeKb = item.size ? ` (${Math.ceil(Number(item.size) / 1024)} KB)` : '';
				return `${filePath}${sizeKb}`;
			}
			default:
				return String(item.path || item.label || item.title || item.name || item.text || '\u2014').slice(0, 150);
		}
	}

	// ── Render ───────────────────────────────────────────────────────────────

	private render() {
		const root = this.shadowRoot as ShadowRoot;
		root.innerHTML = `
			<style>
				${ACCESSIBILITY_STYLES}
				${SECTION_HEADER_STYLES}
				${BUTTON_STYLES}

				:host { display: block; font-family: inherit; }

				.card {
					background: var(--surface, hsla(220, 20%, 12%, 1));
					border: 1px solid var(--border, hsla(220, 15%, 22%, 1));
					border-radius: 0.75rem;
					padding: 1.25rem;
				}

				/* Accordion */
				.section-accordion {
					border: 1px solid var(--border, hsla(220, 15%, 22%, 1));
					border-radius: 0.5rem;
					overflow: hidden;
					margin-bottom: 0.5rem;
				}
				.section-accordion summary {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					padding: 0.65rem 0.9rem;
					cursor: pointer;
					list-style: none;
					user-select: none;
					font-size: 0.88rem;
					font-weight: 500;
					color: var(--text, hsla(220, 15%, 92%, 1));
					background: var(--surface-alt, hsla(220, 20%, 9%, 1));
					transition: background 0.15s;
					min-height: 2.75rem;
				}
				.section-accordion summary::-webkit-details-marker { display: none; }
				.section-accordion summary::marker { display: none; }
				.section-accordion summary:hover { background: var(--surface-hover, hsla(220, 20%, 14%, 1)); }
				.section-accordion summary:focus-visible {
					outline: 2px solid var(--focus-ring, hsla(175, 80%, 40%, 1));
					outline-offset: -2px;
				}
				.section-accordion[open] summary { border-bottom: 1px solid var(--border, hsla(220, 15%, 22%, 1)); }
				.section-name { flex: 1; }
				.section-badge {
					font-size: 0.7rem;
					padding: 0.1rem 0.45rem;
					border-radius: 0.8rem;
					background: var(--accent-faint, hsla(175, 80%, 40%, 0.15));
					color: var(--accent, hsla(175, 80%, 40%, 1));
					font-weight: 600;
				}
				.section-chevron {
					font-size: 0.7rem;
					color: var(--text-muted, hsla(220, 15%, 55%, 1));
					transition: transform 0.2s;
				}
				details[open] .section-chevron { transform: rotate(90deg); }
				.section-body { padding: 0.5rem 0.9rem 0.75rem; }

				/* Item list */
				.item-list {
					list-style: none;
					padding: 0;
					margin: 0;
					max-height: 18rem;
					overflow-y: auto;
				}
				.item-row {
					display: flex;
					align-items: flex-start;
					gap: 0.5rem;
					padding: 0.35rem 0.25rem;
					border-bottom: 1px solid var(--border-faint, hsla(220, 15%, 16%, 1));
					font-size: 0.8rem;
					color: var(--text, hsla(220, 15%, 88%, 1));
				}
				.item-row:last-child { border-bottom: none; }
				.item-row input[type="checkbox"] {
					flex-shrink: 0;
					width: 1rem;
					height: 1rem;
					margin-top: 0.1rem;
					accent-color: var(--accent, hsla(175, 80%, 40%, 1));
					cursor: pointer;
				}
				.item-row.excluded { opacity: 0.45; text-decoration: line-through; }
				.item-text { word-break: break-word; min-width: 0; }
				.type-badge {
					font-size: 0.65rem;
					padding: 0.05rem 0.35rem;
					border-radius: 0.3rem;
					background: var(--surface-alt, hsla(220, 20%, 9%, 1));
					color: var(--text-muted, hsla(220, 15%, 60%, 1));
					border: 1px solid var(--border, hsla(220, 15%, 22%, 1));
					flex-shrink: 0;
				}
				.section-actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; flex-wrap: wrap; }

				/* Summary bar */
				.summary-bar {
					background: var(--surface-alt, hsla(220, 20%, 9%, 1));
					border: 1px solid var(--border, hsla(220, 15%, 22%, 1));
					border-radius: 0.5rem;
					padding: 0.6rem 0.9rem;
					font-size: 0.82rem;
					color: var(--text, hsla(220, 15%, 88%, 1));
					margin-top: 0.75rem;
					display: flex;
					align-items: center;
					gap: 0.5rem;
					flex-wrap: wrap;
				}
				.summary-kb { color: var(--text-muted, hsla(220, 15%, 55%, 1)); font-size: 0.78rem; }

				/* Hard excluded */
				.hard-excluded {
					margin-top: 0.75rem;
					border: 1px dashed var(--border, hsla(220, 15%, 22%, 1));
					border-radius: 0.5rem;
					opacity: 0.65;
				}
				.hard-excluded summary {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					padding: 0.5rem 0.75rem;
					cursor: pointer;
					list-style: none;
					font-size: 0.78rem;
					color: var(--text-muted, hsla(220, 15%, 60%, 1));
					user-select: none;
					min-height: 2.75rem;
				}
				.hard-excluded summary::-webkit-details-marker { display: none; }
				.hard-excluded summary:focus-visible {
					outline: 2px solid var(--focus-ring, hsla(175, 80%, 40%, 1));
					outline-offset: -2px;
				}
				.hard-excluded p { padding: 0.5rem 0.75rem; font-size: 0.78rem; color: var(--text-muted, hsla(220, 15%, 55%, 1)); margin: 0; }

				/* Form fields */
				.field { display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 0.85rem; }
				label { font-size: 0.8rem; color: var(--text-muted, hsla(220, 15%, 60%, 1)); font-weight: 500; }
				input[type="password"],
				input[type="file"] {
					background: var(--input-bg, hsla(220, 20%, 8%, 1));
					border: 1px solid var(--border, hsla(220, 15%, 22%, 1));
					border-radius: 0.5rem;
					color: var(--text, hsla(220, 15%, 92%, 1));
					font-size: 0.9rem;
					min-height: 2.75rem;
					padding: 0.5rem 0.75rem;
					width: 100%;
					box-sizing: border-box;
					transition: border-color 0.15s;
				}
				input[type="file"] { padding: 0.4rem 0.6rem; cursor: pointer; }
				input:focus-visible {
					border-color: var(--accent, hsla(175, 80%, 40%, 1));
					outline: 2px solid var(--accent-faint, hsla(175, 80%, 40%, 0.25));
					outline-offset: 0;
				}

				/* Strength bar */
				.strength-wrap {
					height: 0.3rem;
					background: var(--border, hsla(220, 15%, 22%, 1));
					border-radius: 1rem;
					overflow: hidden;
					margin-top: 0.3rem;
				}
				.strength-bar { height: 100%; border-radius: 1rem; transition: width 0.3s ease, background-color 0.3s ease; }
				.strength-label { font-size: 0.73rem; margin-top: 0.2rem; }
				.strength-label.weak   { color: var(--red, hsla(0, 75%, 55%, 1)); }
				.strength-label.ok     { color: var(--orange, hsla(30, 90%, 55%, 1)); }
				.strength-label.strong { color: var(--green, hsla(145, 65%, 45%, 1)); }

				/* Error / status */
				.error-msg { font-size: 0.78rem; color: var(--red, hsla(0, 75%, 55%, 1)); margin-top: 0.3rem; }
				.status-box {
					background: var(--surface-alt, hsla(220, 20%, 9%, 1));
					border: 1px solid var(--border, hsla(220, 15%, 22%, 1));
					border-radius: 0.5rem;
					padding: 0.75rem 1rem;
					font-size: 0.85rem;
					margin-top: 0.75rem;
					color: var(--text, hsla(220, 15%, 88%, 1));
				}
				.status-box.is-error   { border-color: var(--red, hsla(0, 75%, 55%, 1));     color: var(--red, hsla(0, 75%, 55%, 1)); }
				.status-box.is-success { border-color: var(--green, hsla(145, 65%, 45%, 1)); color: var(--green, hsla(145, 65%, 45%, 1)); }

				/* Spinner */
				.spinner {
					display: inline-block;
					width: 0.9rem;
					height: 0.9rem;
					border: 2px solid var(--border, hsla(220, 15%, 22%, 1));
					border-top-color: var(--accent, hsla(175, 80%, 40%, 1));
					border-radius: 50%;
					animation: spin 0.7s linear infinite;
					vertical-align: middle;
					margin-right: 0.35rem;
				}
				@keyframes spin { to { transform: rotate(360deg); } }

				/* Buttons */
				.btn-row { display: flex; gap: 0.5rem; margin-top: 0.75rem; flex-wrap: wrap; }
				.top-actions { display: flex; justify-content: flex-end; margin-bottom: 1rem; }

				/* Import result */
				.import-result-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; margin-top: 0.5rem; }
				.result-cell {
					background: var(--surface, hsla(220, 20%, 12%, 1));
					border: 1px solid var(--border, hsla(220, 15%, 22%, 1));
					border-radius: 0.4rem;
					padding: 0.4rem 0.6rem;
					font-size: 0.78rem;
				}
				.result-cell .num { font-size: 1rem; font-weight: 600; color: var(--accent, hsla(175, 80%, 40%, 1)); display: block; }
				.result-cell .lbl { color: var(--text-muted, hsla(220, 15%, 60%, 1)); }
				.error-list {
					list-style: none; padding: 0; margin: 0.5rem 0 0;
					max-height: 10rem; overflow-y: auto; font-size: 0.77rem;
				}
				.error-list li {
					padding: 0.25rem 0;
					border-bottom: 1px solid var(--border-faint, hsla(220, 15%, 16%, 1));
					word-break: break-all;
					color: var(--text-muted, hsla(220, 15%, 60%, 1));
				}
				.error-list .ek { color: var(--orange, hsla(30, 90%, 55%, 1)); font-weight: 500; }

				/* Dialog */
				dialog {
					background: var(--surface, hsla(220, 20%, 14%, 1));
					border: 1px solid var(--border, hsla(220, 15%, 28%, 1));
					border-radius: 0.75rem;
					color: var(--text, hsla(220, 15%, 92%, 1));
					padding: 1.5rem;
					max-width: min(42rem, 92vw);
					width: 100%;
					font-size: 0.875rem;
					box-shadow: 0 8px 32px hsla(220, 30%, 5%, 0.6);
				}
				dialog::backdrop { background: hsla(220, 30%, 5%, 0.65); backdrop-filter: blur(3px); }
				dialog h3 { font-size: 1rem; font-weight: 600; margin: 0 0 1rem; color: var(--text, hsla(220, 15%, 92%, 1)); }
				.dialog-section { margin-bottom: 0.75rem; }
				.dialog-section > label { font-size: 0.8rem; color: var(--text-muted, hsla(220, 15%, 60%, 1)); font-weight: 500; display: block; margin-bottom: 0.4rem; }
				.radio-group { display: flex; flex-direction: column; gap: 0.35rem; }
				.radio-group label {
					display: flex; align-items: center; gap: 0.4rem;
					cursor: pointer; font-size: 0.85rem;
					color: var(--text, hsla(220, 15%, 88%, 1));
					font-weight: 400; min-height: 2.75rem;
				}
				.radio-group input[type="radio"] {
					accent-color: var(--accent, hsla(175, 80%, 40%, 1));
					width: 1rem; height: 1rem; min-height: unset; padding: 0;
				}
				.checkbox-opt {
					display: flex; align-items: center; gap: 0.4rem;
					cursor: pointer; font-size: 0.85rem;
					color: var(--text, hsla(220, 15%, 88%, 1)); min-height: 2.75rem;
				}
				.checkbox-opt input[type="checkbox"] {
					accent-color: var(--accent, hsla(175, 80%, 40%, 1));
					width: 1rem; height: 1rem; cursor: pointer;
				}

				@media (prefers-reduced-motion: reduce) {
					.strength-bar { transition: none; }
					.spinner { animation: none; border-top-color: var(--accent, hsla(175, 80%, 40%, 1)); }
					.section-chevron { transition: none; }
				}
				@media (forced-colors: active) {
					input { border-color: ButtonText; }
					.section-badge { border: 1px solid ButtonText; }
					.strength-bar { background: Highlight; }
					dialog { border-color: ButtonText; }
				}
			</style>

			<div class="card" role="region" aria-label="${this.esc(this.tr('aria_backup_card', 'Backup and restore panel'))}">
				<h2>
					<span class="h-icon" aria-hidden="true">&#128190;</span>
					${this.esc(this.tr('backup_card_title', 'Backup'))}
					<span class="subtitle">${this.esc(this.tr('backup_card_description', 'Export and import your personal data'))}</span>
				</h2>
				<div id="stage-root">${this._renderStage()}</div>
				${this._renderImportDialog()}
			</div>
		`;
		this._bindEvents();
	}

	private _renderStage(): string {
		switch (this.stage) {
			case 'preview':    return this._renderPreview();
			case 'passphrase': return this._renderPassphrase();
			case 'import':     return this._renderImport();
			default:           return '';
		}
	}

	// ── Preview stage ─────────────────────────────────────────────────────────

	private _renderPreview(): string {
		const accordions = (SECTIONS as readonly string[]).map(s => this._renderAccordion(s)).join('');
		const selectedCount = this._selectedCount();
		const sectionCount = this._sectionsWithItems();
		const kb = this._estimateSizeKb();
		const summaryText = this.tr('backup_items_selected', '{n} items selected across {s} sections')
			.replace('{n}', String(selectedCount)).replace('{s}', String(sectionCount));
		const kbText = kb > 0 ? this.tr('backup_size_estimate', '~{kb} KB').replace('{kb}', String(kb)) : '';

		return `
			<div class="top-actions">
				<button class="btn btn-ghost" id="btn-open-import"
					aria-label="${this.esc(this.tr('backup_import_title', 'Import Backup'))}">
					${this.esc(this.tr('backup_import_title', 'Import Backup'))}
				</button>
			</div>
			${accordions}
			<div class="summary-bar" id="summary-bar" role="status" aria-live="polite" aria-label="${this.esc(summaryText)}">
				<span>${this.esc(summaryText)}</span>
				${kbText ? `<span class="summary-kb">${this.esc(kbText)}</span>` : ''}
			</div>
			<details class="hard-excluded">
				<summary>
					<span aria-hidden="true">&#128683;</span>
					${this.esc(this.tr('backup_hard_excluded_title', 'Never included'))}
				</summary>
				<p>${this.esc(this.tr('backup_hard_excluded_desc', 'Chat history, OAuth tokens, credentials, widget config'))}</p>
			</details>
			<div class="btn-row">
				<button class="btn btn-primary" id="btn-continue-export"
					${selectedCount === 0 ? 'disabled aria-disabled="true"' : ''}
					aria-label="${this.esc(this.tr('backup_continue_export', 'Continue to export'))}">
					${this.esc(this.tr('backup_continue_export', 'Continue to export'))}
				</button>
			</div>
		`;
	}

	private _renderAccordion(section: string): string {
		const state = this.sectionState[section];
		const label = this._sectionLabel(section);
		const isOpen = this.expandedSections.has(section);
		const badge = state.loaded ? String(state.total) : (isOpen && state.loading ? '\u2026' : '?');
		const ariaSection = this.tr('aria_backup_section', 'Backup section: {name}').replace('{name}', label);
		return `
			<details class="section-accordion" id="details-${section}" ${isOpen ? 'open' : ''}
				aria-label="${this.esc(ariaSection)}">
				<summary aria-expanded="${isOpen}">
					<span class="section-name">${this.esc(label)}</span>
					<span class="section-badge">${this.esc(badge)}</span>
					<span class="section-chevron" aria-hidden="true">&#9656;</span>
				</summary>
				<div class="section-body" id="section-body-${section}">
					${this._renderSectionBody(section)}
				</div>
			</details>
		`;
	}

	private _renderSectionBody(section: string): string {
		const state = this.sectionState[section];
		const label = this._sectionLabel(section);
		if (state.loading && state.items.length === 0) {
			return `<div role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span>${this.esc(this.tr('backup_loading', 'Loading...'))}</div>`;
		}
		if (state.error) {
			return `<div class="error-msg" role="alert">${this.esc(state.error)}</div>`;
		}
		if (!state.loaded && state.items.length === 0) {
			return `<div class="section-actions">
				<button class="btn btn-ghost" data-action="load-section" data-section="${this.esc(section)}"
					aria-label="${this.esc(this.tr('backup_load_section', 'Load'))} ${this.esc(label)}">${this.esc(this.tr('backup_load_section', 'Load'))}</button>
				<button class="btn btn-ghost" data-action="load-all" data-section="${this.esc(section)}"
					aria-label="${this.esc(this.tr('backup_load_all', 'Load all'))} ${this.esc(label)}">${this.esc(this.tr('backup_load_all', 'Load all'))}</button>
			</div>`;
		}
		const rows = state.items.map(item => {
			const key = this._getItemKey(section, item);
			const isExcluded = this.excluded_paths.has(key);
			const displayText = this.esc(this._renderItemText(section, item));
			const cbLabel = this.tr('aria_backup_item_checkbox', 'Include {name} in backup')
				.replace('{name}', this._renderItemText(section, item).slice(0, 60));
			const cbTitle = isExcluded
				? this.tr('backup_item_include', 'Include in backup')
				: this.tr('backup_item_exclude', 'Exclude from backup');
			const typeBadge = item.type ? `<span class="type-badge">${this.esc(String(item.type))}</span>` : '';
			return `<li class="item-row${isExcluded ? ' excluded' : ''}">
				<input type="checkbox" data-item-key="${this.esc(key)}" data-section="${this.esc(section)}"
					${!isExcluded ? 'checked' : ''} aria-label="${this.esc(cbLabel)}" title="${this.esc(cbTitle)}" />
				${typeBadge}<span class="item-text">${displayText}</span>
			</li>`;
		}).join('');
		const loadingMore = state.loading ? `<div role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span></div>` : '';
		const hasMore = state.nextCursor !== null;
		const dis = state.loading ? 'disabled aria-disabled="true"' : '';
		return `
			<ul class="item-list" aria-label="${this.esc(label)}">${rows}</ul>
			${loadingMore}
			<div class="section-actions">
				${hasMore ? `<button class="btn btn-ghost" data-action="load-more" data-section="${this.esc(section)}"
					aria-label="${this.esc(this.tr('backup_load_more', 'Load more'))} ${this.esc(label)}" ${dis}>${this.esc(this.tr('backup_load_more', 'Load more'))}</button>` : ''}
				${!state.loaded ? `<button class="btn btn-ghost" data-action="load-all" data-section="${this.esc(section)}"
					aria-label="${this.esc(this.tr('backup_load_all', 'Load all'))} ${this.esc(label)}" ${dis}>${this.esc(this.tr('backup_load_all', 'Load all'))}</button>` : ''}
			</div>
		`;
	}

	// ── Passphrase stage ──────────────────────────────────────────────────────

	private _renderPassphrase(): string {
		const s = this.passphraseStrength;
		const pct = s === 0 ? 25 : s === 1 ? 60 : 100;
		const barColor = s === 0 ? 'var(--red, hsla(0,75%,55%,1))' : s === 1 ? 'var(--orange, hsla(30,90%,55%,1))' : 'var(--green, hsla(145,65%,45%,1))';
		const sKey = s === 0 ? 'backup_passphrase_strength_weak' : s === 1 ? 'backup_passphrase_strength_ok' : 'backup_passphrase_strength_strong';
		const sFb  = s === 0 ? 'Weak' : s === 1 ? 'OK' : 'Strong';
		const sLabel = this.tr(sKey, sFb);
		const sCls   = s === 0 ? 'weak' : s === 1 ? 'ok' : 'strong';
		const ariaStrength = this.tr('aria_backup_strength', 'Passphrase strength: {level}').replace('{level}', sLabel);
		return `
			<div class="field">
				<label for="export-passphrase">${this.esc(this.tr('backup_passphrase_label', 'Passphrase'))}</label>
				<input type="password" id="export-passphrase" autocomplete="new-password"
					placeholder="${this.esc(this.tr('backup_passphrase_placeholder', 'Min 12 characters'))}"
					aria-label="${this.esc(this.tr('backup_passphrase_label', 'Passphrase'))}"
					aria-describedby="strength-label" minlength="12" maxlength="256" />
				<div class="strength-wrap" id="strength-wrap" role="progressbar"
					aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100" aria-label="${this.esc(ariaStrength)}">
					<div class="strength-bar" id="strength-bar" style="width:${pct}%;background-color:${barColor};"></div>
				</div>
				<span id="strength-label" class="strength-label ${sCls}" aria-live="polite">${this.esc(sLabel)}</span>
				<span id="passphrase-error" class="error-msg" aria-live="assertive" style="display:none;">
					${this.esc(this.tr('backup_passphrase_too_short', 'Passphrase must be at least 12 characters'))}
				</span>
			</div>
			<div class="field">
				<label for="export-passphrase-confirm">${this.esc(this.tr('backup_passphrase_confirm', 'Confirm passphrase'))}</label>
				<input type="password" id="export-passphrase-confirm" autocomplete="new-password"
					aria-label="${this.esc(this.tr('backup_passphrase_confirm', 'Confirm passphrase'))}"
					aria-describedby="mismatch-error" maxlength="256" />
				<span id="mismatch-error" class="error-msg" aria-live="assertive" style="display:none;">
					${this.esc(this.tr('backup_passphrase_mismatch', 'Passphrases do not match'))}
				</span>
			</div>
			${this.exportError ? `<div class="status-box is-error" role="alert" aria-live="assertive">${this.esc(this.exportError)}</div>` : ''}
			${this.exportGenerating ? `<div class="status-box" role="status" aria-live="polite" aria-label="${this.esc(this.tr('aria_backup_export_progress', 'Generating backup file'))}"><span class="spinner" aria-hidden="true"></span>${this.esc(this.tr('backup_export_generating', 'Generating...'))}</div>` : ''}
			${this.exportDone ? `<div class="status-box is-success" role="status" aria-live="polite">${this.esc(this.tr('backup_export_done', 'Backup downloaded'))}</div>` : ''}
			<div class="btn-row">
				<button class="btn btn-primary" id="btn-do-export"
					${this.exportGenerating ? 'disabled aria-disabled="true"' : ''}
					aria-label="${this.esc(this.tr('backup_export_button', 'Export'))}">
					${this.esc(this.tr('backup_export_button', 'Export'))}
				</button>
				<button class="btn btn-ghost" id="btn-back" aria-label="${this.esc(this.tr('backup_back', 'Back'))}">
					${this.esc(this.tr('backup_back', 'Back'))}
				</button>
			</div>
		`;
	}

	// ── Import stage ──────────────────────────────────────────────────────────

	private _renderImport(): string {
		return `
			<div class="field">
				<label for="import-file">${this.esc(this.tr('backup_import_pick_file', 'Choose .ozbackup file'))}</label>
				<input type="file" id="import-file" accept=".ozbackup"
					aria-label="${this.esc(this.tr('aria_backup_file_input', 'Choose backup file to import'))}" />
			</div>
			<div class="field">
				<label for="import-passphrase">${this.esc(this.tr('backup_import_passphrase', 'Backup passphrase'))}</label>
				<input type="password" id="import-passphrase" autocomplete="current-password"
					aria-label="${this.esc(this.tr('backup_import_passphrase', 'Backup passphrase'))}" maxlength="256" />
			</div>
			${this.importError ? `<div class="status-box is-error" role="alert" aria-live="assertive">${this.esc(this.importError)}</div>` : ''}
			${this.importGenerating ? `<div class="status-box" role="status" aria-live="polite" aria-label="${this.esc(this.tr('aria_backup_import_progress', 'Importing backup'))}"><span class="spinner" aria-hidden="true"></span>${this.esc(this.tr('backup_import_progress', 'Importing...'))}</div>` : ''}
			${this.importDone && this.importResult ? this._renderImportResult(this.importResult) : ''}
			<div class="btn-row">
				<button class="btn btn-primary" id="btn-dry-run"
					${this.importGenerating ? 'disabled aria-disabled="true"' : ''}
					aria-label="${this.esc(this.tr('backup_import_preview', 'Preview import'))}">
					${this.esc(this.tr('backup_import_preview', 'Preview import'))}
				</button>
				<button class="btn btn-ghost" id="btn-back" aria-label="${this.esc(this.tr('backup_back', 'Back'))}">
					${this.esc(this.tr('backup_back', 'Back'))}
				</button>
			</div>
		`;
	}

	private _renderImportResult(report: ImportReport): string {
		const totalCreated = Object.values(report.created).reduce((a, b) => a + b, 0);
		const totalSkipped = Object.values(report.skipped).reduce((a, b) => a + b, 0);
		const totalErrors  = report.errors.length;
		const createdLabel = this.tr('backup_import_created', '{n} to create').replace('{n}', String(totalCreated));
		const skippedLabel = this.tr('backup_import_skipped', '{n} to skip').replace('{n}', String(totalSkipped));
		const errorsLabel  = this.tr('backup_import_errors_n', '{n} errors').replace('{n}', String(totalErrors));
		const done = this.tr('backup_import_done', 'Import complete');
		const errorItems = report.errors.slice(0, 30).map(e =>
			`<li><span class="ek">[${this.esc(e.kind)}]</span> ${this.esc(e.path)}: ${this.esc(e.reason.slice(0, 200))}</li>`
		).join('');
		return `
			<div class="status-box${totalErrors > 0 ? ' is-error' : ' is-success'}" role="status" aria-live="polite">
				${this.esc(done)} (${report.duration_ms}ms)
			</div>
			<div class="import-result-grid">
				<div class="result-cell"><span class="num">${totalCreated}</span><span class="lbl">${this.esc(createdLabel)}</span></div>
				<div class="result-cell"><span class="num">${totalSkipped}</span><span class="lbl">${this.esc(skippedLabel)}</span></div>
				<div class="result-cell"><span class="num">${totalErrors}</span><span class="lbl">${this.esc(errorsLabel)}</span></div>
			</div>
			${errorItems ? `<ul class="error-list" aria-label="${this.esc(this.tr('backup_errors', 'Errors'))}">${errorItems}</ul>` : ''}
		`;
	}

	// ── Dialog ────────────────────────────────────────────────────────────────

	private _renderImportDialog(): string {
		return `
			<dialog id="import-dialog" aria-labelledby="dialog-title" aria-modal="true">
				<h3 id="dialog-title">${this.esc(this.tr('backup_import_dry_run_title', 'Import preview'))}</h3>
				<div id="dialog-content"></div>
				<div class="dialog-section">
					<label>${this.esc(this.tr('backup_import_conflict_label', 'On conflict'))}</label>
					<div class="radio-group" role="radiogroup" aria-label="${this.esc(this.tr('backup_import_conflict_label', 'On conflict'))}">
						<label><input type="radio" name="dialog-conflict" value="skip" ${this.importConflict === 'skip' ? 'checked' : ''} aria-label="${this.esc(this.tr('backup_conflict_skip', 'Skip (default)'))}"/> ${this.esc(this.tr('backup_conflict_skip', 'Skip (default)'))}</label>
						<label><input type="radio" name="dialog-conflict" value="merge" ${this.importConflict === 'merge' ? 'checked' : ''} aria-label="${this.esc(this.tr('backup_conflict_merge', 'Merge'))}"/> ${this.esc(this.tr('backup_conflict_merge', 'Merge'))}</label>
						<label><input type="radio" name="dialog-conflict" value="replace" ${this.importConflict === 'replace' ? 'checked' : ''} aria-label="${this.esc(this.tr('backup_conflict_replace', 'Replace (destructive)'))}"/> ${this.esc(this.tr('backup_conflict_replace', 'Replace (destructive)'))}</label>
					</div>
				</div>
				<div class="dialog-section">
					<label>${this.esc(this.tr('backup_import_section_opts', 'Import sections'))}</label>
					<label class="checkbox-opt">
						<input type="checkbox" id="dialog-prefs-opt" ${this.importPrefsOpt ? 'checked' : ''}
							aria-label="${this.esc(this.tr('backup_import_prefs_opt', 'Preferences (not recommended for fresh instances)'))}"/>
						${this.esc(this.tr('backup_import_prefs_opt', 'Preferences (not recommended for fresh instances)'))}
					</label>
				</div>
				<div class="btn-row">
					<button class="btn btn-primary" id="btn-confirm-import" aria-label="${this.esc(this.tr('backup_import_confirm', 'Confirm import'))}">
						${this.esc(this.tr('backup_import_confirm', 'Confirm import'))}
					</button>
					<button class="btn btn-ghost" id="btn-cancel-import" aria-label="${this.esc(this.tr('backup_import_cancel', 'Cancel'))}">
						${this.esc(this.tr('backup_import_cancel', 'Cancel'))}
					</button>
				</div>
			</dialog>
		`;
	}

	// ── Event binding ─────────────────────────────────────────────────────────

	private _bindEvents() {
		const root = this.shadowRoot as ShadowRoot;
		const get = (id: string) => root.getElementById(id);

		if (this.stage === 'preview') {
			get('btn-continue-export')?.addEventListener('click', () => {
				this.stage = 'passphrase';
				this.exportError = '';
				this.exportDone = false;
				this._updateStage();
			});
			get('btn-open-import')?.addEventListener('click', (e) => {
				this._importDialogTrigger = e.currentTarget as HTMLElement;
				this.stage = 'import';
				this.importDone = false;
				this.importResult = null;
				this.importError = '';
				this.importFile = null;
				this._updateStage();
			});
			for (const section of SECTIONS) {
				const details = root.getElementById(`details-${section}`) as HTMLDetailsElement | null;
				if (!details) continue;
				details.addEventListener('toggle', () => {
					const summary = details.querySelector('summary');
					if (details.open) {
						this.expandedSections.add(section);
						summary?.setAttribute('aria-expanded', 'true');
						const st = this.sectionState[section];
						if (!st.loaded && !st.loading) this._loadSection(section, false);
					} else {
						this.expandedSections.delete(section);
						summary?.setAttribute('aria-expanded', 'false');
					}
				});
				const body = root.getElementById(`section-body-${section}`);
				if (body) this._bindSectionBodyEvents(body, section);
			}
		}

		if (this.stage === 'passphrase') {
			const passEl    = get('export-passphrase')         as HTMLInputElement | null;
			const confirmEl = get('export-passphrase-confirm') as HTMLInputElement | null;
			passEl?.addEventListener('input', () => {
				if (this._strengthDebounce) clearTimeout(this._strengthDebounce);
				this._strengthDebounce = setTimeout(() => {
					if (!passEl) return;
					this.passphraseStrength = this._computeStrength(passEl.value);
					this._updateStrengthIndicator();
				}, 250);
			});
			confirmEl?.addEventListener('input', () => {
				const mismatch = root.getElementById('mismatch-error') as HTMLElement | null;
				if (mismatch && passEl && confirmEl) {
					mismatch.style.display = (passEl.value !== confirmEl.value && confirmEl.value.length > 0) ? 'block' : 'none';
				}
			});
			get('btn-do-export')?.addEventListener('click', () => this._doExport());
			get('btn-back')?.addEventListener('click', () => {
				this.stage = 'preview';
				this.exportError = '';
				this.exportDone = false;
				this._updateStage();
			});
		}

		if (this.stage === 'import') {
			const fileEl = get('import-file') as HTMLInputElement | null;
			fileEl?.addEventListener('change', () => { this.importFile = fileEl.files?.[0] ?? null; });
			get('btn-dry-run')?.addEventListener('click', () => this._doDryRun());
			get('btn-back')?.addEventListener('click', () => {
				this.stage = 'preview';
				this.importError = '';
				this.importGenerating = false;
				this.importDone = false;
				this.importResult = null;
				this.importFile = null;
				this._updateStage();
			});
		}

		// Dialog events (always bind)
		const dialog = get('import-dialog') as HTMLDialogElement | null;
		if (dialog) {
			get('btn-cancel-import')?.addEventListener('click', () => this._closeDialog(dialog));
			get('btn-confirm-import')?.addEventListener('click', () => this._doImport(dialog));
			dialog.querySelectorAll<HTMLInputElement>('input[name="dialog-conflict"]').forEach(r => {
				r.addEventListener('change', (e) => { this.importConflict = (e.target as HTMLInputElement).value as ConflictMode; });
			});
			const prefsOpt = get('dialog-prefs-opt') as HTMLInputElement | null;
			prefsOpt?.addEventListener('change', () => { this.importPrefsOpt = prefsOpt.checked; });
			dialog.addEventListener('click', (e) => {
				const rect = dialog.getBoundingClientRect();
				if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
					this._closeDialog(dialog);
				}
			});
		}
	}

	private _bindSectionBodyEvents(body: HTMLElement, section: string) {
		body.querySelectorAll<HTMLElement>('[data-action]').forEach(btn => {
			btn.addEventListener('click', () => {
				const action = btn.getAttribute('data-action');
				if (action === 'load-section') this._loadSection(section, false);
				else if (action === 'load-all')  this._loadSection(section, true);
				else if (action === 'load-more') this._loadMoreSection(section);
			});
		});
		body.querySelectorAll<HTMLInputElement>('input[type="checkbox"][data-item-key]').forEach(cb => {
			cb.addEventListener('change', () => {
				const key = cb.dataset.itemKey ?? '';
				if (cb.checked) this.excluded_paths.delete(key);
				else            this.excluded_paths.add(key);
				const row = cb.closest('.item-row') as HTMLElement | null;
				row?.classList.toggle('excluded', !cb.checked);
				this._updateSummaryBar();
			});
		});
	}

	// ── Targeted DOM updates ──────────────────────────────────────────────────

	private _updateStage() {
		const root = this.shadowRoot as ShadowRoot;
		const savedExportPass    = (root.getElementById('export-passphrase')         as HTMLInputElement | null)?.value ?? '';
		const savedExportConfirm = (root.getElementById('export-passphrase-confirm') as HTMLInputElement | null)?.value ?? '';
		const savedImportPass    = (root.getElementById('import-passphrase')         as HTMLInputElement | null)?.value ?? '';
		const stageRoot = root.getElementById('stage-root');
		if (stageRoot) stageRoot.innerHTML = this._renderStage();
		this._bindEvents();
		if (this.stage === 'passphrase') {
			const ep  = root.getElementById('export-passphrase')         as HTMLInputElement | null;
			const epc = root.getElementById('export-passphrase-confirm') as HTMLInputElement | null;
			if (ep  && savedExportPass)    { ep.value  = savedExportPass;    this.passphraseStrength = this._computeStrength(savedExportPass); this._updateStrengthIndicator(); }
			if (epc && savedExportConfirm) { epc.value = savedExportConfirm; }
		}
		if (this.stage === 'import') {
			const ip = root.getElementById('import-passphrase') as HTMLInputElement | null;
			if (ip && savedImportPass) ip.value = savedImportPass;
		}
	}

	private _updateSectionBody(section: string) {
		const root = this.shadowRoot as ShadowRoot;
		const body = root.getElementById(`section-body-${section}`);
		if (body) {
			body.innerHTML = this._renderSectionBody(section);
			this._bindSectionBodyEvents(body, section);
		}
		const badge = root.querySelector<HTMLElement>(`#details-${section} .section-badge`);
		if (badge) {
			const st = this.sectionState[section];
			badge.textContent = st.loaded ? String(st.total) : '?';
		}
		this._updateSummaryBar();
	}

	private _updateSummaryBar() {
		const root = this.shadowRoot as ShadowRoot;
		const bar = root.getElementById('summary-bar');
		if (!bar) return;
		const selectedCount = this._selectedCount();
		const sectionCount  = this._sectionsWithItems();
		const kb = this._estimateSizeKb();
		const summaryText = this.tr('backup_items_selected', '{n} items selected across {s} sections')
			.replace('{n}', String(selectedCount)).replace('{s}', String(sectionCount));
		const kbText = kb > 0 ? this.tr('backup_size_estimate', '~{kb} KB').replace('{kb}', String(kb)) : '';
		bar.innerHTML = `<span>${this.esc(summaryText)}</span>${kbText ? `<span class="summary-kb">${this.esc(kbText)}</span>` : ''}`;
		bar.setAttribute('aria-label', summaryText);
		const btn = root.getElementById('btn-continue-export') as HTMLButtonElement | null;
		if (btn) { btn.disabled = selectedCount === 0; btn.setAttribute('aria-disabled', String(selectedCount === 0)); }
	}

	private _updateStrengthIndicator() {
		const root = this.shadowRoot as ShadowRoot;
		const s = this.passphraseStrength;
		const pct = s === 0 ? 25 : s === 1 ? 60 : 100;
		const barColor = s === 0 ? 'var(--red, hsla(0,75%,55%,1))' : s === 1 ? 'var(--orange, hsla(30,90%,55%,1))' : 'var(--green, hsla(145,65%,45%,1))';
		const sKey = s === 0 ? 'backup_passphrase_strength_weak' : s === 1 ? 'backup_passphrase_strength_ok' : 'backup_passphrase_strength_strong';
		const sLabel = this.tr(sKey, s === 0 ? 'Weak' : s === 1 ? 'OK' : 'Strong');
		const sCls   = s === 0 ? 'weak' : s === 1 ? 'ok' : 'strong';
		const ariaStrength = this.tr('aria_backup_strength', 'Passphrase strength: {level}').replace('{level}', sLabel);
		const bar  = root.getElementById('strength-bar')  as HTMLElement | null;
		const wrap = root.getElementById('strength-wrap') as HTMLElement | null;
		const lbl  = root.getElementById('strength-label') as HTMLElement | null;
		if (bar)  { bar.style.width = `${pct}%`; bar.style.backgroundColor = barColor; }
		if (wrap) { wrap.setAttribute('aria-valuenow', String(pct)); wrap.setAttribute('aria-label', ariaStrength); }
		if (lbl)  { lbl.textContent = sLabel; lbl.className = `strength-label ${sCls}`; }
	}

	// ── Data loading ──────────────────────────────────────────────────────────

	private async _loadSection(section: string, loadAll: boolean) {
		const state = this.sectionState[section];
		if (state.loading) return;
		state.loading = true;
		state.error = null;
		this._updateSectionBody(section);
		try {
			const suffix = loadAll ? '&load_all=true' : '';
			const url = `/api/dashboard/backup/preview?section=${encodeURIComponent(section)}&cursor=0&limit=50${suffix}`;
			const res = await fetch(url);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const page = await res.json();
			state.items      = page.items ?? [];
			state.total      = page.total ?? state.items.length;
			state.nextCursor = loadAll ? null : (page.next_cursor ?? null);
			state.loaded     = loadAll || page.next_cursor === null;
		} catch (err) {
			state.error = String(err).slice(0, 200);
		} finally {
			state.loading = false;
			this._updateSectionBody(section);
		}
	}

	private async _loadMoreSection(section: string) {
		const state = this.sectionState[section];
		if (state.loading || state.nextCursor === null) return;
		state.loading = true;
		this._updateSectionBody(section);
		try {
			const url = `/api/dashboard/backup/preview?section=${encodeURIComponent(section)}&cursor=${state.nextCursor}&limit=50`;
			const res = await fetch(url);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const page = await res.json();
			state.items      = [...state.items, ...(page.items ?? [])];
			state.total      = page.total ?? state.items.length;
			state.nextCursor = page.next_cursor ?? null;
			state.loaded     = state.nextCursor === null;
		} catch (err) {
			state.error = String(err).slice(0, 200);
		} finally {
			state.loading = false;
			this._updateSectionBody(section);
		}
	}

	// ── Export ────────────────────────────────────────────────────────────────

	private async _doExport() {
		const root = this.shadowRoot as ShadowRoot;
		const passEl    = root.getElementById('export-passphrase')         as HTMLInputElement | null;
		const confirmEl = root.getElementById('export-passphrase-confirm') as HTMLInputElement | null;
		if (!passEl || !confirmEl) return;
		const pass    = passEl.value;
		const confirm = confirmEl.value;
		const shortErr    = root.getElementById('passphrase-error') as HTMLElement | null;
		const mismatchErr = root.getElementById('mismatch-error')   as HTMLElement | null;
		if (pass.length < 12) { if (shortErr) shortErr.style.display = 'block'; return; }
		if (shortErr) shortErr.style.display = 'none';
		if (pass !== confirm) { if (mismatchErr) mismatchErr.style.display = 'block'; return; }
		if (mismatchErr) mismatchErr.style.display = 'none';
		this.exportGenerating = true;
		this.exportError = '';
		this.exportDone  = false;
		this._updateStage();
		try {
			const res = await fetch('/api/dashboard/backup/export', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ passphrase: pass, excluded_paths: [...this.excluded_paths] }),
			});
			if (!res.ok) { this.exportError = (await res.text()).slice(0, 300); this.exportGenerating = false; this._updateStage(); return; }
			const blob = await res.blob();
			const cd = res.headers.get('Content-Disposition') || '';
			const fnMatch = cd.match(/filename="([^"]+)"/);
			const filename = fnMatch ? fnMatch[1] : 'openzero-backup.ozbackup';
			const a = document.createElement('a');
			a.href = URL.createObjectURL(blob);
			a.download = filename;
			document.body.appendChild(a);
			a.click();
			setTimeout(() => { URL.revokeObjectURL(a.href); document.body.removeChild(a); }, 1000);
			this.exportDone  = true;
			this.exportGenerating = false;
			this._updateStage();
		} catch (err) {
			this.exportError = String(err).slice(0, 200);
			this.exportGenerating = false;
			this._updateStage();
		}
	}

	// ── Import ────────────────────────────────────────────────────────────────

	private async _doDryRun() {
		const root   = this.shadowRoot as ShadowRoot;
		const fileEl = root.getElementById('import-file')       as HTMLInputElement | null;
		const passEl = root.getElementById('import-passphrase') as HTMLInputElement | null;
		if (!this.importFile && fileEl?.files?.[0]) this.importFile = fileEl.files[0];
		if (!this.importFile) { this.importError = this.tr('backup_import_pick_file', 'Choose .ozbackup file'); this._updateStage(); return; }
		const pass = passEl?.value || '';
		if (!pass) { this.importError = this.tr('backup_import_passphrase', 'Backup passphrase'); this._updateStage(); return; }
		this.importGenerating = true;
		this.importError = '';
		this._updateStage();
		try {
			const form = new FormData();
			form.append('file',         this.importFile);
			form.append('passphrase',   pass);
			form.append('dry_run',      'true');
			form.append('conflict',     this.importConflict);
			form.append('section_opts', JSON.stringify({ preferences: this.importPrefsOpt }));
			const res = await fetch('/api/dashboard/backup/import', { method: 'POST', body: form });
			if (!res.ok) { this.importError = (await res.text()).slice(0, 300); this.importGenerating = false; this._updateStage(); return; }
			this.dryRunReport     = await res.json();
			this.importGenerating = false;
			this._updateStage();
			const dialog = root.getElementById('import-dialog') as HTMLDialogElement | null;
			if (dialog) {
				this._importDialogTrigger = root.getElementById('btn-dry-run');
				const content = dialog.querySelector<HTMLElement>('#dialog-content');
				if (content && this.dryRunReport) content.innerHTML = this._renderImportResult(this.dryRunReport);
				dialog.showModal();
				const first = dialog.querySelector<HTMLElement>('button, input, [tabindex]');
				first?.focus();
			}
		} catch (err) {
			this.importError      = String(err).slice(0, 200);
			this.importGenerating = false;
			this._updateStage();
		}
	}

	private _closeDialog(dialog: HTMLDialogElement) {
		dialog.close();
		this._importDialogTrigger?.focus();
	}

	private async _doImport(dialog: HTMLDialogElement) {
		if (!this.importFile) return;
		const root   = this.shadowRoot as ShadowRoot;
		const passEl = root.getElementById('import-passphrase') as HTMLInputElement | null;
		const pass   = passEl?.value || '';
		if (!pass) return;
		const conflictRadio = dialog.querySelector<HTMLInputElement>('input[name="dialog-conflict"]:checked');
		if (conflictRadio) this.importConflict = conflictRadio.value as ConflictMode;
		const prefsOpt = dialog.querySelector<HTMLInputElement>('#dialog-prefs-opt');
		if (prefsOpt) this.importPrefsOpt = prefsOpt.checked;
		this._closeDialog(dialog);
		this.importGenerating = true;
		this.importError      = '';
		this.importDone       = false;
		this.importResult     = null;
		this._updateStage();
		try {
			const form = new FormData();
			form.append('file',         this.importFile);
			form.append('passphrase',   pass);
			form.append('dry_run',      'false');
			form.append('conflict',     this.importConflict);
			form.append('section_opts', JSON.stringify({ preferences: this.importPrefsOpt }));
			const headers: Record<string, string> = {};
			if (this.importConflict === 'replace') headers['X-Confirm-Destructive'] = 'yes';
			const res = await fetch('/api/dashboard/backup/import', { method: 'POST', body: form, headers });
			if (!res.ok) { this.importError = (await res.text()).slice(0, 300); this.importGenerating = false; this.importDone = false; this._updateStage(); return; }
			this.importResult     = await res.json();
			this.importDone       = true;
			this.importGenerating = false;
			this._updateStage();
		} catch (err) {
			this.importError      = String(err).slice(0, 200);
			this.importGenerating = false;
			this._updateStage();
		}
	}
}

declare global {
	interface Window {
		__z_translations?: Record<string, string>;
		__z_translations_ready?: Promise<void>;
	}
}

customElements.define('backup-card', BackupCard);
