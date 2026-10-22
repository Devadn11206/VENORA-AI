"""Desktop automation package for VENORA AI."""

from app.desktop.capability import DesktopCapabilityService
from app.desktop.permissions import DesktopPermissionService
from app.desktop.application_launcher import ApplicationLauncherService
from app.desktop.process_inspector import ProcessInspectorService
from app.desktop.screenshot import ScreenshotService
from app.desktop.mouse_keyboard import MouseKeyboardService
from app.desktop.ui_automation import UIAutomationService
from app.desktop.service import DesktopService
from app.desktop.verification import DesktopOutcomeVerifier
from app.desktop.schemas import (
    DesktopActionType,
    ActionStatus,
    VerificationStatus,
    DesktopCapabilityResponse,
    ApplicationInfo,
    ApplicationListResponse,
    LaunchApplicationRequest,
    LaunchApplicationResponse,
    ProcessInfo,
    ProcessListResponse,
    ScreenshotCaptureRequest,
    ScreenshotInfo,
    MouseMoveRequest,
    MouseClickRequest,
    KeyboardTypeRequest,
    KeyboardKeyRequest,
    DesktopActionRequest,
    DesktopActionResult,
    EmergencyStopResponse,
)

__all__ = [
    "DesktopCapabilityService",
    "DesktopPermissionService",
    "ApplicationLauncherService",
    "ProcessInspectorService",
    "ScreenshotService",
    "MouseKeyboardService",
    "UIAutomationService",
    "DesktopService",
    "DesktopOutcomeVerifier",
    "DesktopActionType",
    "ActionStatus",
    "VerificationStatus",
    "DesktopCapabilityResponse",
    "ApplicationInfo",
    "ApplicationListResponse",
    "LaunchApplicationRequest",
    "LaunchApplicationResponse",
    "ProcessInfo",
    "ProcessListResponse",
    "ScreenshotCaptureRequest",
    "ScreenshotInfo",
    "MouseMoveRequest",
    "MouseClickRequest",
    "KeyboardTypeRequest",
    "KeyboardKeyRequest",
    "DesktopActionRequest",
    "DesktopActionResult",
    "EmergencyStopResponse",
]
