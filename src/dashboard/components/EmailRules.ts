import { BUTTON_STYLES } from '../services/buttonStyles';
import { initGoo } from '../services/gooStyles';
import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SECTION_HEADER_STYLES } from '../services/sectionHeaderStyles';

export class EmailRules extends HTMLElement {
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
    this.render();
    this.loadTranslations().then(() => {
      this.render();
      this.fetchRules();
    });
    initGoo(this);
    window.addEventListener('goo-changed', () => initGoo(this));
  }

  private editingId: number | null = null;
  private isAdding: boolean = false;
  private currentRules: { id: number, sender_pattern: string, action: string, badge?: string }[] = [];

  async fetchRules() {
    try {
      const response = await fetch('/api/dashboard/email-rules');
      if (!response.ok) throw new Error('API error');
      const data = await response.json();
      this.currentRules = data;
      this.displayRules(data);
    } catch (_e) {
      const list = this.shadowRoot?.querySelector('#rules-list');
      if (list) list.textContent = 'No rules defined.';
    }
  }

  async addRule(pattern: string, action: string, badge: string) {
    try {
      await fetch('/api/dashboard/email-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender_pattern: pattern, action, badge })
      });
      this.isAdding = false;
      this.render();
      this.fetchRules();
    } catch (e) {
      console.error('Failed to add rule', e);
    }
  }

  async updateRule(id: number, pattern: string, action: string, badge: string) {
    try {
      await fetch(`/api/dashboard/email-rules/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender_pattern: pattern, action, badge })
      });
      this.editingId = null;
      this.isAdding = false;
      this.render();
      this.fetchRules();
    } catch (e) {
      console.error('Failed to update rule', e);
    }
  }


  displayRules(rules: { id: number, sender_pattern: string, action: string, badge?: string }[]) {
    const list = this.shadowRoot?.querySelector('#rules-list');
    if (list) {
      list.innerHTML = rules.map(r => `
				<div class="rule-item">
					<div class="info">
						<span class="pattern">
							${r.sender_pattern}
							${r.badge ? `<span class="label-badge">${r.badge}</span>` : ''}
						</span>
						<span class="action-tag">
							${(r.action || '').toLowerCase() === 'urgent' ? '<span aria-hidden="true">&#9889;</span> Urgent Notify' : (r.action || '').toLowerCase() === 'summarize' ? '<span aria-hidden="true">&#128203;</span> Daily Summary' : '<span aria-hidden="true">&#128263;</span> Ignored'}
						</span>
					</div>
					<div class="item-actions">
						<button class="edit-btn" data-id="${r.id}" aria-label="${this.tr('aria_edit_rule', 'Edit rule for')} ${r.sender_pattern}">${this.tr('edit', 'Edit')}</button>
						<button class="delete-btn" data-id="${r.id}" aria-label="${this.tr('aria_delete_rule', 'Delete rule for')} ${r.sender_pattern}">${this.tr('delete', 'Delete')}</button>
					</div>
				</div>
			`).join('') || 'No rules defined.';

      list.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const id = (e.currentTarget as HTMLElement).getAttribute('data-id');
          if (id) this.deleteRule(parseInt(id));
        });
      });

      list.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const id = (e.currentTarget as HTMLElement).getAttribute('data-id');
          const rule = this.currentRules.find(r => r.id === parseInt(id!));
          if (rule) {
            this.editingId = rule.id;
            this.isAdding = true;
            this.render();
            (this.shadowRoot?.querySelector('#ruleInput') as HTMLInputElement).value = rule.sender_pattern;
            (this.shadowRoot?.querySelector('#actionInput') as HTMLSelectElement).value = rule.action;
            (this.shadowRoot?.querySelector('#badgeInput') as HTMLInputElement).value = rule.badge || '';
          }
        });
      });
    }
  }

  render() {
    if (this.shadowRoot) {
      this.shadowRoot.innerHTML = `
				<style>
					${ACCESSIBILITY_STYLES}
					${SECTION_HEADER_STYLES}
					:host { display: block; }
					.add-box { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1.5rem; background: rgba(255,255,255,0.02); padding: 1rem; border-radius: 1rem; }
					.input-row { display: flex; gap: 0.5rem; }
					input, select {
						flex: 1;
						background: rgba(0, 0, 0, 0.2);
						border: 1px solid rgba(255, 255, 255, 0.08);
						border-radius: 0.75rem;
						padding: 0.6rem 1rem;
						color: var(--text-primary, hsla(0, 0%, 100%, 1));
						outline: none;
						font-family: 'Inter', system-ui, sans-serif;
						font-size: 0.9rem;
					}
					select option { background: hsla(0, 0%, 0%, 1); }
					.rule-item {
						display: flex;
						justify-content: space-between;
						align-items: center;
						background: rgba(255, 255, 255, 0.03);
						padding: 0.75rem 1rem;
						border-radius: 0.75rem;
						margin-bottom: 0.5rem;
					}
					.info { display: flex; flex-direction: column; gap: 4px; }
					.pattern { color: var(--text-primary, hsla(0, 0%, 100%, 1)); font-weight: 500; font-size: 0.9rem; }
					${BUTTON_STYLES}
					.action-tag { font-size: 0.75rem; color: var(--accent-color, hsla(173, 80%, 40%, 1)); font-weight: 600; }
					.label-badge { 
						background: var(--accent-color); 
						color: var(--on-accent-text); 
						font-size: 0.65rem; 
						padding: 2px 6px; 
						border-radius: 4px; 
						margin-left: 8px; 
						vertical-align: middle;
						text-transform: uppercase;
						font-weight: 700;
					}
					.edit-btn { margin-right: 6px; }
					.edit-btn:hover { background: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.2); }
					.item-actions { display: flex; align-items: center; }

					.edit-btn:focus-visible, .delete-btn:focus-visible { outline: 2px solid rgba(255,255,255,0.4); outline-offset: 2px; }
					input:focus-visible, select:focus-visible { outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1)); outline-offset: 2px; }
					.required {
						color: var(--color-danger, hsla(0, 91%, 71%, 1));
					}
					.form-label {
						display: block;
						font-size: 0.68rem;
						font-weight: 600;
						color: rgba(255,255,255,0.45);
						text-transform: uppercase;
						letter-spacing: 0.05em;
						margin: 0 0 0.25rem 0;
					}
					.input-col { display: flex; flex-direction: column; flex: 1; }
					@media (forced-colors: active) {
						.action-tag { color: LinkText; }
						.label-badge { border: 1px solid ButtonText; }
					}
				</style>
				<div class="card">
					<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
						<h2>
							<span class="h-icon" aria-hidden="true">
								<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
									<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
									<polyline points="22,6 12,13 2,6"></polyline>
								</svg>
							</span>
							${this.tr('email_rules', 'Email')}
						</h2>
						${!this.isAdding ? `<button id="showAddBtn" class="btn-primary" aria-label="+ ${this.tr('new_rule', 'New Rule')} — ${this.tr('aria_add_email_rule', 'Add new email rule')}">+ ${this.tr('new_rule', 'New Rule')}</button>` : ''}
					</div>

					${this.isAdding ? `
					<fieldset class="add-box" id="add-rule-form">
						<legend style="font-size:0.75rem;font-weight:600;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:0.06em;padding:0 0.25rem;">${this.editingId ? this.tr('edit_rule_legend', 'Edit Rule') : this.tr('new_rule_legend', 'New Rule')}</legend>
						<div class="input-row">
							<div class="input-col">
								<label class="form-label" for="ruleInput">${this.tr('pattern_label', 'Sender Pattern')} <span class="required" aria-hidden="true">*</span></label>
								<input type="text" id="ruleInput" required aria-required="true" placeholder="${this.tr('ph_rule_pattern', 'e.g. @domain.com or Invoice')}" autocomplete="off" aria-describedby="rule-hint">
								<span id="rule-hint" style="font-size:0.65rem;color:rgba(255,255,255,0.25);margin-top:0.15rem;">Match against sender address or subject keywords</span>
							</div>
							<div class="input-col">
								<label class="form-label" for="actionInput">${this.tr('action_label', 'Action')}</label>
								<select id="actionInput" aria-label="${this.tr('aria_email_action', 'Email action for matching senders')}">
									<option value="urgent">${this.tr('action_urgent', 'Urgent Notification')}</option>
									<option value="summarize">${this.tr('action_summarize', 'Daily Summary')}</option>
									<option value="ignore">${this.tr('action_ignore', 'Ignore Completely')}</option>
								</select>
							</div>
							<div class="input-col">
								<label class="form-label" for="badgeInput">${this.tr('badge_label', 'Badge Label')} <span style="color:rgba(255,255,255,0.3);font-weight:400;">(optional)</span></label>
								<input type="text" id="badgeInput" placeholder="${this.tr('ph_badge_label', 'e.g. CLIENT')}" autocomplete="off" maxlength="20">
							</div>
						</div>
						<div style="display:flex; gap:0.5rem; margin-top:0.75rem;">
							<button id="addBtn" type="submit" class="btn-primary" aria-label="${this.editingId ? this.tr('aria_update_rule', 'Update rule') : this.tr('aria_create_rule', 'Create rule')}">${this.editingId ? this.tr('update_rule', 'Update Rule') : this.tr('create_rule', 'Create Rule')}</button>
							<button id="cancelEdit" type="button" class="cancel-btn" aria-label="${this.tr('aria_cancel_editing', 'Cancel editing')}">${this.tr('cancel', 'Cancel')}</button>
						</div>
					</fieldset>
					` : ''}
					<div id="rules-list">${this.currentRules.length > 0 ? '' : this.tr('loading_rules', 'Loading rules...')}</div>
				</div>
			`;

      if (!this.isAdding) {
        this.shadowRoot.querySelector('#showAddBtn')?.addEventListener('click', () => {
          this.isAdding = true;
          this.render();
        });
      }

      this.displayRules(this.currentRules);

      this.shadowRoot.querySelector('#addBtn')?.addEventListener('click', () => {
        const pattern = (this.shadowRoot?.querySelector('#ruleInput') as HTMLInputElement).value;
        const action = (this.shadowRoot?.querySelector('#actionInput') as HTMLSelectElement).value;
        const badge = (this.shadowRoot?.querySelector('#badgeInput') as HTMLInputElement).value;
        if (pattern) {
          if (this.editingId) {
            this.updateRule(this.editingId, pattern, action, badge);
          } else {
            this.addRule(pattern, action, badge);
          }
          (this.shadowRoot?.querySelector('#ruleInput') as HTMLInputElement).value = '';
          (this.shadowRoot?.querySelector('#badgeInput') as HTMLInputElement).value = '';
        }
      });

      // Accessibility: Submit on Enter
      this.shadowRoot.querySelectorAll('input, select').forEach(el => {
        el.addEventListener('keydown', (e: Event) => {
          const ke = e as KeyboardEvent;
          if (ke.key === 'Enter') {
            ke.preventDefault();
            this.shadowRoot?.querySelector<HTMLButtonElement>('#addBtn')?.click();
          }
        });
      });

      this.shadowRoot.querySelector('#cancelEdit')?.addEventListener('click', () => {
        this.editingId = null;
        this.isAdding = false;
        this.render();
      });
    }
  }

  async deleteRule(id: number) {
    if (!confirm(this.tr('confirm_delete_rule', 'Are you sure you want to delete this intelligence rule?'))) return;
    try {
      await fetch(`/api/dashboard/email-rules/${id}`, { method: 'DELETE' });
      this.fetchRules();
    } catch (e) {
      console.error('Failed to delete rule', e);
    }
  }
}

customElements.define('email-rules', EmailRules);
