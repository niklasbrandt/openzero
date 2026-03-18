# Building & Deploying openZero

This guide is designed for anyone—even if you've never used a server before. Follow these steps exactly to get your Personal AI Operating System (Z) running on your own VPS.

---

## 🏗️ Phase 1: Prepare your VPS (Server)

We recommend a VPS with **Ubuntu 24.04**. For best performance with Llama 8B, aim for at least **8 Cores** and **16GB RAM**.

> [!IMPORTANT]
> **Z uses a 2-tier LLM architecture** (Qwen3-0.6B fast + Qwen3-8B deep). A **12 GB VPS** is the minimum (use `Qwen3-8B-Q2_K.gguf` for the deep tier, ~3 GB total). A **24 GB VPS** comfortably runs the default Q4_K_M deep model (~5 GB total) with headroom for Whisper and TTS. **Swap space is still recommended as a safety buffer.**

### 0. Add Swap Space (MANDATORY first step)

```bash
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Verify with: `free -h` — you should see 8G of swap.

### 1. Log in for the first time

Open the "Terminal" (Mac/Linux) or "PowerShell" (Windows) on your computer and type:

```bash
ssh root@YOUR_SERVER_IP
```

_(Replace `YOUR_SERVER_IP` with the IP address from your hosting provider.)_

### 2. Create your dedicated user

We don't want to run everything as "root" (the superuser) for security reasons.

```bash
adduser openzero
```

- Pick a password and remember it!
- Press `Enter` through all the other questions.

Now, give this user "Sudo" (Superpower) rights:

```bash
usermod -aG sudo openzero
```

### 3. Harden SSH (Recommended)

```bash
# Disable root login and password auth
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd
```

> [!WARNING]
> Make sure you have SSH key access for your `openzero` user BEFORE disabling password auth, or you will lock yourself out.

### 4. Install Fail2Ban

```bash
sudo apt-get install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 5. Enable UFW Firewall

openZero uses Tailscale as its network perimeter. Port 80 must only be reachable through the Tailscale interface — not the public internet.

```bash
# Allow SSH first to prevent lockout
sudo ufw allow ssh

# Allow port 80 ONLY through the Tailscale interface
sudo ufw allow in on tailscale0 to any port 80

# Block port 80 on all other (public) interfaces
sudo ufw deny 80

# Allow DNS (port 53) from Tailscale peers so mobile devices can resolve open.zero via Pi-hole.
# Source is restricted to the Tailscale CGNAT range (100.64.0.0/10) — not the whole interface.
sudo ufw allow in on tailscale0 from 100.64.0.0/10 to any port 53 proto udp
sudo ufw allow in on tailscale0 from 100.64.0.0/10 to any port 53 proto tcp

# Allow DNS (port 53) from Docker bridge networks (172.16.0.0/12) so backend container can resolve open.zero
sudo ufw allow in from 172.16.0.0/12 to any port 53 proto udp
sudo ufw allow in from 172.16.0.0/12 to any port 53 proto tcp

# Activate the firewall
sudo ufw --force enable

# Verify
sudo ufw status verbose
```

Expected output shows `80 on tailscale0 ALLOW IN`, `80 DENY IN`, and `53/udp on tailscale0 ALLOW IN`. Without the port 53 rules, mobile devices on Tailscale cannot resolve `open.zero` and the dashboard will be unreachable from mobile even when Tailscale is connected.

> [!IMPORTANT]
> Run `sudo ufw allow ssh` **before** enabling the firewall or you will lock yourself out.

---

## 🐳 Phase 2: Install Docker (The Engine)

OpenZero runs inside "Containers" (mini virtual computers). Docker is the engine that runs them.

### 1. Run the official installer

Paste this entire block into your terminal:

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

### 2. Grant Docker permissions

This allows you to run Docker without typing `sudo` every time:

```bash
sudo usermod -aG docker openzero
```

### 3. The Crucial Hand-off

**Log out of the server now:**

```bash
exit
```

**Now, log back in—but as your new `openzero` user:**

