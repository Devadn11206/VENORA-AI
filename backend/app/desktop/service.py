"""Unified desktop automation orchestrator service integrating all desktop capabilities."""

import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    DesktopActionExecutionError,
    DesktopEmergencyStopActiveError,
    DesktopPermissionDeniedError,
    VenoraError,
)
from app.database.base import utc_now
from app.desktop.application_launcher import ApplicationLauncherService
from app.desktop.capability import DesktopCapabilityService
from app.desktop.mouse_keyboard import MouseKeyboardService
from app.desktop.permissions import DesktopPermissionService
from app.desktop.process_inspector import ProcessInspectorService
from app.desktop.schemas import (
    ActionStatus,
    ApplicationInfo,
    DesktopActionRequest,
    DesktopActionResult,
    DesktopActionType,
    DesktopCapabilityResponse,
    EmergencyStopResponse,
    KeyboardKeyRequest,
    KeyboardTypeRequest,
    LaunchApplicationRequest,
    LaunchApplicationResponse,
    MouseClickRequest,
    MouseMoveRequest,
    ProcessInfo,
    ScreenshotCaptureRequest,
    ScreenshotInfo,
    VerificationStatus,
)
from app.desktop.screenshot import ScreenshotService
from app.desktop.ui_automation import UIAutomationService
from app.models.execution_log import ExecutionLog, LogLevel

logger = logging.getLogger("venora.desktop.service")


