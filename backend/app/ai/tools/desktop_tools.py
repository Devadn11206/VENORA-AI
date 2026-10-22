"""Controlled AI tools wrapping Phase 2 DesktopService capabilities."""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.ai.schemas import ToolResult
from app.ai.tools.base import BaseTool
from app.desktop.schemas import VerificationStatus
from app.desktop.service import DesktopService
from app.core.errors import (
    DesktopApplicationLaunchError,
    DesktopPermissionDeniedError,
    VenoraError,
)


logger = logging.getLogger("venora.ai.tools.desktop")


# -----------------------------------------------------------------------------
# Arguments Schemas
# -----------------------------------------------------------------------------

class ListApplicationsArgs(BaseModel):
    """Arguments for listing approved applications."""
    filter: Optional[str] = Field(default=None, max_length=50, description="Optional text filter for application names or IDs")


class LaunchApplicationArgs(BaseModel):
    """Arguments for launching an approved application."""
    app_id: str = Field(..., min_length=1, max_length=50, description="Unique identifier of approved application (e.g. 'notepad', 'calculator', 'cmd')")


class InspectProcessesArgs(BaseModel):
    """Arguments for inspecting active processes."""
    limit: Optional[int] = Field(default=20, ge=1, le=100, description="Maximum number of running processes to return (default 20, max 100)")


class CaptureScreenshotArgs(BaseModel):
    """Arguments for capturing desktop screenshot."""
    label: Optional[str] = Field(default="ai_reasoning_capture", max_length=50, description="Optional label identifier for the captured screenshot")


class DesktopCapabilitiesArgs(BaseModel):
    """Arguments for querying desktop capabilities."""
    pass


# -----------------------------------------------------------------------------
# Concrete Desktop Tools
# -----------------------------------------------------------------------------

class ListApplicationsTool(BaseTool):
    """Tool to inspect which desktop applications are approved for launching."""
    name = "list_applications"
    description = "List all desktop applications registered and approved for launching in VENORA AI."
    args_schema = ListApplicationsArgs
    required_permission = "desktop.applications.list"
    is_read_only = True

    def __init__(self, desktop_service: DesktopService) -> None:
        self.desktop_service = desktop_service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            apps = self.desktop_service.list_applications()
            filter_text = (arguments.get("filter") or "").lower()
            if filter_text:
                apps = [a for a in apps if filter_text in a.app_id.lower() or (a.description and filter_text in a.description.lower())]

            results_data = [
                {"app_id": a.app_id, "executable": a.executable, "is_available": a.is_available, "description": a.description}
                for a in apps
            ]
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=results_data,
                verification_status=VerificationStatus.VERIFIED,
            )

        except Exception as exc:
            logger.error(f"Error in {self.name}: {exc}", exc_info=True)
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="EXECUTION_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class LaunchApplicationTool(BaseTool):
    """Tool to launch a specific registered application from the allowlist."""
    name = "launch_application"
    description = "Launch an authorized application by app_id. Arbitrary executable paths or commands are strictly forbidden."
    args_schema = LaunchApplicationArgs
    required_permission = "desktop.applications.launch"
    is_read_only = False
    requires_approval = False

    def __init__(self, desktop_service: DesktopService) -> None:
        self.desktop_service = desktop_service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        app_id = arguments.get("app_id", "").strip().lower()
        if not app_id:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="INVALID_ARGUMENTS",
                safe_error_message="Parameter 'app_id' is required.",
                verification_status=VerificationStatus.FAILED,
            )

        try:
            launch_res = self.desktop_service.launch_application(app_id=app_id)
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={
                    "app_id": launch_res.app_id,
                    "pid": launch_res.pid,
                    "status": launch_res.status.value,
                    "message": launch_res.message,
                    "verified": launch_res.verified,
                },
                verification_status=VerificationStatus.VERIFIED if launch_res.verified else VerificationStatus.UNVERIFIED,
            )
        except DesktopPermissionDeniedError as perm_err:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="APP_NOT_ALLOWED",
                safe_error_message=f"Application '{app_id}' is not in the approved application allowlist or permission denied.",
                verification_status=VerificationStatus.FAILED,
            )
        except DesktopApplicationLaunchError as launch_err:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="LAUNCH_FAILED",
                safe_error_message=str(launch_err),
                verification_status=VerificationStatus.FAILED,
            )
        except Exception as exc:
            logger.error(f"Error launching application '{app_id}': {exc}", exc_info=True)
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="LAUNCH_FAILED",
                safe_error_message=f"Failed to launch application: {exc}",
                verification_status=VerificationStatus.FAILED,
            )



