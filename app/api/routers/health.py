from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()
api_router = APIRouter()


def health_payload() -> dict:
    return {
        "status": "ok",
        "service": get_settings().app_name,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health")
def root_health():
    return health_payload()


@api_router.get("/health")
def api_health():
    return health_payload()
