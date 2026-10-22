"""Tools module export and default registry factory."""

from typing import Optional
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.desktop.service import DesktopService
from app.ai.tools.base import BaseTool
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.desktop_tools import (
    CaptureScreenshotTool,
    DesktopCapabilitiesTool,
    InspectProcessesTool,
    LaunchApplicationTool,
    ListApplicationsTool,
)


def create_default_tool_registry(
    desktop_service: Optional[DesktopService] = None,
    settings: Optional[Settings] = None,
    db: Optional[Session] = None,
) -> ToolRegistry:
    """Instantiate and populate the standard VENORA AI tool registry with approved desktop capabilities."""
    cfg = settings or get_settings()
    svc = desktop_service or DesktopService(db=db, settings=cfg)
    registry = ToolRegistry(permission_service=svc.permissions)

    # Register approved Phase 2 desktop tools
    registry.register(ListApplicationsTool(svc))
    registry.register(LaunchApplicationTool(svc))
    registry.register(InspectProcessesTool(svc))
    registry.register(CaptureScreenshotTool(svc))
    registry.register(DesktopCapabilitiesTool(svc))

    return registry