class InspectProcessesTool(BaseTool):
    """Tool to inspect active running processes securely."""
    name = "inspect_processes"
    description = "Inspect currently running processes on the host system with controlled summary fields (pid, name, cpu_percent, memory_mb)."
    args_schema = InspectProcessesArgs
    required_permission = "desktop.processes.read"
    is_read_only = True

    def __init__(self, desktop_service: DesktopService) -> None:
        self.desktop_service = desktop_service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        limit = arguments.get("limit", 20)
        try:
            limit = int(limit)
            if limit < 1:
                limit = 1
            if limit > 50:
                limit = 50
        except (ValueError, TypeError):
            limit = 20

        try:
            procs = self.desktop_service.list_processes(limit=limit)
            proc_list = [
                {
                    "pid": p.pid,
                    "name": p.name,
                    "status": p.status,
                    "cpu_percent": p.cpu_percent,
                    "memory_mb": p.memory_mb,
                }
                for p in procs
            ]
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={"count": len(proc_list), "processes": proc_list},
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            logger.error(f"Error inspecting processes: {exc}", exc_info=True)
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="INSPECTION_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class CaptureScreenshotTool(BaseTool):
    """Tool to capture task-scoped desktop screenshot metadata."""
    name = "capture_screenshot"
    description = "Capture a desktop screenshot. Returns file path and image metadata (width, height, file_size_bytes). Raw pixels are not returned to the language model."
    args_schema = CaptureScreenshotArgs
    required_permission = "desktop.screenshot.capture"
    is_read_only = False

    def __init__(self, desktop_service: DesktopService) -> None:
        self.desktop_service = desktop_service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        label = arguments.get("label", "ai_reasoning_capture")
        try:
            from app.desktop.schemas import ScreenshotCaptureRequest
            info = self.desktop_service.capture_screenshot(ScreenshotCaptureRequest(label=label))
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={
                    "screenshot_id": info.screenshot_id,
                    "width": info.width,
                    "height": info.height,
                    "file_size_bytes": info.file_size_bytes,
                    "file_path": info.file_path,
                },
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            logger.error(f"Error capturing screenshot: {exc}", exc_info=True)
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="SCREENSHOT_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class DesktopCapabilitiesTool(BaseTool):
    """Tool to report current desktop automation subsystem capabilities."""
    name = "desktop_capabilities"
    description = "Report supported desktop capabilities, display geometry, and whether emergency stop is active."
    args_schema = DesktopCapabilitiesArgs
    required_permission = "desktop.capabilities.read"
    is_read_only = True

    def __init__(self, desktop_service: DesktopService) -> None:
        self.desktop_service = desktop_service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            caps = self.desktop_service.get_capabilities()
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={
                    "os_name": caps.os_name,
                    "is_windows": caps.is_windows,
                    "screenshot_available": caps.screenshot_available,
                    "ui_automation_available": caps.ui_automation_available,
                    "mouse_keyboard_available": caps.mouse_keyboard_available,
                    "input_automation_enabled": caps.input_automation_enabled,
                    "emergency_stop_active": caps.emergency_stop_active,
                    "supported_applications": caps.supported_applications,
                },
                verification_status=VerificationStatus.VERIFIED,
            )

        except Exception as exc:
            logger.error(f"Error retrieving desktop capabilities: {exc}", exc_info=True)
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="CAPABILITIES_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )
