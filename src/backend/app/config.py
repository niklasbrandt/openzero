"""
System Configuration Module
---------------------------
This module centralizes all environment-based settings for the openZero OS.
It uses Pydantic Settings for:
1. Typed validation of environment variables.
2. Smart defaulting for local development.
3. Automatic host normalization (Localhost vs. Docker Service Names).

Usage:
To override any setting, add it to the `.env` file in the project root.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Environment Detection
    IS_DOCKER: bool = os.path.exists('/.dockerenv') or os.environ.get('RUNNING_IN_DOCKER') == 'true'
    BASE_URL: str = "http://localhost" # Default for local dev
    SERVER_IP: str = "127.0.0.1"

    # Database
    DB_USER: str = "zero"
    DB_PASSWORD: str = ""
    DB_NAME: str = "zero_db"
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DATABASE_URL: Optional[str] = None

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ALLOWED_USER_ID: str = ""

    # Local LLM (llama-server / llama.cpp) — always-on CPU inference
    LLM_LOCAL_URL: str = "http://llm-local:8081"
    LLM_MODEL_LOCAL: str = "Qwen3-0.6B"

    # Peer discovery — comma-separated list of additional inference endpoints
    # (Tailscale-connected Macs, other local PCs, etc.).  Probed every 30 s;
    # the fastest responding peer is used automatically.  Supports both
    # llama.cpp (default port 8081) and Ollama (default port 11434).
    # Example: LLM_PEER_CANDIDATES=http://100.x.y.z:11434,http://100.a.b.c:8081
    LLM_PEER_CANDIDATES: str = ""

    # Cloud LLM — optional OpenAI-compatible inference provider (Groq, Together, OpenRouter, …)
    # Leave LLM_CLOUD_API_KEY empty to disable cloud tier; all cloud calls fall back to local.
    LLM_CLOUD_BASE_URL: str = ""
    LLM_CLOUD_API_KEY: str = ""
    LLM_MODEL_CLOUD: str = ""

    # Cloud routing: 2s first-token race — if local responds, use it; else escalate to cloud.
    # Set False to disable cloud for all interactive chat (air-gapped / cost-zero mode).
    SMART_CLOUD_ROUTING: bool = True

    # Timeout for cloud API responses (seconds). External APIs are fast; 30s is generous.
    CLOUD_MODEL_TIMEOUT_S: int = 30

    # Deep thinking provider (optional, for /think command)
    CLOUD_THINK_PROVIDER: Optional[str] = None
    CLOUD_THINK_MODEL: Optional[str] = None

    # Whisper
    WHISPER_BASE_URL: str = "http://whisper:9000"

    # TTS
    TTS_BASE_URL: str = "http://tts:8000"

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")

    # Dashboard Authentication
    DASHBOARD_TOKEN: str = ""

    # Redis & Tasks
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""

    # Planka
    PLANKA_BASE_URL: str = "http://planka:1337"
    PLANKA_ADMIN_EMAIL: str = ""
    PLANKA_ADMIN_PASSWORD: str = ""

    # WhatsApp Cloud API (optional — leave empty to disable)
    # See BUILD.md "WhatsApp" section for setup instructions.
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    # Random secret you choose when registering the webhook in the Meta developer portal
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = ""
    # Owner's WhatsApp phone number in E.164 format without '+', e.g. 15551234567
    WHATSAPP_ALLOWED_PHONE: str = ""
    # Meta App Secret for X-Hub-Signature-256 verification (recommended, not mandatory)
    WHATSAPP_APP_SECRET: str = ""

    # CalDAV (Private Calendar)
    CALDAV_URL: Optional[str] = None
    CALDAV_USERNAME: Optional[str] = None
    CALDAV_PASSWORD: Optional[str] = None

    # LLM Providers
    LLM_PROVIDER: str = "local"
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    # PII sanitization for outbound cloud LLM calls (Groq, OpenAI)
    # Set to false to disable for all cloud providers globally.
    CLOUD_LLM_SANITIZE: bool = True
    
    
    # Scheduling
    TASK_BOARD_SYNC_INTERVAL_MINUTES: int = 5

    # Briefing
    BRIEFING_CALIBRATION: bool = True


    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "../../../.env"),
        extra="ignore"
    )

    @property
    def cloud_configured(self) -> bool:
        """True when a cloud inference provider is fully configured."""
        return bool(self.LLM_CLOUD_API_KEY and self.LLM_CLOUD_BASE_URL and self.LLM_MODEL_CLOUD)

    def __init__(self, **values):
        super().__init__(**values)

        # --- Smart Host Normalization ---
        # Map: Localhost <-> Docker Service Name
        host_map = {
            "DB_HOST": "postgres",
            "QDRANT_HOST": "qdrant",
            "LLM_LOCAL_URL": "http://llm-local:8081",
            "WHISPER_BASE_URL": "http://whisper:9000",
            "TTS_BASE_URL": "http://tts:8000",
            "PLANKA_BASE_URL": "http://planka:1337"
        }

        for attr, docker_val in host_map.items():
            current_val = getattr(self, attr)
            is_url = "://" in docker_val
            
            local_val = "localhost"
            if is_url:
                local_val = docker_val.replace(docker_val.split("://")[1].split(":")[0], "localhost")

            if self.IS_DOCKER:
                # If in Docker but config says localhost, switch to service name
                if current_val == local_val:
                    setattr(self, attr, docker_val)
            else:
                # If not in Docker but config says service name, switch to localhost
                if current_val == docker_val:
                    setattr(self, attr, local_val)

        # Finalize Database URL
        if not self.DATABASE_URL:
            self.DATABASE_URL = f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

settings = Settings()
