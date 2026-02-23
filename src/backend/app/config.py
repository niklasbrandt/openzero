"""
System Configuration Module
---------------------------
This module centralizes all environment-based settings for the OpenZero OS.
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

    # Timezone
    USER_TIMEZONE: str = "America/New_York"

    # Ollama
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"

    # Whisper
    WHISPER_BASE_URL: str = "http://whisper:9000"

    # TTS
    TTS_BASE_URL: str = "http://tts:8000"

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str = ""

    # Planka
    PLANKA_BASE_URL: str = "http://planka:1337"
    PLANKA_ADMIN_EMAIL: str = ""
    PLANKA_ADMIN_PASSWORD: str = ""

    # LLM Providers
    LLM_PROVIDER: str = "ollama"
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    DEEP_THINK_PROVIDER: Optional[str] = None
    DEEP_THINK_MODEL: Optional[str] = None
    
    # Scheduling
    TASK_BOARD_SYNC_INTERVAL_MINUTES: int = 5


    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "../../../.env"), 
        extra="ignore"
    )

    def __init__(self, **values):
        super().__init__(**values)
        
        # --- Smart Host Normalization ---
        # Map: Localhost <-> Docker Service Name
        host_map = {
            "DB_HOST": "postgres",
            "QDRANT_HOST": "qdrant",
            "OLLAMA_BASE_URL": "http://ollama:11434",
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
