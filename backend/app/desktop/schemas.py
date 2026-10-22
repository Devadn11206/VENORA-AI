"""Pydantic schemas for desktop automation, capability detection, and action results."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DesktopActionType(str, Enum):
    """Categorized desktop automation action types."""
    LAUNCH_APPLICATION = "launch_application"
    CAPTURE_SCREENSHOT = "capture_screenshot"
    INSPECT_PROCESS = "inspect_process"
    LIST_PROCESSES = "list_processes"
    MOVE_MOUSE = "move_mouse"
    CLICK_MOUSE = "click_mouse"
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    EMERGENCY_STOP = "emergency_stop"
    RESET_EMERGENCY_STOP = "reset_emergency_stop"


class ActionStatus(str, Enum):
    """Execution status of an action."""
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class VerificationStatus(str, Enum):
    """Empirical verification assessment of the action outcome."""
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    FAILED = "failed"


# Capability Schemas
class DesktopCapabilityResponse(BaseModel):
    """Detailed report on the host OS and available automation capabilities."""
    os_name: str
    is_windows: bool
    is_interactive_desktop: bool
    screenshot_available: bool
    ui_automation_available: bool
    mouse_keyboard_available: bool
    input_automation_enabled: bool
    emergency_stop_active: bool
    unavailable_reasons: Dict[str, str] = Field(default_factory=dict)
    supported_applications: List[str] = Field(default_factory=list)


# Application Schemas
class ApplicationInfo(BaseModel):
    """Details of a configured, whitelisted application."""
    app_id: str
    executable: str
    is_available: bool
    description: Optional[str] = None


class ApplicationListResponse(BaseModel):
    """List of permitted desktop applications."""
    applications: List[ApplicationInfo]
    total: int


class LaunchApplicationRequest(BaseModel):
    """Request payload to launch an approved application."""
    arguments: Optional[List[str]] = Field(default=None, description="Optional safe arguments")
    task_id: Optional[int] = Field(default=None, description="Associated task ID")


class LaunchApplicationResponse(BaseModel):
    """Result of launching an approved application."""
    app_id: str
    pid: Optional[int]
    status: ActionStatus
    verification_status: VerificationStatus
    message: str
    started_at: datetime


# Process Inspection Schemas
class ProcessInfo(BaseModel):
    """Safe, sanitized metadata for a running process."""
    pid: int
    name: str
    status: str
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    created_at: Optional[datetime] = None


class ProcessListResponse(BaseModel):
    """Paginated or bounded list of running processes."""
    processes: List[ProcessInfo]
    total: int


# Screenshot Schemas
class ScreenshotCaptureRequest(BaseModel):
    """Request to capture a task-scoped desktop screenshot."""
    task_id: Optional[int] = Field(default=None, description="Associated task ID")
    label: Optional[str] = Field(default=None, max_length=100, description="Optional descriptive label")


class ScreenshotInfo(BaseModel):
    """Metadata regarding a captured screenshot without exposing binary contents."""
    screenshot_id: str
    filename: str
    captured_at: datetime
    file_size_bytes: int
    width: int
    height: int
    task_id: Optional[int] = None
    verification_status: VerificationStatus


# Mouse and Keyboard Action Requests
class MouseMoveRequest(BaseModel):
    """Payload to move mouse pointer."""
    x: int = Field(..., ge=0, le=7680, description="X coordinate on screen")
    y: int = Field(..., ge=0, le=4320, description="Y coordinate on screen")
    duration: float = Field(default=0.2, ge=0.0, le=5.0, description="Movement transition seconds")


class MouseClickRequest(BaseModel):
    """Payload to click mouse at coordinates."""
    x: Optional[int] = Field(default=None, ge=0, le=7680, description="Optional target X coordinate")
    y: Optional[int] = Field(default=None, ge=0, le=4320, description="Optional target Y coordinate")
    button: str = Field(default="left", pattern="^(left|right|middle)$", description="Mouse button")
    clicks: int = Field(default=1, ge=1, le=3, description="Number of clicks")


class KeyboardTypeRequest(BaseModel):
    """Payload to type safe text."""
    text: str = Field(..., min_length=1, max_length=250, description="Plain text to type")
    interval: float = Field(default=0.02, ge=0.0, le=0.5, description="Typing cadence per character")


class KeyboardKeyRequest(BaseModel):
    """Payload to press an approved key."""
    key: str = Field(..., min_length=1, max_length=20, description="Permitted key name (e.g. enter, tab, esc)")


class DesktopActionRequest(BaseModel):
    """Generic polymorphic action request wrapper."""
    action_type: DesktopActionType
    parameters: Dict[str, Any] = Field(default_factory=dict)
    task_id: Optional[int] = None


class DesktopActionResult(BaseModel):
    """Standardized structured result returned for all desktop operations."""
    action_id: str
    action_type: DesktopActionType
    status: ActionStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    verification_status: VerificationStatus
    result_summary: str
    data: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    safe_error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EmergencyStopResponse(BaseModel):
    """Response returned when emergency stop state changes."""
    emergency_stop_active: bool
    message: str
    timestamp: datetime
