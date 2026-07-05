"""
Application configuration using pydantic-settings.

All settings are loaded from environment variables and validated at startup.
Never hardcode secrets — always use environment variables or a secrets manager.
"""

from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    app_env: Environment = Environment.DEVELOPMENT
    app_name: str = "FitnessOS"
    app_version: str = "1.0.0"
    debug: bool = False
    secret_key: str = Field(min_length=32)
    allowed_origins: str = "http://localhost:3000,http://localhost:3001"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    # ---- Database ----
    database_url: str
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_echo: bool = False

    # ---- Supabase ----
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_storage_bucket: str = "fitnessos-media"

    # ---- Clerk Authentication ----
    clerk_secret_key: str
    clerk_publishable_key: str
    clerk_jwt_issuer: str

    # ---- LLM Providers ----
    default_llm_provider: LLMProvider = LLMProvider.OPENAI
    default_embedding_provider: LLMProvider = LLMProvider.OPENAI

    # OpenAI
    openai_api_key: str = ""
    openai_default_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_default_model: str = "claude-3-5-sonnet-20241022"

    # Google
    google_api_key: str = ""
    google_default_model: str = "gemini-1.5-pro"

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "llama3.1"

    # ---- Redis / Celery ----
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ---- Memory & Embeddings ----
    embedding_dimensions: int = 1536
    memory_retrieval_top_k: int = 10
    memory_similarity_threshold: float = 0.75

    # ---- Rate Limiting ----
    rate_limit_requests_per_minute: int = 60
    rate_limit_chat_per_minute: int = 20

    # ---- Logging ----
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env == Environment.DEVELOPMENT

    def get_llm_config(self, provider: LLMProvider | None = None) -> dict:
        """Return the configuration for the requested LLM provider."""
        target = provider or self.default_llm_provider
        configs = {
            LLMProvider.OPENAI: {
                "api_key": self.openai_api_key,
                "model": self.openai_default_model,
            },
            LLMProvider.ANTHROPIC: {
                "api_key": self.anthropic_api_key,
                "model": self.anthropic_default_model,
            },
            LLMProvider.GOOGLE: {
                "api_key": self.google_api_key,
                "model": self.google_default_model,
            },
            LLMProvider.OPENROUTER: {
                "api_key": self.openrouter_api_key,
                "base_url": self.openrouter_base_url,
                "model": self.openai_default_model,
            },
            LLMProvider.OLLAMA: {
                "base_url": self.ollama_base_url,
                "model": self.ollama_default_model,
            },
        }
        return configs[target]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings. Use dependency injection in FastAPI routes."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
