# Building & Deploying openZero

This guide is designed for anyone—even if you've never used a server before. Follow these steps exactly to get your Personal AI Operating System (Z) running on your own VPS.

---

## 🏗️ Phase 1: Prepare your VPS (Server)

We recommend a VPS with **Ubuntu 24.04**. For best performance with Llama 8B, aim for at least **8 Cores** and **16GB RAM**.

> [!IMPORTANT]
> **Z uses a 3-tier LLM architecture** (phi-4-mini instant + llama3.1:8b standard + qwen2.5:14b deep). With 24GB RAM this runs comfortably. With 16GB, disable the deep tier. **Swap space is still recommended as a safety buffer.**

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
    http://open.zero/home?token=your_generated_token_here
    ```

    Subsequent visits via the bookmark work without the token in the URL.

> [!IMPORTANT]
> If the backend returns HTTP 500 on every dashboard request, the `DASHBOARD_TOKEN` env var is missing or empty. Set it and restart the backend container: `docker compose up -d --no-deps backend`.

### 6. Trigger the Sync (ON YOUR LAPTOP)

Run the sync script from the project root on your laptop:

```bash
bash scripts/sync.sh
```

Z will now package itself, fly to your server, build its brain (llama-server), and start up.

> [!NOTE]
> **AI Models are downloaded automatically** on first start. The entrypoint script downloads GGUF models from HuggingFace for all 3 tiers. This can take **10-30 minutes** on first boot. Monitor with:
>
> ```bash
> docker compose logs -f llm-standard
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
python3 scripts/test_live_vps_protocols.py --url http://YOUR_SERVER_IP --token your_dashboard_token
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

Now you can reach your dashboard at `http://open.zero/home`.

---

## 🧪 Phase 8: Running Tests

openZero includes two independent test suites.

### Prompt Injection Risk Tests (Offline)

Validates the prompt construction pipeline against 208 adversarial attack vectors. No running services required -- this tests the structural integrity of how user input is assembled into LLM prompts.

```bash
# Install pytest (once)
pip install pytest

# Run all 208 tests
python -m pytest tests/test_prompt_injection.py -v --tb=short

# Run a specific category
python -m pytest tests/test_prompt_injection.py -v -k "MemoryPoisoning"
python -m pytest tests/test_prompt_injection.py -v -k "TelegramSpecific"
python -m pytest tests/test_prompt_injection.py -v -k "SecurityInvariants"
```

All tests should pass with 0 failures. See [`docs/artifacts/prompt_injection_tests.md`](docs/artifacts/prompt_injection_tests.md) for full category breakdown and findings.

### Live Protocol Regression Suite (Requires Running Stack)

Tests the end-to-end capabilities of the live environment including LLM responses, memory persistence, and action tag execution.

```bash
python3 scripts/test_live_vps_protocols.py --url http://YOUR_SERVER_IP --token your_token_here
```

This suite runs automatically at the end of every `scripts/sync.sh` deployment.

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
