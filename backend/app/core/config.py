"""Configuration centrale : toutes les valeurs viennent de l'environnement (.env)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SmartCampus AI"
    app_version: str = "0.1.0"
    environment: str = "development"  # development | production
    api_prefix: str = "/api/v1"

    # Frontend autorisé à appeler l'API (CORS)
    cors_origins: list[str] = ["http://localhost:3000"]

    # Utilisés par les autres membres (à compléter dans .env)
    database_url: str = "postgresql+psycopg://smartcampus:smartcampus@localhost:5432/smartcampus"
    demo_data_dir: str | None = None  # dossier des données de démonstration (par défaut ../data/demo)
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30

    # Comptes utilisateurs (SA-28)
    refresh_token_days: int = Field(default=7, gt=0)
    password_min_length: int = Field(default=8, gt=0)

    # Sessions visiteur (SA-25)
    guest_session_ttl_hours: int = Field(default=24, gt=0)
    guest_max_messages: int = Field(default=20, gt=0)
    guest_rate_limit_per_minute: int = Field(default=5, gt=0)
    guest_purge_interval_minutes: int = Field(default=60, gt=0)

    # Mémoire temporaire des conversations (SA-26)
    memory_window_size: int = Field(default=10, gt=0)
    max_message_length: int = Field(default=2000, gt=0)

    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "gemma3:4b"
    llm_timeout_seconds: float = 60
    llm_max_tokens: int = 600
    llm_temperature: float = 0.2

    rag_enabled: bool = False
    rag_embedding_model: str = "nomic-embed-text"
    rag_documents_dir: str = "data/knowledge_base"
    rag_top_k: int = Field(default=4, gt=0, le=20)
    rag_min_similarity: float = Field(default=0.25, ge=-1, le=1)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
