import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { GOO_STYLES, initGoo } from '../services/gooStyles';

export class WelcomeOnboarding extends HTMLElement {
	private t: Record<string, string> = {};

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
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

	connectedCallback() {
		this.loadTranslations().then(() => this.checkStatus());
		initGoo(this);
		window.addEventListener('goo-changed', () => initGoo(this));
	}

	async checkStatus() {
		try {
			const response = await fetch('/api/dashboard/onboarding-status');
			if (!response.ok) return;
			const data = await response.json();
			if (data.needs_onboarding) {
				this.render(data);
			} else {
				this.style.display = 'none';
			}
		} catch (_e) {
			console.warn('Could not check onboarding status');
		}
	}

	render(data: any) {
		const steps = data.steps;
		if (this.shadowRoot) {
			this.shadowRoot.innerHTML = `
				<style>
					:host { display: block; grid-column: 1 / -1; margin-bottom: 2rem; }
					${ACCESSIBILITY_STYLES}
					${GOO_STYLES}
					.card {
						background: linear-gradient(135deg, var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.1)), rgba(var(--accent-secondary-rgb, 0, 102, 255), 0.1));
						border: 2px solid var(--border-accent, hsla(173, 80%, 40%, 0.3));
						border-radius: var(--radius-lg, 1rem);
						padding: 2rem;
						display: flex;
						flex-direction: column;
						gap: 1.5rem;
						animation: slideIn var(--duration-base, 0.25s) ease-out;
						box-shadow: 0 8px 32px var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.1));
					}
					@keyframes slideIn {
						from { opacity: 0; transform: translateY(-10px); }
						to { opacity: 1; transform: translateY(0); }
					}
					h2 { 
						margin: 0; 
						font-size: 1.8rem; 
						background: linear-gradient(135deg, var(--accent-primary, hsla(173, 80%, 40%, 1)), var(--accent-secondary, hsla(216, 100%, 50%, 1))); 
						-webkit-background-clip: text; 
						-webkit-text-fill-color: transparent; 
					}
					p { margin: 0; color: var(--text-primary, hsla(0, 0%, 100%, 1)); opacity: 0.8; line-height: 1.6; }
					
					.steps {
						display: grid;
						grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
						gap: 1rem;
					}
					.step-item {
						background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
						padding: 1rem;
						border-radius: var(--radius-md, 0.75rem);
						border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.1));
						display: flex;
						align-items: center;
						gap: 0.75rem;
						transition: all var(--duration-base, 0.25s) ease;
					}
					.step-item.done { 
						border-color: var(--accent-primary, hsla(173, 80%, 40%, 1)); 
						background: var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.05)); 
					}
					.step-icon { 
						width: 28px; height: 28px; border-radius: 50%; 
						display: flex; align-items: center; justify-content: center;
						background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.06)); font-size: 0.8rem;
						flex-shrink: 0;
					}
					.done .step-icon { 
						background: var(--accent-primary, hsla(173, 80%, 40%, 1)); 
						color: var(--text-primary, hsla(0, 0%, 100%, 1)); 
					}
					.step-text { font-weight: 600; font-size: 0.95rem; color: var(--text-primary, hsla(0, 0%, 100%, 1)); }
					.step-text span { display: block; font-size: 0.75rem; color: var(--text-muted, hsla(0, 0%, 100%, 0.4)); font-weight: 400; margin-top: 0.1rem; }

					.cta {
						align-self: flex-start;
						background: var(--accent-primary-dark, hsla(173, 80%, 25%, 1));
						color: hsla(0, 0%, 100%, 1);
						padding: 0.75rem 1.5rem;
						border-radius: var(--radius-md, 0.75rem);
						text-decoration: none;
						font-weight: 600;
						font-size: 0.95rem;
						transition: all var(--duration-fast, 0.2s);
						border: none;
						cursor: pointer;
						min-height: 44px; /* A11y target */
						box-shadow: 0 4px 12px var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.2));
					}
					.cta:hover { transform: translateY(-2px); box-shadow: 0 6px 16px var(--surface-accent-subtle, hsla(173, 80%, 40%, 0.4)); }
					.cta:focus-visible { outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); outline-offset: 3px; }
					.step-item:focus-visible { outline: 2px solid var(--accent-primary, hsla(173, 80%, 40%, 1)); outline-offset: 2px; }
					@media (prefers-reduced-motion: reduce) {
						.card, .step-item, .cta { animation: none; transition: none; transform: none; }
					}
					@media (forced-colors: active) {
						.card { background: Canvas; border: 2px solid ButtonText; }
						h2 { background: none; color: ButtonText; -webkit-text-fill-color: ButtonText; }
						.step-item.done { border-color: Highlight; }
						.done .step-icon { background: Highlight; color: HighlightText; }
						.cta { background: Highlight; color: HighlightText; border: 1px solid Highlight; }
					}
				</style>
				<div class="card">
					<div>
						<h2>${this.tr('welcome_heading', 'Welcome to openZero')}</h2>
						<p>${this.tr('welcome_subtitle', "Your private agent OS is online. Let's finish the setup to unlock Z's full potential.")}</p>
					</div>
					
					<ul class="steps" role="list" aria-label="${this.tr('aria_setup_steps', 'Setup steps')}" style="list-style:none;padding:0;margin:0;">
						<li class="step-item ${steps.profile ? 'done' : ''}" role="listitem">
							<div class="step-icon" aria-hidden="true">${steps.profile ? '&#10003;' : '1'}</div>
							<div class="step-text">
								${this.tr('step_profile', 'Personal Profile')}
								<span>${this.tr('step_profile_hint', 'Set your mission in about-me.md')}</span>
								${steps.profile ? '<span class="sr-only">' + this.tr('completed', 'Completed') + '</span>' : '<span class="sr-only">' + this.tr('not_completed', 'Not yet completed') + '</span>'}
							</div>
						</li>
						<li class="step-item ${steps.inner_circle ? 'done' : ''}" role="listitem">
							<div class="step-icon" aria-hidden="true">${steps.inner_circle ? '&#10003;' : '2'}</div>
							<div class="step-text">
								${this.tr('step_inner_circle', 'Inner Circle')}
								<span>${this.tr('step_inner_hint', 'Add family & close contacts below')}</span>
								${steps.inner_circle ? '<span class="sr-only">' + this.tr('completed', 'Completed') + '</span>' : '<span class="sr-only">' + this.tr('not_completed', 'Not yet completed') + '</span>'}
							</div>
						</li>
						<li class="step-item ${steps.calendar ? 'done' : ''}" role="listitem">
							<div class="step-icon" aria-hidden="true">${steps.calendar ? '&#10003;' : '3'}</div>
							<div class="step-text">
								${this.tr('step_calendar', 'Calendar')}
								<span>${this.tr('step_calendar_hint', 'OAuth link for external events')}</span>
								${steps.calendar ? '<span class="sr-only">' + this.tr('completed', 'Completed') + '</span>' : '<span class="sr-only">' + this.tr('not_completed', 'Not yet completed') + '</span>'}
							</div>
						</li>
					</ul>

					<div style="display: flex; align-items: center; justify-content: space-between; margin-top: 1rem;">
						<button class="cta" id="dismiss-onboarding-btn">${this.tr('dismiss_onboarding', 'Dismiss Onboarding')}</button>
					</div>
				</div>
			`;
			const dismissBtn = this.shadowRoot?.querySelector('#dismiss-onboarding-btn');
			if (dismissBtn) {
				dismissBtn.addEventListener('click', () => {
					this.style.opacity = '0';
					this.style.pointerEvents = 'none';
					fetch('/api/dashboard/onboarding-dismiss', { method: 'POST' });
					setTimeout(() => { this.style.display = 'none'; }, 500);
				});
			}
		}
	}
}

customElements.define('welcome-onboarding', WelcomeOnboarding);
