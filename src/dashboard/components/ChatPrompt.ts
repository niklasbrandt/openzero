interface ChatMessage {
	role: 'user' | 'assistant';
	content: string;
	timestamp: Date;
	model?: string;
}

export class ChatPrompt extends HTMLElement {
	private messages: ChatMessage[] = [];
	private pendingRequests = 0;
	private pendingRetry: string | null = null;
	private t: Record<string, string> = {};
	private draft = '';

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
		window.addEventListener('identity-updated', () => {
			this.loadTranslations().then(() => this.render());
		});
	}

	private async loadTranslations() {
		try {
			const res = await fetch('/api/dashboard/translations');
			if (res.ok) this.t = await res.json();
		} catch (_) { }
	}

	private tr(key: string, fallback: string): string {
		return this.t[key] || fallback;
	}

	private async loadHistory() {
		try {
			const res = await fetch('/api/dashboard/chat/history?limit=20');
			if (!res.ok) return;
			const data = await res.json();
			if (!data.messages?.length) return;

			// Map messages (oldest at index 0)
			this.messages = data.messages.map((m: any) => ({
				role: m.role === 'z' ? 'assistant' : 'user',
				content: m.content,
				timestamp: new Date(m.at),
				channel: m.channel,
			}));

			// Render immediately. With flex-direction: column-reverse, 
			// it will show at the bottom without any scrolling movement.
			this.renderMessages(true); // pass true to skip animations for history
		} catch (e) {
			// Silent fail -- chat still works without history
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

		// Retry failed messages when user comes back to the tab
		document.addEventListener('visibilitychange', () => {
			if (document.visibilityState === 'visible' && this.pendingRetry && this.pendingRequests === 0) {
				this.retryPending();
			}
		});

		window.addEventListener('focus', () => {
			if (this.pendingRetry && this.pendingRequests === 0) {
				this.retryPending();
			}
		});
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

		// UX for slow local CPU generation
		const slowWarningTimer = setTimeout(() => {
			const typingBubble = this.shadowRoot?.querySelector('.typing-bubble');
			if (typingBubble) {
				const warning = document.createElement('div');
				warning.style.fontSize = '0.75rem';
				warning.style.color = 'rgba(255, 255, 255, 0.78)';
				warning.style.marginTop = '0.5rem';
				warning.style.marginLeft = '0.5rem';
				warning.innerText = this.tr('warming_up', 'Warming up local engine...');
				typingBubble.parentElement?.appendChild(warning);
			}
		}, 6000);

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
			});

			// Notification sound
			try {
				const audio = new Audio('https://assets.mixkit.co/active_storage/sfx/2354/2354-preview.mp3');
				audio.volume = 0.4;
				audio.play();
			} catch (_) { }

			if (data.actions && data.actions.length > 0) {
				window.dispatchEvent(new CustomEvent('refresh-data', {
					detail: { actions: data.actions }
				}));
			}
		} catch (e) {
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
			clearTimeout(slowWarningTimer);
			this.pendingRequests = Math.max(0, this.pendingRequests - 1);
			this.updateSendButton();
			if (this.pendingRequests <= 0) this.hideTypingIndicator();
			this.renderMessages();
			this.scrollToBottom();
			input?.focus();

			// Attach retry click handler if there's a pending message
			if (this.pendingRetry) {
				const lastBubble = this.shadowRoot?.querySelector('.message.assistant:last-child .bubble');
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
							<li role="listitem"><span class="cmd-chip" tabindex="0">/day</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0">/week</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0">/month</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0">/year</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0">/memory</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0">/add</span></li>
							<li role="listitem"><span class="cmd-chip" tabindex="0">/think</span></li>
						</ul>
					</nav>
				</div>
			`;
			return;
		}

		// Reverse rendering for column-reverse. Newest (last in array) is first child (bottom).
		container.innerHTML = [...this.messages].reverse().map((msg) => `
			<div class="message ${msg.role} ${skipAnimation ? '' : 'animate'}"
				role="article"
				aria-label="${msg.role === 'user' ? 'You' : 'Z'} at ${this.formatDateTime(msg.timestamp)}">
				<div class="bubble">
					<div class="bubble-content">${this.renderContent(msg.content)}</div>
					<div class="bubble-footer" aria-hidden="true">
						${msg.model ? `<span class="model-tag">${msg.model}</span>` : ''}
						${(msg as any).channel ? `<span class="channel-tag">${(msg as any).channel}</span>` : ''}
				<span class="time">${this.formatDateTime(msg.timestamp)}</span>
					</div>
				</div>
			</div>
		`).join('');

		// Restore typing indicator if it was there
		if (typing) container.prepend(typing);

		// Apply contrast-aware text color to every agent bubble
		this.applyBubbleTextColor();
	}

	/**
	 * Parse a CSS hex colour string (#rgb or #rrggbb) into {r,g,b} components.
	 * Returns null when the input cannot be parsed.
	 */
	private parseHex(hex: string): { r: number; g: number; b: number } | null {
		const clean = hex.replace(/^#/, '');
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
		const darker  = Math.min(l1, l2);
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
		const hex1  = style.getPropertyValue('--accent-color').trim()    || '#14B8A6';
		const hex2  = style.getPropertyValue('--accent-secondary').trim() || '#0066FF';

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
		return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
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
					h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1rem 0; color: #fff; letter-spacing: 0.02em; }
			:host {
				display: block;
			}

			

			h2 .badge {
				font-size: 0.65rem;
				font-weight: 700;
				text-transform: uppercase;
				letter-spacing: 0.08em;
				background: linear-gradient(135deg, var(--accent-color), var(--accent-secondary));
				color: #fff;
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

			#messages::-webkit-scrollbar { width: 4px; }
			#messages::-webkit-scrollbar-track { background: transparent; }
			#messages::-webkit-scrollbar-thumb {
				background: rgba(255,255,255,0.1);
				border-radius: 4px;
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
				color: rgba(255,255,255,0.333);
				margin-bottom: 0.25rem;
			}

			.empty-state p {
				color: rgba(255, 255, 255, 0.75);
				font-size: 1rem;
				font-weight: 500;
				margin: 0;
			}

			.empty-state span {
				color: rgba(255,255,255,0.66);
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
				background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.1);
				border: 1px solid rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
				color: var(--accent-color);
				padding: 0.2rem 0.5rem;
				border-radius: 0.4rem;
				font-size: 0.75rem;
				font-family: inherit;
				cursor: default;
			}

			/* ── Message bubbles ── */
			.message {
				display: flex;
				max-width: 85%;
				opacity: 0; transform: translateY(12px); /* Initial state for animation */
			}

			.message.animate {
				animation: msgIn 0.3s ease forwards;
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
				padding: 0.75rem 1rem;
				border-radius: 1.25rem;
				font-size: 0.9rem;
				line-height: 1.55;
				position: relative;
			}

			.message.user .bubble {
				background: linear-gradient(135deg, rgba(var(--accent-color-rgb, 20, 184, 166), 0.2), rgba(var(--accent-secondary-rgb, 0, 102, 255), 0.15));
				backdrop-filter: blur(12px);
				-webkit-backdrop-filter: blur(12px);
				color: #fff;
				border: 1px solid rgba(255, 255, 255, 0.12);
				border-bottom-right-radius: 0.35rem;
				box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.1);
			}

			.message.assistant .bubble {
				background: linear-gradient(135deg, var(--accent-color), var(--accent-secondary));
				backdrop-filter: blur(24px) saturate(1.8) brightness(1.2);
				-webkit-backdrop-filter: blur(24px) saturate(1.8) brightness(1.2);
				color: #fff;
				border: 1px solid rgba(255, 255, 255, 0.2);
				border-radius: 1.5rem;
				border-bottom-left-radius: 0.35rem; /* Sharp corner for agent */
				box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.2);
				padding: 1.25rem 1.75rem;
			}

			.bubble .time {
				display: block;
				font-size: 0.65rem;
				color: rgba(255,255,255,0.35);
				text-align: right;
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
				gap: 0.5rem;
				margin-top: 0.35rem;
			}

			.model-tag {
				font-size: 0.6rem;
				color: var(--accent-color);
				opacity: 0.7;
				text-transform: uppercase;
				letter-spacing: 0.05em;
				font-weight: 600;
			}

			.channel-tag {
				font-size: 0.6rem;
				color: rgba(255, 255, 255, 0.25);
				text-transform: uppercase;
				letter-spacing: 0.05em;
				font-weight: 500;
			}

			.message.assistant .bubble .time {
				text-align: left;
				opacity: 0.45;
			}

			.message.assistant .bubble .model-tag {
				opacity: 0.6;
			}

			.message.assistant .bubble .channel-tag {
				opacity: 0.35;
			}

			.bubble-content a {
				color: var(--accent-color);
				text-decoration: underline;
				text-underline-offset: 4px;
				transition: color 0.2s;
			}
			.message.user .bubble-content a {
				color: #fff;
				text-decoration-color: rgba(255, 255, 255, 0.4);
			}
			.bubble-content a:hover {
				color: var(--accent-secondary);
			}

			/* ── Typing indicator ── */
			.typing-bubble {
				display: flex;
				align-items: center;
				gap: 0.3rem;
				padding: 0.85rem 1.2rem;
			}

			.dot {
				width: 7px;
				height: 7px;
				border-radius: 50%;
				background: rgba(255,255,255,0.35);
				animation: typing 1.4s infinite ease-in-out;
			}

			.dot:nth-child(2) { animation-delay: 0.2s; }
			.dot:nth-child(3) { animation-delay: 0.4s; }

			@keyframes typing {
				0%, 60%, 100% { transform: translateY(0); opacity: 0.35; }
				30% { transform: translateY(-6px); opacity: 1; }
			}

			/* ── Input area ── */
			.input-area {
				display: flex;
				gap: 0.5rem;
				align-items: flex-end;
				margin-top: 0.75rem;
				padding-top: 0.75rem;
				border-top: 1px solid rgba(255,255,255,0.05);
			}

			textarea {
				flex: 1;
				resize: none;
				background: rgba(0, 0, 0, 0.2);
				backdrop-filter: blur(8px);
				-webkit-backdrop-filter: blur(8px);
				border: 1px solid rgba(255, 255, 255, 0.08);
				border-radius: 0.75rem;
				padding: 0.6rem 1rem;
				color: #fff;
				font-family: 'Inter', system-ui, sans-serif;
				font-size: 1.1rem;
				line-height: 1.2;
				outline: none;
				transition: border-color 0.3s ease, background 0.3s ease, box-shadow 0.3s ease;
				min-height: 63px;
				max-height: 160px;
				overflow-y: auto;
			}

			textarea::placeholder {
				color: rgba(255, 255, 255, 0.64);
			}

			textarea:focus {
				border-color: var(--accent-color);
				background: rgba(0, 0, 0, 0.28);
				box-shadow: 0 0 20px rgba(var(--accent-color-rgb, 20, 184, 166), 0.08);
			}

			#send-btn {
				width: 84px;
				height: 84px;
				border-radius: 0.6rem;
				border: 1px solid rgba(var(--accent-color-rgb, 20, 184, 166), 0.2);
				background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.12);
				color: var(--accent-color);
				cursor: pointer;
				display: flex;
				align-items: center;
				justify-content: center;
				flex-shrink: 0;
				transition: all 0.25s ease;
			}

			#send-btn:hover:not(:disabled) {
				background: rgba(var(--accent-color-rgb, 20, 184, 166), 0.22);
				border-color: var(--accent-color);
			}

			#send-btn:disabled {
				opacity: 0.5;
				cursor: not-allowed;
			}

			/* ── Spinner ── */
			.spinner {
				animation: spin 0.8s linear infinite;
			}

			@keyframes spin {
				to { transform: rotate(360deg); }
			}

			@keyframes msgIn {
				from { opacity: 0; transform: translateY(12px); }
				to	 { opacity: 1; transform: translateY(0); }
			}

			.message.assistant .bubble {
				animation: msgIn 0.5s cubic-bezier(0.23, 1, 0.32, 1) forwards;
			}
		</style>

		<div id="messages"
			role="log"
			aria-live="polite"
			aria-relevant="additions"
			aria-label="Chat history"
			aria-atomic="false">
			<div class="empty-state">
				<div class="empty-icon" aria-hidden="true">${this.chatSVG()}</div>
				<p>${this.tr('start_chat_with_z', 'Start a conversation with Z')}</p>
				<span>${this.tr('chat_hint', 'Ask anything — manage tasks, query memories, or get briefed.')}</span>
				<nav class="command-hints" aria-label="${this.tr('aria_quick_commands', 'Quick commands')}">
					<ul role="list" style="display:flex;flex-wrap:wrap;gap:0.5rem;justify-content:center;list-style:none;padding:0;margin:1rem 0 0 0;">
						<li role="listitem"><span class="cmd-chip" tabindex="0" aria-label="${this.tr('aria_cmd_day', 'Daily briefing command')}">/day</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" aria-label="${this.tr('aria_cmd_week', 'Weekly briefing command')}">/week</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" aria-label="${this.tr('aria_cmd_month', 'Monthly briefing command')}">/month</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" aria-label="${this.tr('aria_cmd_year', 'Yearly briefing command')}">/year</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" aria-label="${this.tr('aria_cmd_memory', 'Search memory command')}">/memory</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" aria-label="${this.tr('aria_cmd_add', 'Add memory command')}">/add</span></li>
						<li role="listitem"><span class="cmd-chip" tabindex="0" aria-label="${this.tr('aria_cmd_think', 'Deep think command')}">/think</span></li>
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
