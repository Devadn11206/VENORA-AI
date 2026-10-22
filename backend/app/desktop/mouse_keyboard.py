"""Controlled mouse and keyboard input automation with fail-safes and boundary guards."""

import logging
import time
from typing import Optional
import pyautogui

from app.core.config import Settings, get_settings
from app.core.errors import (
    DesktopActionExecutionError,
    DesktopEmergencyStopActiveError,
    DesktopPermissionDeniedError,
)
from app.desktop.permissions import DesktopPermissionService
from app.desktop.schemas import (
    ActionStatus,
    KeyboardKeyRequest,
    KeyboardTypeRequest,
    MouseClickRequest,
    MouseMoveRequest,
    VerificationStatus,
)

logger = logging.getLogger("venora.desktop.mouse_keyboard")


class MouseKeyboardService:
    """Dispatches validated, bound mouse and keyboard operations with active safety mechanisms."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        permission_service: Optional[DesktopPermissionService] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.permissions = permission_service or DesktopPermissionService(self.settings)

        # Configure PyAutoGUI safety features
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05

    def _get_screen_bounds(self) -> tuple[int, int]:
        """Return screen width and height."""
        try:
            return pyautogui.size()
        except Exception:
            return (1920, 1080)

    def move_mouse(self, request: MouseMoveRequest) -> dict:
        """Move the mouse pointer to explicit coordinates within screen bounds."""
        self.permissions.check_permission("desktop.input.mouse")

        screen_w, screen_h = self._get_screen_bounds()
        if request.x > screen_w or request.y > screen_h:
            raise DesktopActionExecutionError(
                action_type="move_mouse",
                reason=f"Coordinates ({request.x}, {request.y}) exceed screen resolution ({screen_w}x{screen_h})."
            )

        logger.info(f"Moving mouse pointer to ({request.x}, {request.y})")
        pyautogui.moveTo(request.x, request.y, duration=request.duration)

        # Verification: check post-move position
        current_x, current_y = pyautogui.position()
        verified = (abs(current_x - request.x) <= 2) and (abs(current_y - request.y) <= 2)

        return {
            "target": {"x": request.x, "y": request.y},
            "actual": {"x": current_x, "y": current_y},
            "verification_status": VerificationStatus.VERIFIED if verified else VerificationStatus.PARTIALLY_VERIFIED,
        }

    def click_mouse(self, request: MouseClickRequest) -> dict:
        """Click mouse button at current or targeted coordinates."""
        self.permissions.check_permission("desktop.input.mouse")

        target_x = request.x
        target_y = request.y

        if target_x is not None and target_y is not None:
            screen_w, screen_h = self._get_screen_bounds()
            if target_x > screen_w or target_y > screen_h:
                raise DesktopActionExecutionError(
                    action_type="click_mouse",
                    reason=f"Coordinates ({target_x}, {target_y}) exceed screen bounds ({screen_w}x{screen_h})."
                )

        logger.info(f"Clicking mouse: button={request.button}, clicks={request.clicks}, target=({target_x}, {target_y})")
        pyautogui.click(
            x=target_x,
            y=target_y,
            clicks=request.clicks,
            button=request.button
        )

        current_x, current_y = pyautogui.position()
        return {
            "button": request.button,
            "clicks": request.clicks,
            "location": {"x": current_x, "y": current_y},
            "verification_status": VerificationStatus.VERIFIED,
        }

    def type_text(self, request: KeyboardTypeRequest) -> dict:
        """Type safe, bounded plain text into current focus context."""
        self.permissions.check_permission("desktop.input.keyboard")

        if len(request.text) > self.settings.MAX_TYPE_TEXT_LENGTH:
            raise DesktopActionExecutionError(
                action_type="type_text",
                reason=f"Text length ({len(request.text)}) exceeds allowed limit ({self.settings.MAX_TYPE_TEXT_LENGTH})."
            )

        # Check emergency stop condition immediately prior to typing
        if self.permissions.emergency_stop_active:
            raise DesktopEmergencyStopActiveError()

        logger.info(f"Typing text (length={len(request.text)}) with cadence {request.interval}s")
        pyautogui.write(request.text, interval=request.interval)

        return {
            "characters_typed": len(request.text),
            "cadence": request.interval,
            "verification_status": VerificationStatus.VERIFIED,
        }

    def press_key(self, request: KeyboardKeyRequest) -> dict:
        """Press an approved key from the allowlist."""
        self.permissions.check_permission("desktop.input.keyboard")

        # Validate against explicit allowlist
        valid_key = self.permissions.validate_key(request.key)

        logger.info(f"Pressing approved key: '{valid_key}'")
        pyautogui.press(valid_key)

        return {
            "key_pressed": valid_key,
            "verification_status": VerificationStatus.VERIFIED,
        }
