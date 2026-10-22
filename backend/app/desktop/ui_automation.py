"""Windows UI Automation abstraction layer for window discovery and control inspection."""

import ctypes
import logging
import platform
from typing import Any, Dict, List, Optional
from app.core.config import Settings, get_settings
from app.core.errors import DesktopCapabilityUnavailableError
from app.desktop.permissions import DesktopPermissionService

logger = logging.getLogger("venora.desktop.ui_automation")


class UIAutomationService:
    """Provides non-intrusive Windows UI element discovery and inspection."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        permission_service: Optional[DesktopPermissionService] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.permissions = permission_service or DesktopPermissionService(self.settings)

    def list_visible_windows(self) -> List[Dict[str, Any]]:
        """Enumerate top-level visible application windows safely using user32EnumWindows."""
        self.permissions.check_permission("desktop.ui.inspect")

        if platform.system() != "Windows":
            raise DesktopCapabilityUnavailableError(
                capability="ui_automation",
                reason="UI automation window inspection is only supported on Windows."
            )

        windows: List[Dict[str, Any]] = []

        try:
            user32 = ctypes.windll.user32

            # Define WNDENUMPROC callback
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def enum_windows_callback(hwnd, extra):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buffer, length + 1)
                        title = buffer.value.strip()

                        # Exclude empty or common background shell windows
                        if title and title not in {"Program Manager", "Default IME"}:
                            pid = ctypes.c_ulong()
                            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                            windows.append({
                                "hwnd": int(hwnd),
                                "title": title,
                                "pid": int(pid.value),
                            })
                return True

            cb = WNDENUMPROC(enum_windows_callback)
            user32.EnumWindows(cb, 0)
            logger.info(f"Enumerated {len(windows)} visible top-level windows.")
            return windows
        except Exception as exc:
            logger.error(f"Failed to enumerate windows: {exc}")
            raise DesktopCapabilityUnavailableError(
                capability="ui_automation",
                reason=f"Failed to enumerate Windows controls: {exc}"
            )