```bash
ssh openzero@YOUR_SERVER_IP
```

---

## 📡 Phase 3: The First Interaction

Now that you are logged in as `openzero`, your server is ready. But it's empty! We need to move the code from your computer to the server.

### 1. Create the project folder (ON THE SERVER)

Run this command on your server to create a home for Z:

```bash
mkdir -p ~/openzero
```

### 2. Setup SSH Keys (Optional but HIGHLY Recommended)

To avoid typing your password 10 times during deployment, run this **ON YOUR LAPTOP** terminal:

> [!TIP]
> **Getting "no identities found"?** This means you don't have an SSH key yet. Run this first: `ssh-keygen -t ed25519` (Press Enter through all prompts) and then try the command below again.

```bash
ssh-copy-id openzero@YOUR_SERVER_IP
```

### 3. Configure your local .env (ON YOUR LAPTOP)

Open a **new** terminal window on your laptop (leave the server window open if you want).
Make sure you have your `.env` file ready with your Telegram Bot Token and other secrets.

```bash
cp .env.example .env
# Edit .env and fill in these critical lines:
# TELEGRAM_BOT_TOKEN=your_token_here
# REMOTE_HOST=YOUR_SERVER_IP
# REMOTE_USER=openzero
# REDIS_PASSWORD=your_strong_random_password  (protects the task queue)
# BASE_URL=http://open.zero  (or http://YOUR_SERVER_IP — must match your access URL)

# LLM Memory Management (RAM savings)
# LLM_FAST_CACHE_RAM=256   (MiB for prompt cache - 0.6B tier)
# LLM_DEEP_CACHE_RAM=1024  (MiB for prompt cache - 8B tier)
```

> [!NOTE]
> `REDIS_PASSWORD` is required. Generate one with `openssl rand -hex 24`. `BASE_URL` is used to scope CORS — requests from any other origin will be rejected.

### 4. Setup Planka (ON THE SERVER)

Planka is your task board. It needs its own configuration file to talk to the database.

1. **Copy the template:**

    ```bash
    cd ~/openzero
    cp .env.planka.example .env.planka
    ```

2. **Edit the file:**

    ```bash
    nano .env.planka
    ```

3. **Critical Changes to make:**
    - **BASE_URL**: Change `http://your-ip-address` to `http://YOUR_SERVER_IP`.
    - **DATABASE_URL**: Update the password part (`CHANGE_ME_STRONG_PASSWORD`) to match the `DB_PASSWORD` you set in your **main `.env`**.
    - **SECRET_KEY**: Replace with a long random string (e.g., mash your keyboard).
    - **Admin Password**: Change `CHANGE_ME_PLANKA_PASS` to something you'll remember to log in.

_Press `Ctrl+O`, `Enter`, then `Ctrl+X` to save and exit nano._

### 5. Set a Dashboard Access Token (Security)

The dashboard is protected by a bearer token. You must set one before the backend will serve any API requests.

1. Generate a strong token on your laptop:

    ```bash
    python3 -c "import secrets; print(secrets.token_urlsafe(32))"
    ```

2. Add it to your **local** `.env`:

    ```env
    DASHBOARD_TOKEN=your_generated_token_here
    ```

3. Add the same value to the **server** `.env` (only needed if you edit the file manually rather than via a full sync):

    ```bash
    echo 'DASHBOARD_TOKEN=your_generated_token_here' >> ~/openzero/.env
    ```

4. The first time you open the dashboard in a browser, you will be prompted for the token. Enter it once — it is saved in `localStorage` and never re-asked on the same device/browser.

    **Mobile shortcut:** Append the token directly to the URL once, open it in mobile Safari/Chrome, and bookmark it. The token is automatically saved and stripped from the URL:

    ```
    http://open.zero/dashboard?token=your_generated_token_here
    ```

    Subsequent visits via the bookmark work without the token in the URL.

