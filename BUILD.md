# 🚀 Building & Deploying OpenZero

This guide is designed for anyone—even if you've never used a server before. Follow these steps exactly to get your Personal AI Operating System (Z) running on your own VPS.

---

## 🏗️ Phase 1: Prepare your VPS (Server)

We recommend a VPS with **Ubuntu 24.04**. For best performance with Llama 8B, aim for at least **8 Cores** and **16GB-24GB RAM**.

### 1. Log in for the first time
Open the "Terminal" (Mac/Linux) or "PowerShell" (Windows) on your computer and type:
```bash
ssh root@YOUR_SERVER_IP
```
*(Replace `YOUR_SERVER_IP` with the IP address from your hosting provider.)*

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
```

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

*Press `Ctrl+O`, `Enter`, then `Ctrl+X` to save and exit nano.*

### 5. Trigger the Sync (ON YOUR LAPTOP)
Run the sync script from the project root on your laptop:
```bash
bash scripts/sync.sh
```
Z will now package itself, fly to your server, build its brain (Ollama), and start up.

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

---

## ❓ FAQ for Beginners

- **What is a "Port"?** It's like a door to a house. OpenZero uses port `80` (Web) and `11434` (AI).
- **What if I get "Permission Denied"?** Always make sure you are logged in as the `openzero` user, not `root`.
- **How do I stop everything?** Go to the folder and type `docker compose down`.

---
*OpenZero is a living system. Every time you run `sync.sh`, it updates its logic without losing your memories.*
