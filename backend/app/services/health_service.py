"""Exemple de service métier : la logique est ici, pas dans la route."""
from app.core.config import get_settings
from app.schemas.common import HealthResponse


def get_health() -> HealthResponse:
    s = get_settings()
    return HealthResponse(status="ok", app=s.app_name, version=s.app_version, environment=s.environment)