> [!IMPORTANT]
> If the backend returns HTTP 500 on every dashboard request, the `DASHBOARD_TOKEN` env var is missing or empty. Set it and restart the backend container: `docker compose up -d --no-deps backend`.

### 5c. Cloud LLM PII Sanitization (Optional)

When routing requests to cloud providers (Groq, OpenAI), openZero can automatically strip named entities (people, emails, phone numbers, locations, organisations) from outbound prompts using a fully offline spaCy NER model. Responses are re-hydrated with the real values before being returned.

- **No manual setup required.** The `en_core_web_sm` spaCy model (~12 MB) is downloaded and baked into the Docker image at build time. It adds approximately 30 seconds to the first `docker build`.
- **Enabled by default** for all cloud provider calls when `LLM_PROVIDER=groq` or `LLM_PROVIDER=openai`.
- To **disable globally**, add the following to your `.env`:

    ```env
    CLOUD_LLM_SANITIZE=false
    ```

- Callers can also opt out per-call by passing `sanitize=False` to `chat()` or `chat_with_context()` directly in code (e.g. for code-generation payloads where no PII is present).

### 5d. Set Up Personal Context Folder

The `personal/` folder is the highest-authority context source for Z. Files here are injected into every system prompt and refreshed every hour.

1. Create your personal files from the examples:

    ```bash
    cp -r personal.example personal
    ```

2. Edit the files in `personal/` with your real personal details.

3. The folder is bind-mounted read-only into the backend container. It is excluded from all git commits and VPS syncs — it never leaves your local machine.

4. On the VPS, you must create the folder manually before starting the stack (it will not be synced):

    ```bash
    mkdir -p ~/openzero/personal
    ```

    Then copy your personal files to the server over your Tailscale connection if you want Z to have access to them there.

### 5e. Set Up Agent Skills Folder

The `agent/` folder lets you drop in skill modules — methodology files, tool guides, and hard-coded behavioural rules — that are injected into every system prompt as operational expertise.

1. Create your agent skills folder from the example template:

    ```bash
    cp -r agent.example agent
    ```

2. Edit the files in `agent/` as needed:
    - `kanban.md` — Kanban/Scrum methodology knowledge (pre-filled, edit or leave as-is).
    - `planka.md` — Planka board operational directives (pre-filled, edit or leave as-is).
    - `agent-rules.md` — Hard-coded behavioural rules (empty template, fill in your own rules).
    - You can add any additional `.md`, `.txt`, `.docx`, or `.pdf` skill files.

3. The folder is bind-mounted read-only into the backend container and excluded from all git commits and VPS syncs.

4. On the VPS, create the folder manually before starting the stack:

    ```bash
    mkdir -p ~/openzero/agent
    ```

    Then copy your skill files to the server over your Tailscale connection.

### 5b. Restrict Dashboard to Tailscale Only (Optional, Recommended)

By default, Traefik binds port 80 on all interfaces (`0.0.0.0`). If you are using Tailscale, you can restrict it to your server's Tailscale IP so the dashboard is unreachable from the public internet.

1. Find your server's Tailscale IP (run on the VPS):

    ```bash
    tailscale ip -4
    ```

2. Add it to your **local** `.env`:

    ```env
    TAILSCALE_IP=100.x.x.x
    ```

    Leave `TAILSCALE_IP` unset (or empty) on servers without Tailscale — the default `0.0.0.0` binding is used automatically.

### 6. Trigger the Sync (ON YOUR LAPTOP)

Run the sync script from the project root on your laptop:

```bash
bash scripts/sync.sh
```

Z will now package itself, fly to your server, build its brain (llama-server), and start up.

> [!NOTE]
> **AI Models are downloaded automatically** on first start. The entrypoint script downloads GGUF models from HuggingFace for both tiers. This can take **5-15 minutes** on first boot. Monitor with:
>
> ```bash
> docker compose logs -f llm-deep
> ```

> [!NOTE]
> **First Login & Planka**: On the very first start, Planka usually requires a "Terms of Service" acceptance. Z handles this automatically for the admin account. You can access your task board at `http://YOUR_SERVER_IP/login`.

