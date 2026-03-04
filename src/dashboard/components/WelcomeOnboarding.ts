import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';

export class WelcomeOnboarding extends HTMLElement {
	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.checkStatus();
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
		} catch (e) {
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
					.card {
						background: linear-gradient(135deg, rgba(var(--accent-color-rgb, 20, 184, 166), 0.1), rgba(0, 102, 255, 0.1));
						border: 1px solid rgba(var(--accent-color-rgb, 20, 184, 166), 0.3);
						border-radius: var(--radius-lg, 1rem);
						padding: 2rem;
						display: flex;
						flex-direction: column;
						gap: 1.5rem;
						animation: slideIn 0.5s ease-out;
					}
					@keyframes slideIn {
						from { opacity: 0; }
						to { opacity: 1; }
					}
					h2 { margin: 0; font-size: 1.8rem; background: linear-gradient(135deg, var(--accent-color, #14B8A6), #0066FF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
					p { margin: 0; color: var(--text-secondary, rgba(255, 255, 255, 0.8)); line-height: 1.6; }
					
					.steps {
						display: grid;
						grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
						gap: 1rem;
					}
					.step-item {
						background: rgba(255, 255, 255, 0.05);
						padding: 1rem;
						border-radius: 0.75rem;
						border: 1px solid rgba(255, 255, 255, 0.08);
						display: flex;
						align-items: center;
						gap: 0.75rem;
						transition: all 0.3s ease;
					}
					.step-item.done { border-color: var(--accent-color, #14B8A6); background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.05); }
					.step-icon { 
						width: 24px; height: 24px; border-radius: 50%; 
						display: flex; align-items: center; justify-content: center;
						background: rgba(255, 255, 255, 0.1); font-size: 0.8rem;
					}
					.done .step-icon { background: var(--accent-color, #14B8A6); color: #fff; }
					.step-text { font-weight: 500; font-size: 0.9rem; }
					.step-text span { display: block; font-size: 0.75rem; color: rgba(255, 255, 255, 0.4); font-weight: 400; }

					.cta {
						align-self: flex-start;
						background: var(--accent-color, #14B8A6);
						color: #fff;
						padding: 0.75rem 1.5rem;
						border-radius: var(--radius-md, 0.75rem);
						text-decoration: none;
						font-weight: 600;
						font-size: 0.95rem;
						transition: all var(--duration-fast, 0.2s);
						border: none;
						cursor: pointer;
					}
					.cta:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(var(--accent-color-rgb, 20, 184, 166), 0.4); }
					.cta:focus-visible { outline: 2px solid var(--accent-color, #14B8A6); outline-offset: 3px; }
					.step-item:focus-visible { outline: 2px solid rgba(var(--accent-color-rgb, 20, 184, 166), 0.5); outline-offset: 2px; border-radius: 0.75rem; }
				</style>
				<div class="card">
					<div>
						<h2>Welcome to openZero</h2>
						<p>Your private agent OS is online. Let's finish the setup to unlock Z's full potential.</p>
					</div>
					
					<ul class="steps" role="list" aria-label="Setup steps" style="list-style:none;padding:0;margin:0;">
						<li class="step-item ${steps.profile ? 'done' : ''}" role="listitem">
							<div class="step-icon" aria-hidden="true">${steps.profile ? '&#10003;' : '1'}</div>
							<div class="step-text">
								Personal Profile
								<span>Set your mission in about-me.md</span>
								${steps.profile ? '<span class="sr-only">Completed</span>' : '<span class="sr-only">Not yet completed</span>'}
							</div>
						</li>
						<li class="step-item ${steps.inner_circle ? 'done' : ''}" role="listitem">
							<div class="step-icon" aria-hidden="true">${steps.inner_circle ? '&#10003;' : '2'}</div>
							<div class="step-text">
								Inner Circle
								<span>Add family &amp; close contacts below</span>
								${steps.inner_circle ? '<span class="sr-only">Completed</span>' : '<span class="sr-only">Not yet completed</span>'}
							</div>
						</li>
						<li class="step-item ${steps.calendar ? 'done' : ''}" role="listitem">
							<div class="step-icon" aria-hidden="true">${steps.calendar ? '&#10003;' : '3'}</div>
							<div class="step-text">
								Calendar
								<span>OAuth link for external events</span>
								${steps.calendar ? '<span class="sr-only">Completed</span>' : '<span class="sr-only">Not yet completed</span>'}
							</div>
						</li>
					</ul>

					<div style="display: flex; align-items: center; justify-content: space-between; margin-top: 1rem;">
						<button class="cta" id="dismiss-onboarding-btn" aria-label="Dismiss setup onboarding checklist">Dismiss Onboarding</button>
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
