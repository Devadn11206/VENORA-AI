"""Desktop automation API routes for capability inspection, application launching, screenshots, and actions."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.desktop.schemas import (
    ApplicationListResponse,
    DesktopActionRequest,
    DesktopActionResult,
    DesktopCapabilityResponse,
    EmergencyStopResponse,
    LaunchApplicationRequest,
    LaunchApplicationResponse,
    ProcessInfo,
    ProcessListResponse,
    ScreenshotCaptureRequest,
    ScreenshotInfo,
)
from app.desktop.service import DesktopService

router = APIRouter(prefix="/desktop", tags=["Desktop Automation"])


def get_desktop_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DesktopService:
    """Dependency provider for DesktopService."""
    return DesktopService(db=db, settings=settings)


@router.get(
    "/capabilities",
    response_model=DesktopCapabilityResponse,
    summary="Get Desktop Capabilities",
    description="Detect and report host operating system, window station availability, and automation libraries."
)
def get_capabilities(
    service: DesktopService = Depends(get_desktop_service),
):
    return service.get_capabilities()


@router.get(
    "/applications",
    response_model=ApplicationListResponse,
    summary="List Approved Applications",
    description="List configured, whitelisted applications and verify their executable presence on disk."
)
def list_applications(
    service: DesktopService = Depends(get_desktop_service),
):
    apps = service.list_applications()
    return ApplicationListResponse(applications=apps, total=len(apps))


@router.post(
    "/applications/{app_id}/launch",
    response_model=LaunchApplicationResponse,
    status_code=status.HTTP_200_OK,
    summary="Launch Approved Application",
    description="Safely start a whitelisted desktop application by its configured application identifier."
)
def launch_application(
    app_id: str,
    request: Optional[LaunchApplicationRequest] = None,
    service: DesktopService = Depends(get_desktop_service),
):
    return service.launch_application(app_id=app_id, request=request)


@router.get(
    "/processes",
    response_model=ProcessListResponse,
    summary="List Running Processes",
    description="Inspect running system processes with sanitized, read-only metadata without exposing sensitive command lines."
)
def list_processes(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of processes to return"),
    service: DesktopService = Depends(get_desktop_service),
):
    procs = service.list_processes(limit=limit)
    return ProcessListResponse(processes=procs, total=len(procs))


@router.get(
    "/processes/{pid}",
    response_model=ProcessInfo,
    summary="Inspect Process by PID",
    description="Read process status, CPU, memory, and creation time for a specific PID."
)
def get_process(
    pid: int,
    service: DesktopService = Depends(get_desktop_service),
):
    return service.get_process(pid=pid)


@router.post(
    "/screenshots",
    response_model=ScreenshotInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Capture Desktop Screenshot",
    description="Capture an on-demand task-scoped screenshot and verify its integrity on disk."
)
def capture_screenshot(
    request: Optional[ScreenshotCaptureRequest] = None,
    service: DesktopService = Depends(get_desktop_service),
):
    return service.capture_screenshot(request=request)


@router.get(
    "/screenshots/{screenshot_id}",
    summary="Retrieve Captured Screenshot Image",
    description="Stream a verified, previously captured screenshot file by its unique identifier with strict path validation."
)
def get_screenshot(
    screenshot_id: str,
    service: DesktopService = Depends(get_desktop_service),
):
    file_path = service.get_screenshot_path(screenshot_id=screenshot_id)
    return FileResponse(
        path=str(file_path),
        media_type="image/png",
        filename=file_path.name,
    )


@router.post(
    "/actions",
    response_model=DesktopActionResult,
    summary="Execute Desktop Action",
    description="Dispatch an authorized, controlled desktop action (mouse movement, click, typing, key press) with empirical verification."
)
def execute_action(
    request: DesktopActionRequest,
    service: DesktopService = Depends(get_desktop_service),
):
    return service.execute_action(request=request)


@router.post(
    "/emergency-stop",
    response_model=EmergencyStopResponse,
    summary="Toggle Emergency Stop",
    description="Activate or disengage the central emergency stop mechanism to instantly halt interactive automation."
)
def toggle_emergency_stop(
    active: bool = Query(default=True, description="Set emergency stop state (true to engage, false to reset)"),
    service: DesktopService = Depends(get_desktop_service),
):
    return service.set_emergency_stop(active=active)