---

## 🛠️ Step 4: Maintenance & Logs

If Z isn't replying or you want to see what he's thinking:

1. **Check if everything is running:**

    ```bash
    cd ~/openzero
    docker compose ps
    ```

2. **Watch the live logs (The "Matrix" view):**

    ```bash
    docker compose logs -f backend
    ```

3. **Check Pi-hole (Privacy DNS):**
   Once Tailscale is connected, browse to `http://YOUR_SERVER_IP/admin` to manage your local DNS.

### Running Regression Tests Manually

To verify the health and AI capabilities of your live openZero deployment at any time, run the integrated regression suite from your laptop:

```bash
python3 tests/test_live_regression.py --url http://YOUR_SERVER_IP --token your_dashboard_token
```

This live validation suite tests:

1. **System Health API:** Verifies OS RAM/CPU metrics and subsystem statuses.
2. **Memory Persistence:** Validates that semantic vault storage and retrieval work through the LLM.
3. **Action Protocols:** Injects full Semantic Action Tags (for projects, lists, tasks, events, and people) to ensure the backend executes them correctly.
4. **Deep Routing:** Checks that complex demands successfully route to the deep inference tier.
5. **Clean up:** Automatically deletes any test data it creates in the database and Planka.

---

## 🌐 Optional: Using a Vanity Domain (open.zero)

If you set `BASE_URL=http://open.zero` in your `.env`, you must tell your local machine how to resolve that name.

On **macOS/Linux** (Laptop/Desktop):

1. Open terminal and run: `sudo nano /etc/hosts`
2. Add the following line at the end:
    ```text
    YOUR_SERVER_IP  open.zero
    ```
3. Save (Ctrl+O, Enter) and Exit (Ctrl+X).

On **Mobile Phones (iOS/Android)**:
Since you cannot safely edit `/etc/hosts` on a mobile phone, and normal Wi-Fi DNS is bypassed by VPNs/Cellular data, the most reliable way to route `open.zero` to your server is via **Tailscale Split DNS**:

