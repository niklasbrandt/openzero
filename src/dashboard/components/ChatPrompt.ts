interface ChatMessage {
	role: 'user' | 'assistant';
	content: string;
	timestamp: Date;
}

export class ChatPrompt extends HTMLElement {
	private messages: ChatMessage[] = [];
	private isLoading = false;

	constructor() {
		super();
		this.attachShadow({ mode: 'open' });
	}

	connectedCallback() {
		this.render();
		this.setupListeners();
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

		// Auto-resize textarea
		input?.addEventListener('input', () => {
			if (input) {
				input.style.height = 'auto';
				input.style.height = Math.min(input.scrollHeight, 160) + 'px';
			}
		});
	}

	private async handleSend() {
		const input = this.shadowRoot?.querySelector<HTMLTextAreaElement>('#chat-input');
		const message = input?.value.trim();
		if (!message || this.isLoading) return;

		// Add user message
		this.messages.push({ role: 'user', content: message, timestamp: new Date() });
		if (input) {
			input.value = '';
			input.style.height = 'auto';
		}
		this.renderMessages();
		this.scrollToBottom();

		// Send to API
		this.isLoading = true;
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

			this.messages.push({
				role: 'assistant',
				content: data.reply || 'No response received.',
				timestamp: new Date(),
			});
		} catch (e) {
			// Simulate a brief delay for natural feel
			await new Promise(r => setTimeout(r, 800));
			this.hideTypingIndicator();

			const offlineReplies = [
				`Received: "${message}"\n\nZ is currently in standby. Deploy the backend to enable live responses.`,
				`Message queued. Z will process this once the backend is online.`,
				`Got it. The backend API isn't connected yet — once it is, Z will handle conversations like this in real time.`,
				`Noted. Connect the OpenZero backend to unlock live AI chat.`,
			];
			const reply = offlineReplies[this.messages.length % offlineReplies.length];

			this.messages.push({
				role: 'assistant',
				content: reply,
				timestamp: new Date(),
			});
		} finally {
			this.isLoading = false;
			this.updateSendButton();
			this.renderMessages();
			this.scrollToBottom();
			input?.focus();
		}
	}

	private scrollToBottom() {
		requestAnimationFrame(() => {
			const container = this.shadowRoot?.querySelector('#messages');
			if (container) container.scrollTop = container.scrollHeight;
		});
	}

	private showTypingIndicator() {
		const container = this.shadowRoot?.querySelector('#messages');
		if (!container) return;
		const indicator = document.createElement('div');
		indicator.id = 'typing';
		indicator.className = 'message assistant';
		indicator.innerHTML = `
			<div class="bubble typing-bubble">
				<span class="dot"></span>
				<span class="dot"></span>
				<span class="dot"></span>
			</div>
		`;
		container.appendChild(indicator);
		this.scrollToBottom();
	}

	private hideTypingIndicator() {
		this.shadowRoot?.querySelector('#typing')?.remove();
	}

	private updateSendButton() {
		const btn = this.shadowRoot?.querySelector<HTMLButtonElement>('#send-btn');
		if (btn) {
			btn.disabled = this.isLoading;
			btn.innerHTML = this.isLoading ? this.spinnerSVG() : this.sendSVG();
		}
	}

	private formatTime(date: Date): string {
		return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	private renderMessages() {
		const container = this.shadowRoot?.querySelector('#messages');
		if (!container) return;

		// Remove typing indicator if present
		this.shadowRoot?.querySelector('#typing')?.remove();

		if (this.messages.length === 0) {
			container.innerHTML = `
				<div class="empty-state">
					<div class="empty-icon">${this.chatSVG()}</div>
					<p>Start a conversation with Z</p>
					<span>Ask anything — manage tasks, query memories, or get briefed.</span>
				</div>
			`;
			return;
		}

		container.innerHTML = this.messages.map(msg => `
			<div class="message ${msg.role}">
				<div class="bubble">
					<div class="bubble-content">${this.escapeHTML(msg.content)}</div>
					<span class="time">${this.formatTime(msg.timestamp)}</span>
				</div>
			</div>
		`).join('');
	}

	private escapeHTML(str: string): string {
		return str
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/\n/g, '<br>');
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
			:host {
				display: block;
			}

			h2 {
				color: #fff;
				font-weight: 200;
				letter-spacing: -0.025em;
				margin: 0 0 1rem 0;
				font-size: 1.25rem;
				display: flex;
				align-items: center;
				gap: 0.5rem;
			}

			h2 .badge {
				font-size: 0.65rem;
				font-weight: 700;
				text-transform: uppercase;
				letter-spacing: 0.08em;
				background: linear-gradient(135deg, #14B8A6, #0066FF);
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
				flex-direction: column;
				gap: 0.75rem;
				padding: 0.25rem 0.25rem 1rem 0.25rem;
				scroll-behavior: smooth;
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
			}

			.empty-icon {
				color: rgba(255,255,255,0.15);
				margin-bottom: 0.25rem;
			}

			.empty-state p {
				color: rgba(255,255,255,0.5);
				font-size: 1rem;
				font-weight: 500;
				margin: 0;
			}

			.empty-state span {
				color: rgba(255,255,255,0.25);
				font-size: 0.85rem;
			}

			/* ── Message bubbles ── */
			.message {
				display: flex;
				max-width: 85%;
				animation: msgIn 0.3s ease forwards;
			}

			.message.user {
				align-self: flex-end;
			}

			.message.assistant {
				align-self: flex-start;
			}

			.bubble {
				padding: 0.75rem 1rem;
				border-radius: 1.25rem;
				font-size: 0.9rem;
				line-height: 1.55;
				position: relative;
			}

			.message.user .bubble {
				background: linear-gradient(135deg, #14B8A6, #0066FF);
				color: #fff;
				border-bottom-right-radius: 0.35rem;
				box-shadow: 0 4px 16px rgba(20, 184, 166, 0.25);
			}

			.message.assistant .bubble {
				background: rgba(255, 255, 255, 0.06);
				backdrop-filter: blur(12px) saturate(1.2);
				-webkit-backdrop-filter: blur(12px) saturate(1.2);
				color: rgba(255, 255, 255, 0.9);
				border: 1px solid rgba(255, 255, 255, 0.06);
				border-bottom-left-radius: 0.35rem;
			}

			.bubble .time {
				display: block;
				font-size: 0.65rem;
				color: rgba(255,255,255,0.35);
				margin-top: 0.35rem;
				text-align: right;
			}

			.message.assistant .bubble .time {
				text-align: left;
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
				font-family: 'Inter', system-ui, -apple-system, sans-serif;
				font-size: 0.9rem;
				line-height: 1.5;
				outline: none;
				transition: border-color 0.3s ease, background 0.3s ease, box-shadow 0.3s ease;
				min-height: 44px;
				max-height: 160px;
				overflow-y: auto;
			}

			textarea::placeholder {
				color: rgba(255,255,255,0.25);
			}

			textarea:focus {
				border-color: rgba(20, 184, 166, 0.4);
				background: rgba(0, 0, 0, 0.28);
				box-shadow: 0 0 20px rgba(20, 184, 166, 0.08);
			}

			#send-btn {
				width: 44px;
				height: 44px;
				border-radius: 0.6rem;
				border: 1px solid rgba(20, 184, 166, 0.2);
				background: rgba(20, 184, 166, 0.12);
				color: #14B8A6;
				cursor: pointer;
				display: flex;
				align-items: center;
				justify-content: center;
				flex-shrink: 0;
				transition: all 0.25s ease;
			}

			#send-btn:hover:not(:disabled) {
				background: rgba(20, 184, 166, 0.22);
				border-color: rgba(20, 184, 166, 0.4);
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
				from { opacity: 0; transform: translateY(8px); }
				to   { opacity: 1; transform: translateY(0); }
			}
		</style>

		<h2>
			Chat with Z
			<span class="badge">AI</span>
		</h2>

		<div id="messages">
			<div class="empty-state">
				<div class="empty-icon">${this.chatSVG()}</div>
				<p>Start a conversation with Z</p>
				<span>Ask anything — manage tasks, query memories, or get briefed.</span>
			</div>
		</div>

		<div class="input-area">
			<textarea id="chat-input" rows="1" placeholder="Ask Z something…"></textarea>
			<button id="send-btn" aria-label="Send message">${this.sendSVG()}</button>
		</div>
		`;
	}
}

customElements.define('chat-prompt', ChatPrompt);