class DesktopService:
    """Orchestrates desktop capability detection, applications, inspection, screenshots, and input actions."""

    def __init__(
        self,
        db: Optional[Session] = None,
        settings: Optional[Settings] = None,
        permission_service: Optional[DesktopPermissionService] = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.permissions = permission_service or DesktopPermissionService(self.settings)

        # Initialize sub-services sharing permissions
        self.capabilities = DesktopCapabilityService(self.settings)
        self.launcher = ApplicationLauncherService(self.settings, self.permissions)
        self.inspector = ProcessInspectorService(self.settings, self.permissions)
        self.screenshots = ScreenshotService(self.settings, self.permissions)
        self.input_service = MouseKeyboardService(self.settings, self.permissions)
        self.ui_service = UIAutomationService(self.settings, self.permissions)

    def _record_audit_log(
        self,
        event_type: str,
        message: str,
        task_id: Optional[int] = None,
        level: LogLevel = LogLevel.INFO,
        metadata_json: Optional[str] = None,
    ) -> None:
        """Write desktop operation events to Phase 1 ExecutionLog table if DB session is available."""
        if self.db:
            try:
                log_entry = ExecutionLog(
                    task_id=task_id,
                    event_type=event_type,
                    level=level,
                    message=message,
                    created_at=utc_now(),
                    metadata_json=metadata_json,
                )
                self.db.add(log_entry)
                self.db.commit()
            except Exception as exc:
                logger.warning(f"Could not persist desktop execution audit log: {exc}")

    # =========================================================================
    # Capability & Emergency Stop
    # =========================================================================
    def get_capabilities(self) -> DesktopCapabilityResponse:
        """Report host capabilities and active emergency stop state."""
        self.permissions.check_permission("desktop.capabilities.read")
        return self.capabilities.detect_capabilities(
            emergency_stop_active=self.permissions.emergency_stop_active
        )

    def set_emergency_stop(self, active: bool) -> EmergencyStopResponse:
        """Engage or disengage emergency stop mechanism."""
        self.permissions.set_emergency_stop(active)
        msg = "Emergency stop engaged. Input automation actions blocked." if active else "Emergency stop disengaged."
        self._record_audit_log(
            event_type="desktop_emergency_stop",
            message=msg,
            level=LogLevel.WARNING if active else LogLevel.INFO,
        )
        return EmergencyStopResponse(
            emergency_stop_active=active,
            message=msg,
            timestamp=utc_now(),
        )

    # =========================================================================
    # Application & Process Inspection
    # =========================================================================
    def list_applications(self) -> List[ApplicationInfo]:
        """List whitelisted applications."""
        return self.launcher.list_applications()

    def launch_application(self, app_id: str, request: Optional[LaunchApplicationRequest] = None) -> LaunchApplicationResponse:
        """Launch whitelisted application and record event."""
        task_id = request.task_id if request else None
        args = request.arguments if request else None
        result = self.launcher.launch_application(app_id=app_id, arguments=args, task_id=task_id)

        self._record_audit_log(
            event_type="application_launched",
            message=result.message,
            task_id=task_id,
            level=LogLevel.INFO,
        )
        return result

    def list_processes(self, limit: int = 50) -> List[ProcessInfo]:
        """Inspect running processes."""
        return self.inspector.list_processes(limit=limit)

    def get_process(self, pid: int) -> ProcessInfo:
        """Inspect specific process by PID."""
        return self.inspector.get_process_by_pid(pid=pid)

    # =========================================================================
    # Screenshots
    # =========================================================================
    def capture_screenshot(self, request: Optional[ScreenshotCaptureRequest] = None) -> ScreenshotInfo:
        """Capture task-scoped desktop screenshot."""
        task_id = request.task_id if request else None
        label = request.label if request else None
        info = self.screenshots.capture_screenshot(task_id=task_id, label=label)

        self._record_audit_log(
            event_type="screenshot_captured",
            message=f"Captured screenshot '{info.screenshot_id}' ({info.width}x{info.height})",
            task_id=task_id,
            level=LogLevel.INFO,
        )
        return info

    def get_screenshot_path(self, screenshot_id: str):
        """Locate verified screenshot path on disk."""
        return self.screenshots.get_screenshot_path(screenshot_id)

    # =========================================================================
    # Structured Unified Desktop Action Dispatcher
    # =========================================================================
    def execute_action(self, request: DesktopActionRequest) -> DesktopActionResult:
        """Execute a validated desktop action and return structured, verified result."""
        action_id = f"act_{secrets.token_hex(6)}"
        start_time = time.time()
        started_dt = utc_now()
        action_type = request.action_type
        params = request.parameters or {}
        task_id = request.task_id

        try:
            # 1. Emergency stop check
            if self.permissions.emergency_stop_active and action_type not in {
                DesktopActionType.EMERGENCY_STOP,
                DesktopActionType.RESET_EMERGENCY_STOP,
            }:
                raise DesktopEmergencyStopActiveError()

            result_data = None
            summary = ""
            verification = VerificationStatus.UNVERIFIED

            # Dispatch based on action type
            if action_type == DesktopActionType.LAUNCH_APPLICATION:
                app_id = params.get("app_id")
                if not app_id:
                    raise DesktopActionExecutionError(action_type=action_type.value, reason="Missing 'app_id' parameter.")
                launch_res = self.launch_application(app_id=app_id, request=LaunchApplicationRequest(task_id=task_id))
                result_data = launch_res.model_dump()
                summary = launch_res.message
                verification = launch_res.verification_status

            elif action_type == DesktopActionType.CAPTURE_SCREENSHOT:
                snap_res = self.capture_screenshot(request=ScreenshotCaptureRequest(task_id=task_id))
                result_data = snap_res.model_dump()
                summary = f"Screenshot {snap_res.screenshot_id} captured successfully."
                verification = snap_res.verification_status

            elif action_type == DesktopActionType.MOVE_MOUSE:
                move_req = MouseMoveRequest(**params)
                result_data = self.input_service.move_mouse(move_req)
                summary = f"Pointer moved to ({move_req.x}, {move_req.y})."
                verification = result_data["verification_status"]

            elif action_type == DesktopActionType.CLICK_MOUSE:
                click_req = MouseClickRequest(**params)
                result_data = self.input_service.click_mouse(click_req)
                summary = f"Mouse clicked button '{click_req.button}' ({click_req.clicks}x)."
                verification = result_data["verification_status"]

            elif action_type == DesktopActionType.TYPE_TEXT:
                type_req = KeyboardTypeRequest(**params)
                result_data = self.input_service.type_text(type_req)
                summary = f"Typed text of length {len(type_req.text)}."
                verification = result_data["verification_status"]

            elif action_type == DesktopActionType.PRESS_KEY:
                key_req = KeyboardKeyRequest(**params)
                result_data = self.input_service.press_key(key_req)
                summary = f"Pressed key '{key_req.key}'."
                verification = result_data["verification_status"]

            elif action_type == DesktopActionType.EMERGENCY_STOP:
                res = self.set_emergency_stop(True)
                result_data = res.model_dump()
                summary = res.message
                verification = VerificationStatus.VERIFIED

            elif action_type == DesktopActionType.RESET_EMERGENCY_STOP:
                res = self.set_emergency_stop(False)
                result_data = res.model_dump()
                summary = res.message
                verification = VerificationStatus.VERIFIED

            else:
                raise DesktopActionExecutionError(action_type=action_type.value, reason="Unsupported desktop action type.")

            completed_dt = utc_now()
            duration_ms = (time.time() - start_time) * 1000

            action_result = DesktopActionResult(
                action_id=action_id,
                action_type=action_type,
                status=ActionStatus.COMPLETED,
                started_at=started_dt,
                completed_at=completed_dt,
                duration_ms=round(duration_ms, 2),
                verification_status=verification,
                result_summary=summary,
                data=result_data,
            )

            self._record_audit_log(
                event_type="desktop_action_completed",
                message=f"Action '{action_type.value}' completed ({verification.value}): {summary}",
                task_id=task_id,
                level=LogLevel.INFO,
            )
            return action_result

        except (DesktopPermissionDeniedError, DesktopEmergencyStopActiveError) as perm_err:
            completed_dt = utc_now()
            duration_ms = (time.time() - start_time) * 1000
            self._record_audit_log(
                event_type="desktop_action_blocked",
                message=f"Action '{action_type.value}' blocked: {perm_err.message}",
                task_id=task_id,
                level=LogLevel.WARNING,
            )
            return DesktopActionResult(
                action_id=action_id,
                action_type=action_type,
                status=ActionStatus.BLOCKED,
                started_at=started_dt,
                completed_at=completed_dt,
                duration_ms=round(duration_ms, 2),
                verification_status=VerificationStatus.FAILED,
                result_summary=perm_err.message,
                error_code="PERMISSION_DENIED",
                safe_error_message=perm_err.message,
            )
        except Exception as exc:
            completed_dt = utc_now()
            duration_ms = (time.time() - start_time) * 1000
            if isinstance(exc, VenoraError):
                safe_msg = exc.message
            elif hasattr(exc, "errors"):
                # Pydantic validation error
                safe_msg = f"Invalid parameters for {action_type.value}: {exc}"
            else:
                safe_msg = str(exc) if exc else "Desktop action encountered execution failure."
            self._record_audit_log(
                event_type="desktop_action_failed",
                message=f"Action '{action_type.value}' failed: {safe_msg}",
                task_id=task_id,
                level=LogLevel.ERROR,
            )
            return DesktopActionResult(
                action_id=action_id,
                action_type=action_type,
                status=ActionStatus.FAILED,
                started_at=started_dt,
                completed_at=completed_dt,
                duration_ms=round(duration_ms, 2),
                verification_status=VerificationStatus.FAILED,
                result_summary=f"Failed to execute action: {safe_msg}",
                error_code="EXECUTION_FAILED",
                safe_error_message=safe_msg,
            )
