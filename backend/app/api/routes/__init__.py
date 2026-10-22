"""API routes package."""

from app.api.routes.health import router as health_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.desktop import router as desktop_router

__all__ = ["health_router", "tasks_router", "desktop_router"]