1. Go to the Tailscale Admin Console in your browser: [https://login.tailscale.com/admin/dns](https://login.tailscale.com/admin/dns)
2. Scroll down to **Nameservers** and click **Add nameserver** -> **Custom...**
3. Enter your server's Tailscale IP address (e.g. `100.X.Y.Z`).
4. Check the box **"Restrict to domain"** and enter `open.zero`.
5. Click **Save**.
6. On your mobile phone, open the Tailscale app, make sure you are connected, and then restart the app.

Tailscale will now magically route _only_ queries for `open.zero` to your OpenZero server, allowing your phone to connect!

Now you can reach your dashboard at `http://open.zero/dashboard`.

---

## 🎨 Phase 9: Customizing the Interface (UI & Theming)

The openZero dashboard features a high-performance mission-control interface. You can customize its appearance and behaviors directly from the **User Card** in the top-right corner.

### 1. Theme Presets

- Over **50 HSLA-based presets** (Fusion, Cyberpunk, Nordic, Dracula, etc.) are available.
- Switching themes updates the `--accent-primary`, `--accent-secondary`, and `--accent-tertiary` color tokens globally.

### 2. Auto/Light Mode support

- Special themes (Paper, Snow, Latte) activate **Light Mode**.
- Most presets are optimized for **Dark Mode** to preserve battery and reduce eye strain in mission-control environments.

### 3. Motion & Performance

- **Cursor Parallax:** The background glow and accent highlights track your mouse movements using a hardware-accelerated `lerp` engine.
- **Goo Mode (Phase 4):** Organic fluid interactions are driven by an SVG filter (`#oz-goo`) and CSS classes (`.oz-goo-container`).
### 4. Agent Personality

- You can now configure Z's **Communication Style**, **Emotional Tone**, and **Agency Level** directly from the User Card.
- These settings are updated in real-time and saved to the backend as part of your identity profile.
- A single "Save Profile" action now persists both your personal details and your agent's character traits.

---

## 🧪 Phase 10: Running Tests

openZero includes two independent test suites.

### Security Tests (Offline)

Two offline suites covering 307 tests total. No running services required.

**Prompt injection suite** (`tests/test_security_prompt_injection.py`): 295 tests across 27 categories validating the prompt construction pipeline against adversarial attack vectors.

**Static analysis gate** (`tests/test_static_analysis.py`): 12 AST-based tests enforcing backend security invariants (no exception cause leakage via HTTPException, no interpolation of exception objects into HTTP responses, etc.).

```bash
# Install pytest + coverage (once)
pip install pytest pytest-cov

# Run both suites (307 tests total)
python -m pytest tests/test_security_prompt_injection.py tests/test_static_analysis.py -v --tb=short

# Run with coverage report
python -m pytest tests/test_security_prompt_injection.py tests/test_static_analysis.py -v --tb=short --cov=tests

# Run a specific category
python -m pytest tests/test_security_prompt_injection.py -v -k "MemoryPoisoning"
python -m pytest tests/test_security_prompt_injection.py -v -k "TelegramSpecific"
python -m pytest tests/test_security_prompt_injection.py -v -k "ActionTagExceptionLeakage"
```

All tests should pass with 0 failures. See `tests/test_security_prompt_injection.py` for full category breakdown.

### Live Protocol Regression Suite (Requires Running Stack)

Tests the end-to-end capabilities of the live environment including LLM responses, memory persistence, and action tag execution.

```bash
python3 tests/test_live_regression.py --url http://YOUR_SERVER_IP --token your_token_here
```

This suite runs automatically at the end of every `scripts/sync.sh` deployment.

---

## 🔬 Phase 11: CI / Quality Gates

The GitHub Actions pipeline runs 11 jobs on every push to `main`.

| Job             | Tool                                           | Blocks deploy? |
| --------------- | ---------------------------------------------- | :------------: |
| `frontend`      | tsc --noEmit + npm audit                       |      yes       |
| `backend`       | py_compile + translation key check             |      yes       |
| `accessibility` | axe-core + Playwright WCAG 2.1 AA              |      yes       |
| `security`      | pytest prompt-injection (268 tests) + coverage |      yes       |
| `lint`          | ruff                                           |      yes       |
| `sast`          | bandit                                         |      yes       |
| `eslint`        | ESLint 9 + typescript-eslint                   |      yes       |
| `mypy`          | mypy Python type-check                         |      yes       |
| `dep-audit`     | pip-audit (torch/pymupdf exempted)             |       no       |
| `lighthouse`    | @lhci/cli perf + a11y budget                   |   warn only    |
| `build`         | Docker build + Trivy CRITICAL/HIGH scan        |      yes       |

To run the frontend linter locally:

```bash
cd src/dashboard
npm ci
npx eslint src/ components/ services/
```

To run mypy locally:

```bash
pip install mypy types-redis
mypy src/backend/app/ --ignore-missing-imports --python-version=3.11
```

---

## ❓ FAQ & Troubleshooting for Beginners

- **What is a "Port"?** It's like a door to a house. OpenZero uses only port `80` (HTTP via Traefik). All other ports are internal only.
- **Port 53 "Address already in use"?** Ubuntu's default DNS resolver hogs port 53, preventing Pi-hole from starting. Connect to your server via SSH and run this to fix it:
    ```bash
    sudo sed -r -i.orig 's/#?DNSStubListener=yes/DNSStubListener=no/g' /etc/systemd/resolved.conf
    sudo sh -c 'rm /etc/resolv.conf && ln -s /run/systemd/resolve/resolv.conf /etc/resolv.conf'
    sudo systemctl restart systemd-resolved
    ```
- **What if I get "Permission Denied"?** Always make sure you are logged in as the `openzero` user, not `root`.
- **How do I stop everything?** Go to the folder and type `docker compose down`.

---

_OpenZero is a living system. Every time you run `sync.sh`, it updates its logic without losing your memories._
