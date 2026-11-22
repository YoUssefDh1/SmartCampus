"""Configuration centrale : toutes les valeurs viennent de l'environnement (.env)."""
from functools import lru_cache

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
    db_pool_max_size: int = 10
    db_pool_timeout_seconds: float = 5.0
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30

    # Mode démo de l'authentification (tant que /auth/login n'existe pas, SA-28).
    # Actif UNIQUEMENT si ENVIRONMENT=development : l'en-tête X-Dev-Role simule un utilisateur.
    auth_dev_mode: bool = False

    @property
    def dev_auth_enabled(self) -> bool:
        return self.auth_dev_mode and self.environment == "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
