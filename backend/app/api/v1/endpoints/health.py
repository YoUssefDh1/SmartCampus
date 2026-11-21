from fastapi import APIRouter

from app.schemas.common import HealthResponse
from app.services import health_service

router = APIRouter(prefix="/health", tags=["Système"])


@router.get("", response_model=HealthResponse, summary="Vérifier que le service répond")
def health() -> HealthResponse:
    return health_service.get_health()
