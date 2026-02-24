export class AgentCore extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
    }

    connectedCallback() {
        this.render();
    }

    render() {
        if (!this.shadowRoot) return;

        this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .core {
          background: rgba(10, 15, 30, 0.4);
          border: 1px solid rgba(20, 184, 166, 0.15);
          padding: 1.5rem;
          position: relative;
          overflow: hidden;
          color: #fff;
          font-family: 'Inter', sans-serif;
        }
        .core::before {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0; height: 1px;
          background: linear-gradient(90deg, transparent, var(--accent-color), transparent);
          animation: scan 3s linear infinite;
        }
        @keyframes scan {
          0% { transform: translateY(-50px); }
          100% { transform: translateY(200px); }
        }
        .status-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 1.5rem;
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--accent-color);
        }
        .pulse {
          width: 8px;
          height: 8px;
          background: var(--accent-color);
          border-radius: 50%;
          box-shadow: 0 0 10px var(--accent-color);
          display: inline-block;
          margin-right: 8px;
          animation: blink 1.5s infinite;
        }
        @keyframes blink {
          50% { opacity: 0.3; }
        }
        .metrics {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1rem;
        }
        .metric-box {
          border-left: 2px solid rgba(255, 255, 255, 0.1);
          padding-left: 0.75rem;
        }
        .metric-label { font-size: 0.65rem; color: rgba(255,255,255,0.4); }
        .metric-value { font-size: 1rem; font-weight: 600; margin-top: 2px; }
        .dna-string {
          margin-top: 1.5rem;
          font-family: 'Fira Code', monospace;
          font-size: 0.6rem;
          color: rgba(20, 184, 166, 0.3);
          word-break: break-all;
          line-height: 1;
        }
      </style>
      <div class="core">
        <div class="status-header">
          <span><span class="pulse"></span>Neural Link: Active</span>
          <span>Latency: 14ms</span>
        </div>
        <div class="metrics">
          <div class="metric-box">
            <div class="metric-label">System Mode</div>
            <div class="metric-value">Sentinel</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Grounding</div>
            <div class="metric-value">Strict</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Memory Index</div>
            <div class="metric-value">Optimized</div>
          </div>
          <div class="metric-box">
            <div class="metric-label">Privacy Shield</div>
            <div class="metric-value">Active</div>
          </div>
        </div>
        <div class="dna-string">
          0100010101111000011001010110001101110101011101000110100101101111011011100101111101011010011001010111001001101111
        </div>
      </div>
    `;
    }
}
customElements.define('agent-core', AgentCore);
