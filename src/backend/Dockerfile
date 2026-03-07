# Build Dashboard
FROM node:20-slim AS dashboard-build
WORKDIR /dashboard
COPY src/dashboard/package*.json ./
RUN npm install
COPY src/dashboard/ ./
RUN npm run build

# Final Backend Image
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    dnsutils \
    curl \
    ca-certificates \
    gnupg \
    lsb-release \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Pre-install CPU-only PyTorch before requirements
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY src/backend/requirements.txt .
# Upgrade setuptools AFTER requirements to prevent pip downgrading it.
# Patches CVE-2025-47273 (path traversal, HIGH); python:3.12-slim ships 70.2.0.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "setuptools>=78.1.1" \
    && python -m spacy download en_core_web_sm

# Copy release context if exists (from sync.sh)
COPY LATEST_CHANGES.txt* ./

COPY src/backend/app/ ./app/
COPY --from=dashboard-build /dashboard/dist/ ./static/

# Non-root user — GID 999 matches the standard docker socket group on Debian/Ubuntu
# so appuser retains docker.sock access without running as root.
RUN groupadd -f -g 999 docker \
    && useradd -m -u 1000 -G docker appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
