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
                this.render(data.steps);
            } else {
                this.style.display = 'none';
            }
        } catch (e) {
            console.warn('Could not check onboarding status');
        }
    }

    render(steps: any) {
        if (this.shadowRoot) {
            this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; grid-column: 1 / -1; margin-bottom: 2rem; }
          .card {
            background: linear-gradient(135deg, rgba(20, 184, 166, 0.1), rgba(0, 102, 255, 0.1));
            border: 1px solid rgba(20, 184, 166, 0.3);
            border-radius: 1rem;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
            animation: slideIn 0.5s ease-out;
          }
          @keyframes slideIn {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
          }
          h2 { margin: 0; font-size: 1.8rem; background: linear-gradient(135deg, #14B8A6, #0066FF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
          p { margin: 0; color: rgba(255, 255, 255, 0.8); line-height: 1.6; }
          
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
          .step-item.done { border-color: #14B8A6; background: rgba(20, 184, 166, 0.05); }
          .step-icon { 
            width: 24px; height: 24px; border-radius: 50%; 
            display: flex; align-items: center; justify-content: center;
            background: rgba(255, 255, 255, 0.1); font-size: 0.8rem;
          }
          .done .step-icon { background: #14B8A6; color: #fff; }
          .step-text { font-weight: 500; font-size: 0.9rem; }
          .step-text span { display: block; font-size: 0.75rem; color: rgba(255, 255, 255, 0.4); font-weight: 400; }

          .cta {
            align-self: flex-start;
            background: #14B8A6;
            color: #fff;
            padding: 0.75rem 1.5rem;
            border-radius: 0.75rem;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.95rem;
            transition: all 0.2s;
            border: none;
            cursor: pointer;
          }
          .cta:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(20, 184, 166, 0.4); }
        </style>
        <div class="card">
          <div>
            <h2>Welcome to OpenZero</h2>
            <p>Your private agent OS is online. Let's finish the setup to unlock Z's full potential.</p>
          </div>
          
          <div class="steps">
            <div class="step-item ${steps.profile ? 'done' : ''}">
              <div class="step-icon">${steps.profile ? '✓' : '1'}</div>
              <div class="step-text">
                Personal Profile <span>Set your mission in about-me.md</span>
              </div>
            </div>
            <div class="step-item ${steps.inner_circle ? 'done' : ''}">
              <div class="step-icon">${steps.inner_circle ? '✓' : '2'}</div>
              <div class="step-text">
                Inner Circle <span>Add family & close contacts below</span>
              </div>
            </div>
            <div class="step-item ${steps.calendar ? 'done' : ''}">
              <div class="step-icon">${steps.calendar ? '✓' : '3'}</div>
              <div class="step-text">
                Calendar <span>OAuth link for external events</span>
              </div>
            </div>
          </div>

          <button class="cta" onclick="this.parentElement.style.opacity='0.5'; setTimeout(()=>this.parentElement.parentElement.style.display='none', 300)">Dismiss Onboarding</button>
        </div>
      `;
        }
    }
}

customElements.define('welcome-onboarding', WelcomeOnboarding);
