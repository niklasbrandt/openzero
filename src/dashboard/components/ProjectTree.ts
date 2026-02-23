export class ProjectTree extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.render();
    this.fetchData();
    this.setupToggle();
    window.addEventListener('refresh-data', (e: any) => {
      if (e.detail.actions.includes('project') || e.detail.actions.includes('board')) {
        this.fetchData();
      }
    });
  }

  private setupToggle() {
    this.shadowRoot?.querySelector('#new-project-btn')?.addEventListener('click', () => {
      // Toggle the sibling <create-project> element in the light DOM
      const createProject = this.parentElement?.querySelector('create-project') as HTMLElement | null;
      if (createProject) {
        const isOpen = createProject.getAttribute('data-open') === 'true';
        createProject.setAttribute('data-open', isOpen ? 'false' : 'true');

        const btn = this.shadowRoot?.querySelector('#new-project-btn');
        if (btn) btn.textContent = isOpen ? '+ New Project' : '− Cancel';
      }
    });
  }

  async fetchData() {
    try {
      const response = await fetch('/api/dashboard/projects');
      if (!response.ok) throw new Error('API error');
      const text = await response.text();
      if (!text) throw new Error('Empty response');
      const data = JSON.parse(text);
      if (data.tree) {
        this.updateTree(data.tree);
      } else {
        this.showEmpty();
      }
    } catch (e) {
      this.showEmpty();
    }
  }

  showEmpty() {
    const pre = this.shadowRoot?.querySelector('pre');
    if (pre) {
      pre.textContent = 'No projects yet. Create one to get started.';
      pre.style.color = 'rgba(255, 255, 255, 0.3)';
      pre.style.fontFamily = "'Inter', system-ui, sans-serif";
      pre.style.textAlign = 'center';
      pre.style.padding = '2rem';
    }
  }

  updateTree(treeData: string) {
    const pre = this.shadowRoot?.querySelector('pre');
    if (pre) {
      pre.innerHTML = treeData;
    }
  }

  render() {
    if (this.shadowRoot) {
      this.shadowRoot.innerHTML = `
        <style>
          h2 { font-size: 1.5rem; font-weight: bold; margin: 0 0 1rem 0; color: #fff; letter-spacing: 0.02em; }
          :host { display: block; }
          .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
          }
          
          #new-project-btn {
            background: rgba(20, 184, 166, 0.12);
            color: #14B8A6;
            border: 1px solid rgba(20, 184, 166, 0.2);
            padding: 0.4rem 1rem;
            border-radius: 0.6rem;
            font-size: 0.8rem;
            font-weight: 600;
            font-family: 'Inter', system-ui, sans-serif;
            cursor: pointer;
            transition: all 0.25s ease;
            letter-spacing: 0.02em;
          }
          #new-project-btn:hover {
            background: rgba(20, 184, 166, 0.22);
            border-color: rgba(20, 184, 166, 0.4);
          }
          pre {
            background: rgba(0, 0, 0, 0.3);
            padding: 1.5rem;
            border-radius: 1rem;
            font-family: 'Fira Code', monospace;
            font-size: 0.95rem;
            line-height: 1.6;
            color: #14B8A6;
            border: 1px solid rgba(255, 255, 255, 0.05);
            overflow-x: auto;
            margin: 0;
          }
          pre a {
            transition: color 0.2s ease, text-shadow 0.2s ease;
          }
          pre a:hover {
            color: #0066FF !important;
            text-shadow: 0 0 8px rgba(0, 102, 255, 0.4);
          }
        </style>
        <div class="card">
          <div class="header">
            <h2>Projects</h2>
            <button id="new-project-btn">+ New Project</button>
          </div>
          <pre>Loading tree...</pre>
        </div>
      `;
    }
  }
}

customElements.define('project-tree', ProjectTree);

