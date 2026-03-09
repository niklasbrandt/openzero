import { ACCESSIBILITY_STYLES } from '../services/accessibilityStyles';
import { SCROLLBAR_STYLES } from '../services/scrollbarStyles';
import { GOO_STYLES, initGoo } from '../services/gooStyles';

interface ChatMessage {
	role: 'user' | 'assistant';
	content: string;
	timestamp: Date;
	model?: string;
	channel?: string;
	pending_actions?: any[];
}

export class ChatPrompt extends HTMLElement {
	private messages: ChatMessage[] = [];
	private pendingRequests = 0;
	private pendingRetry: string | null = null;
	private t: Record<string, string> = {};
	private draft = '';
	private _pollTimer: ReturnType<typeof setInterval> | null = null;

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.draft = localStorage.getItem('z_chat_draft') || '';
		this.render();
		this.loadTranslations().then(() => {
			this.render();
			this.loadHistory();
		});
		initGoo(this);
		window.addEventListener('goo-changed', () => { initGoo(this); this.render(); });
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => this.render());
		});

		// Poll every 20 s while the tab is visible so Telegram messages appear
		// in the dashboard without needing the user to re-focus the window.
		this._pollTimer = setInterval(() => {
			if (document.visibilityState === 'visible' && this.pendingRequests === 0) {
				this.loadHistory();
			}
		}, 20_000);
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

	private async loadHistory() {
		try {
			// Clamp to the backend's enforced cap of 100.
			const limit = Math.min(100, Math.max(30, this.messages.length + 5));
			const res = await fetch(`/api/dashboard/chat/history?limit=${limit}`);
			if (!res.ok) return;
			const data = await res.json();
			if (!data.messages?.length) return;

			// Map messages (oldest at index 0)
			this.messages = data.messages.map((m: any) => ({
				role: m.role === 'z' ? 'assistant' : 'user',
				content: m.content,
				timestamp: new Date(m.at),
				channel: m.channel,
				model: m.model || undefined,
			}));

			// Render immediately. With flex-direction: column-reverse, 
			// it will show at the bottom without any scrolling movement.
			this.renderMessages(true); // pass true to skip animations for history
		} catch (_e) {
			// Silent fail -- chat still works without history
		}
	}

	disconnectedCallback() {
		if (this._pollTimer !== null) {
			clearInterval(this._pollTimer);
			this._pollTimer = null;
		}
	}

	private setupListeners() {
		const input = this.shadowRoot?.querySelector<HTMLTextAreaElement>('#chat-input');
		const sendBtn = this.shadowRoot?.querySelector('#send-btn');

		sendBtn?.addEventListener('click', () => this.handleSend());

		input?.addEventListener('keydown', (e: KeyboardEvent) => {
			if (e.key === 'Enter' && !e.shiftKey) {
				e.preventDefault();
				this.handleSend();
			}
		});

		// Save draft on every keystroke
		input?.addEventListener('input', (e) => {
			this.draft = (e.target as HTMLTextAreaElement).value;
			localStorage.setItem('z_chat_draft', this.draft);
		});

		// LLM Pre-Warming: Load model into RAM when user prepares to type
		input?.addEventListener('focus', () => {
			fetch('/api/dashboard/system').catch(() => { });
		}, { once: true }); // Only once per session/load

		// Sync chat (including Telegram messages) when the user returns to the tab/window
		const syncOnReturn = () => {
			if (this.pendingRequests === 0) {
				if (this.pendingRetry) {
					this.retryPending();
				} else {
					this.loadHistory();
				}
			}
		};
		document.addEventListener('visibilitychange', () => {
			if (document.visibilityState === 'visible') syncOnReturn();
		});
		window.addEventListener('focus', syncOnReturn);

		// Cmd-chip activation: click or Enter/Space inserts command and sends
		this.shadowRoot?.querySelectorAll('.cmd-chip').forEach(chip => {
			const activate = () => {
				const cmd = chip.textContent?.trim();
				if (!cmd || !input) return;
				input.value = cmd;
				this.draft = cmd;
				this.handleSend();
			};
			chip.addEventListener('click', activate);
			chip.addEventListener('keydown', (e: Event) => {
				const ke = e as KeyboardEvent;
				if (ke.key === 'Enter' || ke.key === ' ') {
					ke.preventDefault();
					activate();
				}
			});
		});
	}

	private async confirmAction(actionId: string, msgIdx: number) {
		try {
			const res = await fetch(`/api/dashboard/actions/confirm/${actionId}`, { method: 'POST' });
			if (res.ok) {
				const data = await res.json();
				// Remove the action from local state
				if (this.messages[msgIdx]) {
					this.messages[msgIdx].pending_actions = this.messages[msgIdx].pending_actions?.filter(a => a.id !== actionId);
					if (data.executed && data.executed.length > 0) {
						this.messages[msgIdx].content += `\n\n✅ Executed: ${data.executed[0]}`;
					}
				}
				this.renderMessages(true);
				window.dispatchEvent(new CustomEvent('refresh-data', { detail: { actions: ['task', 'calendar', 'projects'] } }));
			}
		} catch (e) {
			console.error('Action confirmation failed', e);
		}
	}

	private async cancelAction(actionId: string, msgIdx: number) {
		try {
			const res = await fetch(`/api/dashboard/actions/cancel/${actionId}`, { method: 'POST' });
			if (res.ok) {
				if (this.messages[msgIdx]) {
					this.messages[msgIdx].pending_actions = this.messages[msgIdx].pending_actions?.filter(a => a.id !== actionId);
					this.messages[msgIdx].content += `\n\n🚫 Action cancelled.`;
				}
				this.renderMessages(true);
			}
		} catch (e) {
			console.error('Action cancellation failed', e);
		}
	}

	private async handleSend() {
		const input = this.shadowRoot?.querySelector<HTMLTextAreaElement>('#chat-input');
		const message = input?.value.trim();
		if (!message) return; // Removed isLoading check to allow concurrent messages

		// Add user message
		this.messages.push({ role: 'user', content: message, timestamp: new Date() });

		// Clear local state
		this.draft = '';
		localStorage.removeItem('z_chat_draft');
		if (input) {
			input.value = '';
		}
		this.renderMessages();
		this.scrollToBottom();

		// Send to API
		this.pendingRequests++;
		this.updateSendButton();
		this.showTypingIndicator();

		try {
			const response = await fetch('/api/dashboard/chat', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					message,
					history: this.messages.slice(0, -1).map(m => ({
						role: m.role,
						content: m.content,
					})),
				}),
			});

			const data = await response.json();
			this.hideTypingIndicator();
			this.pendingRetry = null; // Success — clear any retry state
			this.messages.push({
				role: 'assistant',
				content: data.reply || this.tr('no_response', 'No response received.'),
				timestamp: new Date(),
				model: data.model,
				pending_actions: data.pending_actions,
			});

			// Re-sync with DB so any interleaved Telegram messages appear in correct order.
			// Non-blocking: fires in background while notification + refresh-data continue.
			this.loadHistory();

			// Notification sound
			try {
				const audio = new Audio('https://assets.mixkit.co/active_storage/sfx/2354/2354-preview.mp3');
				audio.volume = 0.4;
				audio.play();
			} catch (_) { }

			if (data.actions && data.actions.length > 0) {
				// Map human-readable action strings to widget refresh keys.
				// parse_and_execute_actions returns strings like "Event 'X' scheduled."
				// but CalendarAgenda listens for the keyword 'calendar'.
				const actionTypes: string[] = [];
				for (const act of data.actions as string[]) {
					if (/event|scheduled|calendar/i.test(act)) actionTypes.push('calendar');
					if (/task/i.test(act)) actionTypes.push('task');
					if (/project/i.test(act)) actionTypes.push('projects');
					if (/memory|learned/i.test(act)) actionTypes.push('memory');
				}
				window.dispatchEvent(new CustomEvent('refresh-data', {
					detail: { actions: actionTypes.length ? actionTypes : data.actions }
				}));
			}
		} catch (_e) {
			this.pendingRequests--;
			if (this.pendingRequests <= 0) this.hideTypingIndicator();

			// Store for retry on tab re-entry
			this.pendingRetry = message;

			this.messages.push({
				role: 'assistant',
				content: `⚡ ${this.tr('backend_unreachable', 'Backend unreachable.')} ${this.tr('retry_on_return', 'Will auto-retry when you return.')}\n\n_${this.tr('tap_to_retry', 'Tap here to retry now.')}_`,
				timestamp: new Date(),
			});
		} finally {
			this.pendingRequests = Math.max(0, this.pendingRequests - 1);
			this.updateSendButton();
			if (this.pendingRequests <= 0) this.hideTypingIndicator();
			this.renderMessages();
			this.scrollToBottom();
			input?.focus();

			// Attach retry click handler if there's a pending message.
			// In column-reverse layout the newest message is the FIRST DOM child,
			// so :first-child is the correct selector (not :last-child).
			if (this.pendingRetry) {
				const lastBubble = this.shadowRoot?.querySelector('.message.assistant:first-child .bubble');
				if (lastBubble) {
					(lastBubble as HTMLElement).style.cursor = 'pointer';
					lastBubble.addEventListener('click', () => this.retryPending(), { once: true });
				}
			}
		}
	}

	private async retryPending() {
		if (!this.pendingRetry) return;
		const msg = this.pendingRetry;
		this.pendingRetry = null;

		// Remove the error bubble
		const lastMsg = this.messages[this.messages.length - 1];
		if (lastMsg?.role === 'assistant' && (lastMsg.content.includes('Backend unreachable') || lastMsg.content.includes(this.tr('backend_unreachable', 'Backend unreachable')))) {
			this.messages.pop();
		}

		// Also remove the original user message since handleSend will re-add it
		const lastUser = this.messages[this.messages.length - 1];
		if (lastUser?.role === 'user' && lastUser.content === msg) {
			this.messages.pop();
		}

		this.renderMessages();

		// Re-inject the message into the input and send
		const input = this.shadowRoot?.querySelector<HTMLTextAreaElement>('#chat-input');
		if (input) input.value = msg;
		await this.handleSend();
	}

	private scrollToBottom() {
		requestAnimationFrame(() => {
			const container = this.shadowRoot?.querySelector('#messages');
			if (container) {
				container.scrollTop = 0; // In column-reverse, 0 is bottom
			}
		});
	}

	private showTypingIndicator() {
		const container = this.shadowRoot?.querySelector('#messages');
		if (!container) return;

		// Remove existing typing if somehow present
		this.shadowRoot?.querySelector('#typing')?.remove();

		const indicator = document.createElement('div');
		indicator.id = 'typing';
		indicator.className = 'message assistant';
		indicator.setAttribute('role', 'status');
		indicator.setAttribute('aria-label', this.tr('thinking', 'Z is composing a response'));
		indicator.setAttribute('aria-live', 'polite');
		indicator.innerHTML = `
			<div class="bubble typing-bubble" aria-hidden="true">
				<span class="dot"></span>
				<span class="dot"></span>
				<span class="dot"></span>
			</div>
		`;

		// Prepend so it's at the bottom in column-reverse
		container.prepend(indicator);
		this.scrollToBottom();
	}

	private hideTypingIndicator() {
		if (this.pendingRequests <= 0) {
			this.shadowRoot?.querySelector('#typing')?.remove();
		}
	}

	private updateSendButton() {
		const btn = this.shadowRoot?.querySelector<HTMLButtonElement>('#send-btn');
		if (btn) {
			// Button remains enabled but shows spinner if any requests are pending
			btn.innerHTML = this.pendingRequests > 0 ? this.spinnerSVG() : this.sendSVG();
		}
	}

	private formatDateTime(date: Date): string {
		const now = new Date();
		const isToday = date.toDateString() === now.toDateString();
		const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

		if (isToday) return time;

		const isThisYear = date.getFullYear() === now.getFullYear();
		const dateStr = date.toLocaleDateString([], {
			month: 'short',
			day: 'numeric',
			...(isThisYear ? {} : { year: '2-digit' })
		});

		return `${dateStr}, ${time}`;
	}

	private renderMessages(skipAnimation = false) {
		const container = this.shadowRoot?.querySelector('#messages');
		if (!container) return;

		// Remove typing indicator if present
		const typing = this.shadowRoot?.querySelector('#typing');

		if (this.messages.length === 0) {
			container.innerHTML = `
				<div class="empty-state">
					<div class="empty-icon" aria-hidden="true">${this.chatSVG()}</div>
					<p>${this.tr('start_chat_with_z', 'Start a conversation with Z')}</p>
					<span>${this.tr('chat_hint', 'Ask anything — manage tasks, query memories, or get briefed.')}</span>
					<nav aria-label="${this.tr('aria_quick_commands', 'Quick commands')}" class="command-hints">
						<ul role="list" style="display:flex;flex-wrap:wrap;gap:0.5rem;justify-content:center;list-style:none;padding:0;margin:1rem 0 0 0;">
							<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/day — ${this.tr('aria_cmd_day', 'Daily briefing command')}">/day</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/week — ${this.tr('aria_cmd_week', 'Weekly briefing command')}">/week</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/month — ${this.tr('aria_cmd_month', 'Monthly briefing command')}">/month</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/year — ${this.tr('aria_cmd_year', 'Yearly briefing command')}">/year</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/memory — ${this.tr('aria_cmd_memory', 'Search memory command')}">/memory</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/add — ${this.tr('aria_cmd_add', 'Add memory command')}">/add</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/think — ${this.tr('aria_cmd_think', 'Deep think command')}">/think</span></li>
						</ul>
					</nav>
				</div>
			`;
			return;
		}

		container.innerHTML = [...this.messages].reverse().map((msg, idx) => {
			const realIdx = this.messages.length - 1 - idx;
			return `
			<div class="message ${msg.role} ${skipAnimation ? '' : 'animate'}"
				role="article"
				aria-label="${msg.role === 'user' ? this.tr('aria_you', 'You') : 'Z'} ${this.tr('aria_at', 'at')} ${this.formatDateTime(msg.timestamp)}">
				<div class="bubble">
					<div class="bubble-content">${this.renderContent(msg.content)}</div>
					
					${msg.pending_actions && msg.pending_actions.length > 0 ? `
						<div class="action-buttons">
							${msg.pending_actions.map(action => `
								<div class="action-group">
									<p class="action-desc">${action.description}</p>
									<div class="action-row">
										<button class="action-btn confirm-btn" data-action-id="${action.id}" data-msg-idx="${realIdx}">Confirm</button>
										<button class="action-btn cancel-btn" data-action-id="${action.id}" data-msg-idx="${realIdx}">Cancel</button>
									</div>
								</div>
							`).join('')}
						</div>
					` : ''}

					<div class="bubble-footer" aria-hidden="true">
						${msg.model ? `<span class="model-tag">${msg.model}</span>` : ''}
						${msg.channel ? `<span class="channel-tag">${msg.channel}</span>` : ''}
						<span class="time">${this.formatDateTime(msg.timestamp)}</span>
					</div>
				</div>
			</div>
		`}).join('');

		// Attach listeners to action buttons
		this.shadowRoot?.querySelectorAll('.confirm-btn').forEach(btn => {
			btn.addEventListener('click', (e) => {
				const target = e.target as HTMLButtonElement;
				this.confirmAction(target.dataset.actionId!, parseInt(target.dataset.msgIdx!));
			});
		});
		this.shadowRoot?.querySelectorAll('.cancel-btn').forEach(btn => {
			btn.addEventListener('click', (e) => {
				const target = e.target as HTMLButtonElement;
				this.cancelAction(target.dataset.actionId!, parseInt(target.dataset.msgIdx!));
			});
		});

		// Restore typing indicator if it was there
		if (typing) container.prepend(typing);

		// Apply contrast-aware text color to every agent bubble
		this.applyBubbleTextColor();

		// Apply Goo Mode liquification if enabled
		this.applyGooLiquification();
	}

	/**
	 * Apply active Goo Mode effects to chat elements.
	 * Uses CSS-only bouncy entrance animation (no SVG filter on containers).
	 */
	private applyGooLiquification() {
		const isGoo = localStorage.getItem('goo-mode') === 'true';
		const messages = this.shadowRoot?.querySelectorAll('.message.animate');

		if (isGoo && messages) {
			messages.forEach(msg => {
				const bubble = msg.querySelector('.bubble');
				if (bubble) {
					(bubble as HTMLElement).style.animation = 'oz-goo-msg 0.7s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards';
				}
			});
		}
	}

	/**
	 * Parse a CSS hex colour string (#rgb or #rrggbb) into {r,g,b} components.
	 * Returns null when the input cannot be parsed.
	 */
	private parseHex(color: string): { r: number; g: number; b: number } | null {
		// Handle hsla(H, S%, L%, A) and hsl(H, S%, L%)
		const hm = /hsla?\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%/.exec(color);
		if (hm) {
			const h = +hm[1], s = +hm[2] / 100, l = +hm[3] / 100;
			const k = (n: number) => (n + h / 30) % 12;
			const a = s * Math.min(l, 1 - l);
			const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
			return { r: Math.round(f(0) * 255), g: Math.round(f(8) * 255), b: Math.round(f(4) * 255) };
		}
		// Handle #RGB and #RRGGBB
		const clean = color.replace(/^#/, '');
		if (clean.length === 3) {
			return {
				r: parseInt(clean[0] + clean[0], 16),
				g: parseInt(clean[1] + clean[1], 16),
				b: parseInt(clean[2] + clean[2], 16),
			};
		}
		if (clean.length === 6) {
			return {
				r: parseInt(clean.slice(0, 2), 16),
				g: parseInt(clean.slice(2, 4), 16),
				b: parseInt(clean.slice(4, 6), 16),
			};
		}
		return null;
	}

	/**
	 * WCAG 2.1 relative luminance for a sRGB colour.
	 * https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
	 */
	private relativeLuminance({ r, g, b }: { r: number; g: number; b: number }): number {
		const toLinear = (c: number): number => {
			const s = c / 255;
			return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
		};
		return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
	}

	/**
	 * WCAG contrast ratio between two relative luminance values.
	 * Returns a value in the range [1, 21].
	 */
	private contrastRatio(l1: number, l2: number): number {
		const lighter = Math.max(l1, l2);
		const darker = Math.min(l1, l2);
		return (lighter + 0.05) / (darker + 0.05);
	}

	/**
	 * Determine whether black or white text provides better contrast against
	 * the agent bubble gradient background.
	 *
	 * The gradient runs from --accent-color to --accent-secondary.  We
	 * approximate the perceptual midpoint by linearly blending the two
	 * endpoint colours at 50 % and then comparing contrast ratios.
	 */
	private pickBubbleTextColor(): '#000000' | '#ffffff' {
		const style = getComputedStyle(document.documentElement);
		const hex1 = style.getPropertyValue('--accent-color').trim() || 'hsla(173, 80%, 40%, 1)';
		const hex2 = style.getPropertyValue('--accent-secondary').trim() || 'hsla(216, 100%, 50%, 1)';

		const c1 = this.parseHex(hex1);
		const c2 = this.parseHex(hex2);

		if (!c1 || !c2) return '#ffffff';

		// Blend at gradient midpoint (t = 0.5)
		const mid = {
			r: Math.round((c1.r + c2.r) / 2),
			g: Math.round((c1.g + c2.g) / 2),
			b: Math.round((c1.b + c2.b) / 2),
		};

		const L = this.relativeLuminance(mid);
		const contrastWhite = this.contrastRatio(1.0, L);
		const contrastBlack = this.contrastRatio(L, 0.0);

		return contrastBlack > contrastWhite ? '#000000' : '#ffffff';
	}

	/**
	 * Apply the contrast-chosen text colour to every rendered assistant bubble.
	 * Called automatically at the end of renderMessages().
	 */
	private applyBubbleTextColor(): void {
		const color = this.pickBubbleTextColor();
		this.shadowRoot
			?.querySelectorAll<HTMLElement>('.message.assistant .bubble')
			.forEach(bubble => { bubble.style.color = color; });
	}

	private renderContent(str: string): string {
		// 1. Basic HTML escaping
		let html = str
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');

		// 2. Bold: **text**
		html = html.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');

		// 3. Links: [text](url)
		html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" class="chat-link">$1</a>');

		// 4. Newlines to <br>
		html = html.replace(/\n/g, '<br>');

		return html;
	}

	private sendSVG(): string {
		return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="oz-goo-blob"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
	}

	private spinnerSVG(): string {
		return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinner"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"/><path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/></svg>`;
	}

	private chatSVG(): string {
		return `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
	}

	render() {
		if (!this.shadowRoot) return;
		this.shadowRoot.innerHTML = `
		<style>
					${ACCESSIBILITY_STYLES}
					${SCROLLBAR_STYLES}
					${GOO_STYLES}
					h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1rem 0; color: var(--text-primary, hsla(0, 0%, 100%, 1)); letter-spacing: 0.02em; }
			:host {
				display: block;
			}

			

			h2 .badge {
				font-size: 0.65rem;
				font-weight: 700;
				text-transform: uppercase;
				letter-spacing: 0.08em;
				background: linear-gradient(135deg, var(--accent-color), var(--accent-secondary));
				color: var(--text-primary, hsla(0, 0%, 100%, 1));
				padding: 0.2rem 0.6rem;
				border-radius: 2rem;
			}

			/* ── Messages area ── */
			#messages {
				min-height: 200px;
				max-height: 420px;
				overflow-y: auto;
				display: flex;
				flex-direction: column-reverse;
				gap: 0.75rem;
				padding: 1.5rem 0.25rem;
				scroll-behavior: auto; /* Changed to auto to prevent initial scroll movement */
				mask-image: linear-gradient(to bottom, transparent 0%, black 10%, black 100%);
				-webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 10%, black 100%);
				overflow-anchor: auto;
				scroll-padding: 1rem 0;
			}

			/* ── Empty state ── */
			.empty-state {
				display: flex;
				flex-direction: column;
				align-items: center;
				justify-content: center;
				min-height: 180px;
				gap: 0.5rem;
				text-align: center;
				margin: auto; /* Ensures centering in column-reverse */
			}

			.empty-icon {
				color: var(--text-faint, hsla(0, 0%, 100%, 0.2));
				margin-bottom: 0.25rem;
			}

			.empty-state p {
				color: var(--text-secondary, hsla(0, 0%, 100%, 0.7));
				font-size: 1rem;
				font-weight: 500;
				margin: 0;
			}

			.empty-state > span {
				color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
				font-size: 0.85rem;
			}

			.command-hints {
				display: flex;
				flex-wrap: wrap;
				gap: 0.5rem;
				justify-content: center;
				margin-top: 1rem;
			}
			
			.cmd-chip {
				background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
				border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
				/* --accent-text adapts: dark mode uses the bright accent (fine on dark bg),
				   light mode uses a much darker shade (22% L) for WCAG AA 4.5:1 on near-white surfaces. */
				color: var(--accent-text, var(--accent-primary, hsla(173, 80%, 40%, 1)));
				padding: 0.2rem 0.6rem;
				border-radius: var(--radius-sm, 0.35rem);
				font-size: 0.75rem;
				font-family: inherit;
				cursor: pointer;
				transition: all var(--duration-fast, 0.2s);
				min-height: 44px; /* WCAG 2.1 AA */
				display: inline-flex;
				align-items: center;
			}
			.cmd-chip:hover, .cmd-chip:focus-visible {
				background: var(--surface-card-hover, hsla(0, 0%, 100%, 0.05));
				border-color: var(--border-accent, hsla(173, 80%, 40%, 0.25));
				outline: 2px solid var(--accent-color, hsla(173, 80%, 40%, 1));
				outline-offset: 2px;
			}

			/* ── Message bubbles ── */
			.message {
				display: flex;
				max-width: 85%;
				opacity: 0; transform: translateY(12px); /* Initial state for animation */
			}

			.message.animate {
				animation: msgIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
			}

			.message:not(.animate) {
				opacity: 1; transform: translateY(0); /* Immediate state for history */
			}

			.message.user {
				align-self: flex-end;
			}

			.message.assistant {
				align-self: center;
				max-width: 95%;
				width: 100%;
				margin: 0.5rem 0;
			}

			.bubble {
				padding: 0.75rem 1.25rem;
				border-radius: var(--radius-lg, 0.85rem);
				font-size: 0.95rem;
				line-height: 1.6;
				position: relative;
				transition: transform var(--duration-base, 0.3s) var(--ease-snap);
			}

			.message:hover .bubble {
				transform: scale(1.005);
			}

			.message.user .bubble {
				background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
				color: var(--text-primary, hsla(0, 0%, 100%, 1));
				border: 1px solid var(--border-medium, hsla(0, 0%, 100%, 0.12));
				border-bottom-right-radius: var(--radius-xs, 0.25rem);
				box-shadow: 0 8px 32px hsla(0, 0%, 0%, 0.25), inset 0 1px 0 hsla(0, 0%, 100%, 0.05);
			}

			.message.assistant .bubble {
				background: linear-gradient(135deg, var(--accent-color), var(--accent-secondary));
				color: var(--text-primary, hsla(0, 0%, 100%, 1));
				border: 1px solid hsla(0, 0%, 100%, 0.2);
				border-radius: var(--radius-xl, 1.25rem);
				border-bottom-left-radius: var(--radius-xs, 0.25rem);
				box-shadow: 0 12px 48px hsla(0, 0%, 0%, 0.4), inset 0 1px 0 hsla(0, 0%, 100%, 0.2);
				padding: 1.5rem 2rem;
			}

			.bubble .time {
				display: block;
				font-size: 0.7rem;
				color: var(--text-faint, hsla(0, 0%, 100%, 0.2));
				text-align: right;
				font-weight: 500;
			}

			/* Assistant bubble sub-elements inherit the contrast-chosen text colour */
			.message.assistant .bubble .time,
			.message.assistant .bubble .model-tag,
			.message.assistant .bubble .channel-tag {
				color: inherit;
			}

			.bubble-footer {
				display: flex;
				justify-content: space-between;
				align-items: center;
				gap: 0.75rem;
				margin-top: 0.5rem;
			}

			.model-tag {
				font-size: 0.65rem;
				color: var(--accent-color, hsla(173, 80%, 40%, 1));
				opacity: 0.7;
				text-transform: uppercase;
				letter-spacing: 0.05em;
				font-weight: 700;
			}

			.channel-tag {
				font-size: 0.65rem;
				color: var(--text-faint, hsla(0, 0%, 100%, 0.2));
				text-transform: uppercase;
				letter-spacing: 0.05em;
				font-weight: 600;
			}

			.message.assistant .bubble .time {
				text-align: left;
				opacity: 0.6;
			}

			.message.assistant .bubble .model-tag {
				opacity: 0.7;
			}

			.message.assistant .bubble .channel-tag {
				opacity: 0.4;
			}

			.bubble-content a {
				color: var(--accent-color, hsla(173, 80%, 40%, 1));
				text-decoration: underline;
				text-underline-offset: 4px;
				transition: color 0.2s;
			}
			.message.user .bubble-content a {
				color: var(--text-primary, hsla(0, 0%, 100%, 1));
				text-decoration-color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
			}
			.bubble-content a:hover {
				color: var(--accent-secondary, hsla(216, 100%, 50%, 1));
			}

			/* ── Typing indicator ── */
			.typing-bubble {
				display: flex;
				align-items: center;
				gap: 0.4rem;
				padding: 1rem 1.5rem;
				background: var(--surface-card, hsla(0, 0%, 100%, 0.03));
				border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
				border-radius: var(--radius-lg, 0.85rem);
			}

			.dot {
				width: 6px;
				height: 6px;
				border-radius: 50%;
				background: var(--text-muted, hsla(0, 0%, 100%, 0.4));
				animation: typing 1.4s infinite ease-in-out;
			}

			.dot:nth-child(2) { animation-delay: 0.2s; }
			.dot:nth-child(3) { animation-delay: 0.4s; }

			@keyframes typing {
				0%, 60%, 100% { transform: translateY(0); opacity: 0.3; }
				30% { transform: translateY(-4px); opacity: 1; }
			}

			.action-buttons {
				margin-top: 1.25rem;
				display: flex;
				flex-direction: column;
				gap: 1rem;
				background: hsla(0, 0%, 0%, 0.15);
				padding: 1rem;
				border-radius: var(--radius-md, 0.5rem);
				border: 1px solid hsla(0, 0%, 100%, 0.1);
			}
			.action-group {
				display: flex;
				flex-direction: column;
				gap: 0.5rem;
			}
			.action-desc {
				margin: 0;
				font-size: 0.85rem;
				font-weight: 500;
				color: inherit;
				opacity: 0.9;
			}
			.action-row {
				display: flex;
				gap: 0.5rem;
			}
			.action-btn {
				flex: 1;
				padding: 0.6rem;
				border-radius: var(--radius-sm, 0.35rem);
				border: 1px solid hsla(0, 0%, 100%, 0.2);
				font-size: 0.8rem;
				font-weight: 700;
				cursor: pointer;
				transition: all 0.2s;
				text-transform: uppercase;
				letter-spacing: 0.05em;
			}
			.confirm-btn {
				background: hsla(0, 0%, 100%, 0.2);
				color: inherit;
			}
			.confirm-btn:hover {
				background: hsla(0, 0%, 100%, 0.3);
			}
			.cancel-btn {
				background: transparent;
				color: inherit;
				opacity: 0.7;
			}
			.cancel-btn:hover {
				opacity: 1;
				background: hsla(0, 0%, 0%, 0.2);
			}

			/* ── Input area ── */
			.input-area {
				display: flex;
				gap: 0.75rem;
				align-items: flex-end;
				margin-top: 1rem;
				padding-top: 1rem;
				border-top: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
			}

			textarea {
				flex: 1;
				resize: none;
				background: hsla(0, 0%, 0%, 0.3);
				border: 1px solid var(--border-subtle, hsla(0, 0%, 100%, 0.08));
				border-radius: var(--radius-md, 0.5rem);
				padding: 0.75rem 1.25rem;
				color: var(--text-primary, hsla(0, 0%, 100%, 1));
				font-family: inherit;
				font-size: 1.1rem;
				line-height: 1.4;
				outline: none;
				transition: all var(--duration-fast, 0.2s);
				min-height: 56px;
				max-height: 200px;
				overflow-y: auto;
			}

			textarea::placeholder {
				color: var(--text-muted, hsla(0, 0%, 100%, 0.4));
			}

			textarea:focus {
				border-color: var(--accent-color, hsla(173, 80%, 40%, 1));
				background: hsla(0, 0%, 0%, 0.4);
				box-shadow: 0 0 0 3px rgba(var(--accent-color-rgb, 20, 184, 166), 0.1);
			}

			#send-btn {
				width: 56px;
				height: 56px;
				border-radius: var(--radius-md, 0.5rem);
				border: 1px solid var(--border-accent, hsla(173, 80%, 40%, 0.25));
				background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.1);
				color: var(--accent-color, hsla(173, 80%, 40%, 1));
				cursor: pointer;
				display: flex;
				align-items: center;
				justify-content: center;
				flex-shrink: 0;
				transition: all var(--duration-fast, 0.2s);
			}

			#send-btn svg { width: 18px; height: 18px; transition: transform var(--duration-fast, 0.2s); }
			#send-btn:hover:not(:disabled) svg { transform: translateX(2px) translateY(-1px) scale(1.1); }

			.oz-goo-blob {
				position: relative;
				z-index: 1;
			}

			#send-btn:hover:not(:disabled) {
				background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
				border-color: var(--accent-color, hsla(173, 80%, 40%, 1));
				transform: translateY(-2px);
				box-shadow: 0 4px 12px rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
			}

			#send-btn:disabled {
				opacity: 0.4;
				cursor: not-allowed;
				filter: grayscale(1);
			}

			/* ── Spinner ── */
			.spinner {
				animation: spin 0.8s linear infinite; scale(0.98); }
				to	 { opacity: 1; transform: translateY(0) scale(1); }
			}

			.message.assistant .bubble {
				animation: msgIn 0.5s cubic-bezier(0.23, 1, 0.32, 1) forwards;
				transition: background var(--duration-fast, 0.2s);
			}

			.message.user .bubble {
				transition: background var(--duration-fast, 0.2s);
			}

			@keyframes msgIn {
				from { opacity: 0; transform: translateY(12px); }
				to	 { opacity: 1; transform: translateY(0); }
			}

			@keyframes msgInGoo {
				from { opacity: 0; transform: translateY(24px) scale(0.8); filter: blur(10px); }
				to	 { opacity: 1; transform: translateY(0) scale(1); filter: blur(0); }
			}

			/* Reduced-motion overrides beyond shared module */
			@media (prefers-reduced-motion: reduce) {
				.message, .message.assistant .bubble,
				.spinner, .dot { animation: none !important; }
				.message { opacity: 1; transform: none; }
				textarea, #send-btn { transition: none; }
			}
			@media (forced-colors: active) {
				h2 .badge { background: ButtonFace; border: 1px solid ButtonText; color: ButtonText; }
				.cmd-chip { border: 1px solid Highlight; color: Highlight; }
				.message .bubble { border: 1px solid ButtonText; }
				.model-tag { color: LinkText; }
				#send-btn { border: 1px solid Highlight; }
			}
		</style>

		<div id="messages"
			role="log"
			aria-live="polite"
			aria-relevant="additions"
			aria-label="${this.tr('aria_chat_history', 'Chat history')}"
			aria-atomic="false">
			<div class="empty-state">
				<div class="empty-icon" aria-hidden="true">${this.chatSVG()}</div>
				<p>${this.tr('start_chat_with_z', 'Start a conversation with Z')}</p>
				<span>${this.tr('chat_hint', 'Ask anything — manage tasks, query memories, or get briefed.')}</span>
				<nav class="command-hints" aria-label="${this.tr('aria_quick_commands', 'Quick commands')}">
					<ul role="list" style="display:flex;flex-wrap:wrap;gap:0.5rem;justify-content:center;list-style:none;padding:0;margin:1rem 0 0 0;">
						<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/day — ${this.tr('aria_cmd_day', 'Daily briefing command')}">/day</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/week — ${this.tr('aria_cmd_week', 'Weekly briefing command')}">/week</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/month — ${this.tr('aria_cmd_month', 'Monthly briefing command')}">/month</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/year — ${this.tr('aria_cmd_year', 'Yearly briefing command')}">/year</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/memory — ${this.tr('aria_cmd_memory', 'Search memory command')}">/memory</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/add — ${this.tr('aria_cmd_add', 'Add memory command')}">/add</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" role="button" aria-label="/think — ${this.tr('aria_cmd_think', 'Deep think command')}">/think</span></li>
					</ul>
				</nav>
			</div>
		</div>

		<div class="input-area" role="group" aria-label="${this.tr('aria_message_input', 'Message input')}">
			<textarea id="chat-input" rows="1" placeholder="${this.tr('ask_z_placeholder', 'Ask Z something...')}" aria-label="${this.tr('aria_message', 'Message')}" autocomplete="off" spellcheck="true">${this.draft}</textarea>
			<button id="send-btn" aria-label="${this.tr('aria_send_message', 'Send message')}" type="button">${this.sendSVG()}</button>
		</div>
		`;

		// Re-attach listeners to the new elements every time we render
		this.setupListeners();
	}
}

customElements.define('chat-prompt', ChatPrompt);
