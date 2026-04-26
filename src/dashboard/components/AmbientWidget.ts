import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';
import { EMPTY_STATE_STYLES } from '../services/emptyStateStyles';

interface AmbientStatus {
	enabled: boolean;
	pending_count: number;
	pending: AmbientSignal[];
	briefing_queue_depth: number;
	rate_count: number;
	rate_max: number;
	cooldowns: CooldownEntry[];
	error?: string;
}

interface AmbientSignal {
	rule_id: string;
	message?: string;
	priority?: number;
	severity?: number;
	source?: string;
	ts?: number;
	_key?: string;
}

interface CooldownEntry {
	rule_id: string;
	ttl_seconds: number;
}

interface AmbientConfig {
	enabled: boolean;
	poll_interval_s: number;
	max_triggers_per_hour: number;
	quiet_moment_window_m: number;
	briefing_queue_enabled: boolean;
}

export class AmbientWidget extends HTMLElement {
	private _status: AmbientStatus | null = null;
	private _config: AmbientConfig | null = null;
	private _error: string | null = null;
	private t: Record<string, string> = {};
	private _refreshTimer: ReturnType<typeof setInterval> | null = null;
	private _observer: IntersectionObserver | null = null;
	private _visible = false;
	private _onVisChange = () => this._handleVisibilityChange();

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.loadTranslations().then(() => {
			this.render();
			this.fetchAll();
		});
		this._observer = new IntersectionObserver(
			([entry]) => {
				this._visible = entry.isIntersecting;
				if (entry.isIntersecting && !document.hidden) {
					this._startPolling();
				} else {
					this._stopPolling();
				}
			},
			{ threshold: 0 }
		);
		this._observer.observe(this);
		document.addEventListener('visibilitychange', this._onVisChange);
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => {
				this.render();
				this.fetchAll();
			});
		});
	}

	disconnectedCallback() {
		this._stopPolling();
		if (this._observer) {
			this._observer.disconnect();
			this._observer = null;
		}
		document.removeEventListener('visibilitychange', this._onVisChange);
	}

	private _handleVisibilityChange() {
		if (document.hidden) {
			this._stopPolling();
		} else if (this._visible) {
			this._startPolling();
		}
	}

	private _startPolling() {
		if (this._refreshTimer) return;
		this._refreshTimer = setInterval(() => this.fetchAll(), 30000);
	}

	private _stopPolling() {
		if (this._refreshTimer) {
			clearInterval(this._refreshTimer);
			this._refreshTimer = null;
		}
	}

	private async loadTranslations() {
		if (window.__z_translations) { this.t = window.__z_translations; return; }
		try {
			const r = await fetch('/api/dashboard/translations');
			if (r.ok) this.t = await r.json();
		} catch (e) { console.error('Failed to load translations', e); }
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] ?? fallback;
	}

	private async fetchAll() {
		await Promise.all([this.fetchStatus(), this.fetchConfig()]);
		this.render();
	}

	private async fetchStatus() {
		try {
			const r = await fetch('/api/dashboard/ambient/status');
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			this._status = await r.json();
			this._error = this._status?.error ?? null;
		} catch (e: any) {
			this._error = e.message ?? 'Failed to load';
		}
	}

	private async fetchConfig() {
		try {
			const r = await fetch('/api/dashboard/ambient/config');
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			this._config = await r.json();
		} catch { /* non-critical */ }
	}

	private async dismissSignal(key: string) {
		try {
			await fetch(`/api/dashboard/ambient/dismiss-pending?rule_id=${encodeURIComponent(key)}`, { method: 'POST' });
			await this.fetchStatus();
			this.render();
		} catch { /* silent */ }
	}

	private _priorityColor(priority: number): string {
		if (priority <= 1) return 'var(--color-error-h, 0), var(--color-error-s, 84%), var(--color-error-l, 60%)';
		if (priority <= 2) return '30, 90%, 58%';
		if (priority <= 3) return '48, 95%, 55%';
		return '220, 20%, 55%';
	}

	private _severityWidth(severity: number): string {
		const pct = Math.round(Math.max(0, Math.min(1, severity)) * 100);
		return `${pct}%`;
	}

	private _severityBarColor(severity: number): string {
		if (severity > 0.7) return 'hsla(var(--color-error-h, 0), var(--color-error-s, 84%), var(--color-error-l, 60%), 0.85)';
		if (severity > 0.4) return 'hsla(30, 90%, 58%, 0.85)';
		return 'hsla(48, 95%, 55%, 0.8)';
	}

	private _formatTtl(seconds: number): string {
		if (seconds <= 0) return '—';
		const m = Math.floor(seconds / 60);
		const s = seconds % 60;
		return m > 0 ? `${m}m ${s}s` : `${s}s`;
	}

	private _renderSignals(): string {
		const signals = this._status?.pending ?? [];
		if (!signals.length) {
			return `<p class="empty-state" role="status">${this.tr('ambient_no_signals', 'No active signals')}</p>`;
		}
		return signals.map(sig => {
			const pColor = this._priorityColor(sig.priority ?? 5);
			const sWidth = this._severityWidth(sig.severity ?? 0.5);
			const sColor = this._severityBarColor(sig.severity ?? 0.5);
			const source = sig.source ?? sig.rule_id ?? '—';
			const message = sig.message ?? '';
			const key = sig._key ?? sig.rule_id ?? '';
			return `
				<article class="signal-card" role="article" aria-label="${this.tr('ambient_source_label', 'Source')}: ${source}">
					<div class="signal-header">
						<span class="priority-badge" style="background:hsla(${pColor},0.18);color:hsla(${pColor},1);border-color:hsla(${pColor},0.4);"
							aria-label="${this.tr('ambient_priority_label', 'Priority')} ${sig.priority ?? 5}">P${sig.priority ?? 5}</span>
						<span class="signal-source">${source}</span>
						<button class="dismiss-btn" data-key="${key}"
							aria-label="${this.tr('ambient_dismiss_aria', 'Dismiss ambient signal')}">${this.tr('ambient_dismiss_label', 'Dismiss')}</button>
					</div>
					${message ? `<p class="signal-message">${message}</p>` : ''}
					<div class="severity-track" role="meter" aria-valuenow="${Math.round((sig.severity ?? 0.5) * 100)}"
						aria-valuemin="0" aria-valuemax="100" aria-label="${this.tr('ambient_severity_label', 'Severity')}">
						<div class="severity-fill" style="width:${sWidth};background:${sColor};"></div>
					</div>
				</article>
			`;
		}).join('');
	}

	private _renderCooldowns(): string {
		const cooldowns = this._status?.cooldowns ?? [];
		if (!cooldowns.length) return '';
		return `
			<section class="cooldowns-section" aria-label="${this.tr('ambient_cooldown_label', 'Cooldown')}">
				<h3 class="sub-heading">${this.tr('ambient_cooldown_label', 'Cooldown')}</h3>
				<ul class="cooldown-list" role="list">
					${cooldowns.map(c => `
						<li class="cooldown-item" role="listitem">
							<span class="cooldown-rule">${c.rule_id}</span>
							<span class="cooldown-ttl" aria-label="${this._formatTtl(c.ttl_seconds)}">${this._formatTtl(c.ttl_seconds)}</span>
						</li>
					`).join('')}
				</ul>
			</section>
		`;
	}

	private _renderStats(): string {
		const s = this._status;
		if (!s) return '';
		const rateMax = s.rate_max ?? 3;
		const rateCount = s.rate_count ?? 0;
		const ratePct = rateMax > 0 ? Math.round((rateCount / rateMax) * 100) : 0;
		return `
			<div class="stats-row" role="group" aria-label="${this.tr('ambient_section_aria', 'Ambient intelligence panel')}">
				<div class="stat-cell">
					<span class="stat-value" aria-live="polite">${rateCount}/${rateMax}</span>
					<span class="stat-label">${this.tr('ambient_rate_label', 'Triggers/hr')}</span>
					<div class="rate-track" role="meter" aria-valuenow="${ratePct}" aria-valuemin="0" aria-valuemax="100">
						<div class="rate-fill" style="width:${ratePct}%;"></div>
					</div>
				</div>
				<div class="stat-cell">
					<span class="stat-value" aria-live="polite">${s.pending_count}</span>
					<span class="stat-label">${this.tr('ambient_pending_label', 'Queued')}</span>
				</div>
				<div class="stat-cell">
					<span class="stat-value" aria-live="polite">${s.briefing_queue_depth}</span>
					<span class="stat-label">${this.tr('ambient_briefing_label', 'In briefing')}</span>
				</div>
			</div>
		`;
	}

	private render() {
		const root = this.shadowRoot;
		if (!root) return;
		const enabled = this._status?.enabled ?? this._config?.enabled ?? false;
		const statusLabel = enabled
			? this.tr('ambient_engine_status_on', 'Engine on')
			: this.tr('ambient_engine_status_off', 'Engine off');

		root.innerHTML = `
			<style>
				${ACCESSIBILITY_STYLES}
				${SECTION_HEADER_STYLES}
				${EMPTY_STATE_STYLES}

				:host {
					display: block;
					font-family: var(--font-body, system-ui, sans-serif);
					font-size: 0.875rem;
					color: var(--color-text, hsla(220, 15%, 90%, 1));
				}

				.widget-wrap {
					background: var(--color-surface-1, hsla(220, 18%, 14%, 0.85));
					border: 1px solid var(--color-border, hsla(220, 15%, 25%, 0.4));
					border-radius: 0.75rem;
					padding: 1.25rem;
					display: flex;
					flex-direction: column;
					gap: 1rem;
				}

				.header-row {
					display: flex;
					align-items: center;
					gap: 0.75rem;
					flex-wrap: wrap;
				}

				.h-icon {
					width: 1.25rem;
					height: 1.25rem;
					opacity: 0.85;
					flex-shrink: 0;
				}

				.widget-title {
					font-size: 1rem;
					font-weight: 600;
					margin: 0;
					flex: 1;
					min-width: 0;
					white-space: nowrap;
					overflow: hidden;
					text-overflow: ellipsis;
				}

				.engine-badge {
					font-size: 0.7rem;
					padding: 0.2rem 0.55rem;
					border-radius: 99rem;
					font-weight: 600;
					letter-spacing: 0.03em;
					border: 1px solid;
				}

				.engine-badge.on {
					background: hsla(142, 71%, 45%, 0.15);
					color: hsla(142, 71%, 65%, 1);
					border-color: hsla(142, 71%, 45%, 0.35);
				}

				.engine-badge.off {
					background: hsla(220, 15%, 25%, 0.3);
					color: hsla(220, 15%, 55%, 1);
					border-color: hsla(220, 15%, 30%, 0.4);
				}

				.section-title {
					font-size: 0.75rem;
					font-weight: 600;
					text-transform: uppercase;
					letter-spacing: 0.08em;
					opacity: 0.6;
					margin: 0 0 0.5rem 0;
				}

				.sub-heading {
					font-size: 0.72rem;
					font-weight: 600;
					text-transform: uppercase;
					letter-spacing: 0.07em;
					opacity: 0.55;
					margin: 0 0 0.4rem 0;
				}

				.signal-card {
					background: hsla(220, 18%, 18%, 0.6);
					border: 1px solid var(--color-border, hsla(220, 15%, 25%, 0.4));
					border-radius: 0.5rem;
					padding: 0.75rem;
					display: flex;
					flex-direction: column;
					gap: 0.4rem;
				}

				.signal-card + .signal-card {
					margin-top: 0.5rem;
				}

				.signal-header {
					display: flex;
					align-items: center;
					gap: 0.5rem;
					flex-wrap: wrap;
				}

				.priority-badge {
					font-size: 0.65rem;
					font-weight: 700;
					padding: 0.15rem 0.4rem;
					border-radius: 0.25rem;
					border: 1px solid;
					flex-shrink: 0;
				}

				.signal-source {
					flex: 1;
					min-width: 0;
					font-size: 0.8rem;
					font-weight: 500;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}

				.signal-message {
					font-size: 0.8rem;
					opacity: 0.8;
					margin: 0;
					line-height: 1.45;
				}

				.severity-track {
					height: 0.25rem;
					background: hsla(220, 15%, 28%, 0.5);
					border-radius: 99rem;
					overflow: hidden;
				}

				.severity-fill {
					height: 100%;
					border-radius: 99rem;
					transition: width 0.4s ease;
				}

				.dismiss-btn {
					font-size: 0.68rem;
					padding: 0.2rem 0.5rem;
					border-radius: 0.3rem;
					border: 1px solid hsla(220, 15%, 35%, 0.5);
					background: transparent;
					color: var(--color-text, hsla(220, 15%, 75%, 1));
					cursor: pointer;
					min-width: 44px;
					min-height: 28px;
					transition: background 0.15s ease;
				}

				.dismiss-btn:hover {
					background: hsla(220, 15%, 28%, 0.6);
				}

				.dismiss-btn:focus-visible {
					outline: 2px solid var(--color-accent, hsla(175, 80%, 45%, 1));
					outline-offset: 2px;
				}

				.stats-row {
					display: grid;
					grid-template-columns: repeat(3, 1fr);
					gap: 0.5rem;
				}

				.stat-cell {
					background: hsla(220, 18%, 18%, 0.4);
					border: 1px solid var(--color-border, hsla(220, 15%, 25%, 0.3));
					border-radius: 0.4rem;
					padding: 0.5rem 0.6rem;
					display: flex;
					flex-direction: column;
					gap: 0.15rem;
				}

				.stat-value {
					font-size: 1rem;
					font-weight: 700;
					color: var(--color-accent, hsla(175, 80%, 60%, 1));
					line-height: 1;
				}

				.stat-label {
					font-size: 0.65rem;
					text-transform: uppercase;
					letter-spacing: 0.06em;
					opacity: 0.55;
				}

				.rate-track {
					height: 0.2rem;
					background: hsla(220, 15%, 28%, 0.5);
					border-radius: 99rem;
					overflow: hidden;
					margin-top: 0.2rem;
				}

				.rate-fill {
					height: 100%;
					border-radius: 99rem;
					background: var(--color-accent, hsla(175, 80%, 50%, 0.8));
					transition: width 0.4s ease;
				}

				.cooldowns-section {
					border-top: 1px solid var(--color-border, hsla(220, 15%, 25%, 0.25));
					padding-top: 0.75rem;
				}

				.cooldown-list {
					list-style: none;
					margin: 0;
					padding: 0;
					display: flex;
					flex-direction: column;
					gap: 0.3rem;
				}

				.cooldown-item {
					display: flex;
					align-items: center;
					justify-content: space-between;
					font-size: 0.78rem;
					gap: 0.5rem;
				}

				.cooldown-rule {
					opacity: 0.75;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}

				.cooldown-ttl {
					font-variant-numeric: tabular-nums;
					opacity: 0.6;
					white-space: nowrap;
					flex-shrink: 0;
				}

				.disabled-notice {
					font-size: 0.82rem;
					opacity: 0.55;
					text-align: center;
					padding: 1rem 0;
				}

				.error-banner {
					font-size: 0.78rem;
					color: hsla(var(--color-error-h, 0), var(--color-error-s, 84%), var(--color-error-l, 65%), 0.9);
					background: hsla(var(--color-error-h, 0), var(--color-error-s, 84%), var(--color-error-l, 30%), 0.1);
					border: 1px solid hsla(var(--color-error-h, 0), var(--color-error-s, 84%), var(--color-error-l, 40%), 0.25);
					border-radius: 0.4rem;
					padding: 0.5rem 0.65rem;
				}

				@media (prefers-reduced-motion: reduce) {
					.severity-fill,
					.rate-fill {
						transition: none;
					}
				}

				@media (forced-colors: active) {
					.signal-card,
					.stat-cell,
					.dismiss-btn {
						border: 1px solid ButtonText;
					}
					.priority-badge,
					.engine-badge {
						forced-color-adjust: none;
					}
				}
			</style>

			<section
				class="widget-wrap"
				aria-label="${this.tr('ambient_section_aria', 'Ambient intelligence panel')}"
				role="region"
			>
				<div class="header-row">
					<svg class="h-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true" focusable="false">
						<circle cx="12" cy="12" r="3"/>
						<path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
					</svg>
					<h2 class="widget-title">${this.tr('ambient_widget_title', 'Ambient Intelligence')}</h2>
					<span class="engine-badge ${enabled ? 'on' : 'off'}" role="status" aria-live="polite">${statusLabel}</span>
				</div>

				${this._error ? `<p class="error-banner" role="alert">${this._error}</p>` : ''}

				${!enabled ? `
					<p class="disabled-notice" role="status">${this.tr('ambient_engine_disabled', 'Engine disabled')}</p>
				` : `
					${this._renderStats()}

					<div class="signals-section">
						<h3 class="section-title">${this.tr('ambient_signals_active', 'Active Signals')}</h3>
						${this._renderSignals()}
					</div>

					${this._renderCooldowns()}
				`}
			</section>
		`;

		// Attach dismiss handlers after render
		root.querySelectorAll<HTMLButtonElement>('.dismiss-btn').forEach(btn => {
			btn.addEventListener('click', () => {
				const key = btn.dataset.key ?? '';
				if (key) this.dismissSignal(key);
			});
		});
	}
}

customElements.define('ambient-widget', AmbientWidget);
