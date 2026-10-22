"""Environment and capability detection service for Windows desktop automation."""

import os
import platform
import sys
from typing import Dict, List, Optional
from app.core.config import Settings, get_settings
from app.desktop.schemas import DesktopCapabilityResponse


class DesktopCapabilityService:
    """Detects and reports actual OS and automation library capabilities without false claims."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def detect_capabilities(self, emergency_stop_active: bool = False) -> DesktopCapabilityResponse:
        """Probe the system environment and installed modules for available capabilities."""
        os_name = platform.system()
        is_windows = os_name == "Windows"
        unavailable: Dict[str, str] = {}

        # 1. Interactive desktop detection
        is_interactive = False
        if is_windows:
            try:
                # On Windows, interactive sessions have a visible window station (e.g. WinSta0)
                # We can check user32 or console session presence
                import ctypes
                user32 = ctypes.windll.user32
                # GetProcessWindowStation
                h_winsta = user32.GetProcessWindowStation()
                if h_winsta != 0:
                    is_interactive = True
            except Exception as exc:
                unavailable["interactive_desktop"] = f"Could not verify window station: {exc}"
        else:
            unavailable["os"] = f"Target OS is {os_name}; Windows is required for desktop automation."

        # 2. Screenshot availability probe (Pillow ImageGrab)
        screenshot_available = False
        try:
            from PIL import ImageGrab
            screenshot_available = True
        except ImportError:
            unavailable["screenshot"] = "Pillow library is not installed."
        except Exception as exc:
            unavailable["screenshot"] = f"Screenshot module error: {exc}"

        # 3. UI Automation probe (pywinauto or ctypes UI automation)
        ui_automation_available = False
        try:
            import pywinauto
            ui_automation_available = True
        except ImportError:
            # Fallback check for Windows native UI Automation COM/ctypes
            if is_windows:
                try:
                    import ctypes
                    # OleInitialize check
                    ctypes.windll.ole32.OleInitialize(None)
                    ui_automation_available = True
                except Exception:
                    unavailable["ui_automation"] = "Native Windows UI automation interface unavailable."
            else:
                unavailable["ui_automation"] = "pywinauto library is not installed."

        # 4. Mouse and Keyboard automation probe (PyAutoGUI)
        mouse_keyboard_available = False
        try:
            import pyautogui
            # Enable fail-safe feature by default
            pyautogui.FAILSAFE = True
            mouse_keyboard_available = True
        except ImportError:
            unavailable["mouse_keyboard"] = "pyautogui library is not installed."
        except Exception as exc:
            unavailable["mouse_keyboard"] = f"pyautogui initialization error: {exc}"

        # Permitted applications
        supported_apps = list(self.settings.DESKTOP_APPROVED_APPLICATIONS.keys())

        return DesktopCapabilityResponse(
            os_name=os_name,
            is_windows=is_windows,
            is_interactive_desktop=is_interactive,
            screenshot_available=screenshot_available,
            ui_automation_available=ui_automation_available,
            mouse_keyboard_available=mouse_keyboard_available,
            input_automation_enabled=self.settings.DESKTOP_INPUT_AUTOMATION_ENABLED,
            emergency_stop_active=emergency_stop_active,
            unavailable_reasons=unavailable,
            supported_applications=supported_apps,
        )
