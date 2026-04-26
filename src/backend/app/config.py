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

    # Cloud routing: when True and cloud is configured, use cloud as the primary model for
    # all interactive requests; fall back to local only if cloud is unavailable.
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
    # Minimum cosine similarity score for injecting a retrieved memory into the chat
    # context.  Results below this threshold are silently discarded so topically
    # unrelated memories do not bleed into unrelated conversations.
    MEMORY_MIN_SCORE: float = 0.72

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
    # PII sanitization for outbound cloud LLM calls (Groq, OpenAI).
    # Disabled by default — the spaCy NER model produces false-positives on
    # non-personal payloads (scientific names, project IDs, etc.).
    # Set to true only when sending genuinely personal data to cloud providers.
    CLOUD_LLM_SANITIZE: bool = False
    # Cloud tool-calling: enable the model to autonomously call tools
    # (web search, etc.) via standard function-calling on /v1/chat/completions.
    # Disabled by default until verified with the configured provider.
    CLOUD_LLM_TOOLS: bool = True
    
    
    # Scheduling
    TASK_BOARD_SYNC_INTERVAL_MINUTES: int = 5

    # Briefing
    BRIEFING_CALIBRATION: bool = True

    # Self-audit
    # Name of the Planka project that serves as the container for user-initiated projects.
    # When set, the audit checks that newly created projects became boards under this parent
    # rather than top-level Planka projects.
    AUDIT_MY_PROJECTS_PARENT: str = "My Projects"
    # How many hours between full self-audit runs (action fulfillment + hallucination + redundancy).
    AUDIT_INTERVAL_HOURS: int = 6
    # Seconds to wait after a Z reply containing [AUDIT:...] tags before firing the reactive one-shot audit.
    # Gives Planka and other downstream systems time to process the action before the verifier checks them.
    AUDIT_REACTIVE_DELAY_SECONDS: int = 15
    # How many hours back to scan Z's stored messages when running any audit (periodic or on-demand).
    # 48 covers two full days of activity and matches the typical "look back at the last two days" user intent.
    AUDIT_LOOKBACK_HOURS: int = 48

    # ── Ambient Capture & Contextual Routing ─────────────────────────────────
    # See docs/artifacts/ambient_capture_routing.md for the full architectural
    # plan. Epoch 1 ships dark; the engine code is in place but no message
    # path invokes it until AMBIENT_CAPTURE_ENABLED is True (Epoch 2).
    #
    # Single-user / single-tenant operator identity (Section 18). REQUIRED
    # before ambient capture can be enabled — engine refuses to start without
    # it rather than defaulting open. Set to your Planka user id (string).
    OPERATOR_USER_ID: str = ""
    # Master kill-switch for the ambient capture engine. Default False.
    # When False, intent_bus is a verbatim pass-through to the existing
    # deterministic intent router and ambient routing never fires.
    AMBIENT_CAPTURE_ENABLED: bool = False
    # Per-channel opt-in (Epoch 2). All False until the operator flips them.
    AMBIENT_CAPTURE_TELEGRAM: bool = False
    AMBIENT_CAPTURE_WHATSAPP: bool = False
    AMBIENT_CAPTURE_DASHBOARD: bool = False
    # Pending capture TTL (seconds). Configurable in AgentsWidget once the
    # Inference panel ships. Range enforced in code: 10s..600s.
    AMBIENT_PENDING_TTL_SECONDS: int = 90
    # Confidence thresholds. Defaults align with the "Confident butler" preset
    # from Section 7. Range enforced in code: 0.0..1.0.
    AMBIENT_SILENT_FLOOR: float = 0.80
    AMBIENT_ASK_FLOOR: float = 0.45
    AMBIENT_CHAT_FLOOR: float = 0.20
    # Comma-separated extra domains the auto-description sanitiser allows
    # in addition to wikipedia.org / youtube.com (Section 11 + M4).
    AMBIENT_AUTO_DESC_ALLOWED_DOMAINS: str = ""
    # Routing-lesson retention. 0 = never expire (default per Section 7).
    AMBIENT_ROUTING_LESSON_RETENTION_DAYS: int = 0

    # ── Ambient Intelligence (State-Diff Engine) ──────────────────────────────
    # See docs/artifacts/ambient_intelligence.md for the full architectural plan.
    # Separate from AMBIENT_CAPTURE_* (which routes inbound user messages).
    # This engine reacts to observed state changes and fires crews proactively.
    #
    # Master switch. Default False — ships dark. Enable when P0 is validated.
    AMBIENT_ENABLED: bool = False
    # Snapshot interval in seconds (default 5 minutes).
    AMBIENT_POLL_INTERVAL_S: int = 300
    # Minutes of silence before a quiet-moment delivery is allowed.
    AMBIENT_QUIET_MOMENT_WINDOW_M: int = 15
    # Maximum ambient triggers per hour across all rules (global rate cap).
    AMBIENT_MAX_TRIGGERS_PER_HOUR: int = 3
    # Fold undelivered priority 4-5 insights into the morning briefing.
    AMBIENT_BRIEFING_QUEUE_ENABLED: bool = True


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
