# Building and Running OpenZero

This guide provides step-by-step instructions to build and deploy your Personal AI Operating System.

## Prerequisites

- **Docker & Docker Compose**: Essential for running the containerized services.
  - [Download Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
- **Tailscale**: For secure, private access without exposing ports to the internet.
  - [Install Tailscale](https://tailscale.com/download)
- **Telegram Bot Token**: Create a bot via [@BotFather](https://t.me/botfather) to get your token.

## Project Structure

- `src/`: Core source code (e.g., FastAPI backend).
- `docs/`: Implementation guides and character specifications.
- `scripts/`: Entrypoint scripts and utility tools.
- `personal/`: (Gitignored) Your private configuration and data.
- `docker-compose.yml`: Service orchestration.

## Step 1: Initializing the Project Structure

If you are starting from a fresh clone, ensure the following directory structure is created:

```bash
mkdir -p src/backend/app/api src/backend/app/services src/backend/app/models src/backend/app/tasks scripts docs
```

## Step 2: Configuration

1. **Backend Environment Variables**:
   Copy the example environment file and fill in your secrets (Telegram token, DB passwords):
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your preferred settings.

2. **Planka Environment Variables**:
   Copy the example environment file for Planka and ensure the `DATABASE_URL` matches your credentials:
   ```bash
   cp .env.planka.example .env.planka
   ```
   Edit `.env.planka` and set a secure `SECRET_KEY` and `DEFAULT_ADMIN_PASSWORD`.

## Step 3: Building the Services

Run the following command to build the Docker images:

```bash
docker compose build
```

## Step 4: Starting the System (Production)

Once built, start all services in the background:

```bash
docker compose up -d
```

## Local Development Mode (Recommended for Building)

If you are modifying the code or want a faster feedback loop, use the dedicated **Dev Mode** script. This starts the heavy infrastructure (Databases, AI) in Docker but runs the app logic directly on your machine.

```bash
./scripts/dev.sh
```

**What this does:**
1. **Infrastructure**: Automatically starts Postgres, Qdrant, Ollama, and Planka in Docker.
2. **Environment**: Sets up your local Python `.venv` and installs Node dependencies if needed.
3. **Hot Reload**: Starts the FastAPI backend and Vite dashboard with live-reloading enabled.
4. **Clean Exit**: Stopping the script (Ctrl+C) automatically shuts down the background Docker containers.

## Step 5: Post-Deployment Setup

1. **Verify Services**: Check the health of your services:
   ```bash
   docker compose ps
   ```
2. **Access Planka**: Connect to Tailscale and open `http://localhost:1337` (or your Tailscale IP).
3. **Verify AI**: Send `/start` to your Telegram bot.
4. **Access Dashboard**: Open `http://localhost:8000` (or your Tailscale IP on port 8000) to view your OpenZero Dashboard.

## Troubleshooting

- **Ollama Model Pulling**: On first start, the `ollama` container will pull the `llama3.1:8b` model. This may take a few minutes depending on your internet speed.
- **Logs**: If something isn't working, check the logs:
   ```bash
   docker compose logs -f backend
   ```
