"""Health and readiness diagnostic endpoints for VENORA AI."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.database.session import get_db

router = APIRouter(prefix="/health", tags=["Health"])
logger = get_logger("api.health")


@router.get(
    "",
    summary="Application Health Probe",
    description="Returns high-level application status and metadata without exposing internal credentials."
)
def get_health(settings: Settings = Depends(get_settings)):
    """Liveness probe indicating that the HTTP server is running."""
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@router.get(
    "/ready",
    summary="Application Readiness Probe",
    description="Verifies database accessibility to ensure the backend is fully operational."
)
def get_readiness(db: Session = Depends(get_db)):
    """Readiness probe verifying database connectivity."""
    try:
        # Execute minimal connectivity test
        db.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected"
        }
    except Exception as exc:
        logger.error(f"Readiness check failed: {exc}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "disconnected",
                "message": "Database connection unavailable"
            }
        )
