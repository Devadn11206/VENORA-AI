"""Desktop permission verification service with default-deny enforcement."""

import logging
from typing import Dict, List, Optional, Set
from app.core.config import Settings, get_settings
from app.core.errors import (
    DesktopEmergencyStopActiveError,
    DesktopPermissionDeniedError,
)

logger = logging.getLogger("venora.desktop.permissions")

# Process-level emergency stop flag to share state across HTTP requests
_GLOBAL_EMERGENCY_STOP: bool = False


class DesktopPermissionService:
    """Manages action-level authorization and allowlist policies for desktop operations."""

    # Explicit recognized action categories
    KNOWN_ACTIONS: Set[str] = {
        "desktop.capabilities.read",
        "desktop.applications.list",
        "desktop.applications.launch",
        "desktop.processes.read",
        "desktop.screenshot.capture",
        "desktop.screenshot.read",
        "desktop.ui.inspect",
        "desktop.ui.activate",
        "desktop.input.mouse",
        "desktop.input.keyboard",
        "desktop.emergency_stop.toggle",
        # Phase 5: Document Intelligence Permissions
        "document.read",
        "document.search",
        "document.extract",
        "document.summarize",
        "document.compare",
        "document.index",
        "document.export",
        # Phase 6: Browser Automation & Web Intelligence Permissions
        "browser.session.create",
        "browser.session.close",
        "browser.navigate",
        "browser.page.inspect",
        "browser.interact.click",
        "browser.interact.fill",
        "browser.interact.select",
        "browser.interact.scroll",
        "browser.screenshot",
        "browser.search",
        "browser.research",
        # Phase 7: Long-Term Memory & Retrieval Permissions
        "memory.read",
        "memory.search",
        "memory.create",
        "memory.update",
        "memory.archive",
        "memory.delete",
        # Phase 8: Voice Interface Permissions
        "voice.capabilities.read",
        "voice.session.create",
        "voice.session.cancel",
        "voice.capture.start",
        "voice.capture.stop",
        "voice.transcribe",
        "voice.synthesize",
        "voice.respond",
        "voice.audio.read",
    }

    # Approved standard keyboard keys allowlist
    ALLOWED_KEYS: Set[str] = {
        "enter", "return", "tab", "space", "backspace", "delete", "esc", "escape",
        "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
        "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
        "ctrl", "alt", "shift", "win", "windows"
    }

    def __init__(self, settings: Optional[Settings] = None) -> None:
        global _GLOBAL_EMERGENCY_STOP
        self.settings = settings or get_settings()
        if self.settings.DESKTOP_EMERGENCY_STOP_ACTIVE:
            _GLOBAL_EMERGENCY_STOP = True

    @property
    def emergency_stop_active(self) -> bool:
        """Check whether emergency stop is currently engaged."""
        global _GLOBAL_EMERGENCY_STOP
        return _GLOBAL_EMERGENCY_STOP

    def set_emergency_stop(self, active: bool) -> None:
        """Set the emergency stop state."""
        global _GLOBAL_EMERGENCY_STOP
        _GLOBAL_EMERGENCY_STOP = active
        if active:
            logger.warning("EMERGENCY STOP ACTIVATED: All interactive desktop operations are now halted.")
        else:
            logger.info("Emergency stop deactivated by authorized local command.")

    def check_permission(self, action: str, resource_id: Optional[str] = None) -> None:
        """Verify whether an action is permitted under current settings and safety guards.
        
        Raises DesktopPermissionDeniedError or DesktopEmergencyStopActiveError on denial.
        """
        # 1. Action validation
        if action not in self.KNOWN_ACTIONS:
            logger.warning(f"Permission denied: Unknown action '{action}'")
            raise DesktopPermissionDeniedError(action=action, reason=f"Unrecognized action '{action}'. Default-deny applied.")

        # 2. Emergency stop check takes highest precedence for operational actions
        if self.emergency_stop_active and action not in {"desktop.capabilities.read", "desktop.emergency_stop.toggle"}:
            logger.warning(f"Action '{action}' blocked by active Emergency Stop.")
            raise DesktopEmergencyStopActiveError()

        # 3. Master automation switches
        if action.startswith("desktop.") and not self.settings.DESKTOP_AUTOMATION_ENABLED:
            logger.warning(f"Permission denied for '{action}': Desktop automation is globally disabled.")
            raise DesktopPermissionDeniedError(action=action, reason="Desktop automation subsystem is disabled in configuration.")

        if action.startswith("browser.") and not self.settings.BROWSER_ENABLED:
            logger.warning(f"Permission denied for '{action}': Browser automation is globally disabled.")
            raise DesktopPermissionDeniedError(action=action, reason="Browser automation subsystem is disabled in configuration.")

        if action.startswith("voice.") and not getattr(self.settings, "VOICE_ENABLED", True):
            logger.warning(f"Permission denied for '{action}': Voice interface is globally disabled.")
            raise DesktopPermissionDeniedError(action=action, reason="Voice interface subsystem is disabled in configuration.")

        if action.startswith("voice.capture.") and not getattr(self.settings, "VOICE_MICROPHONE_ENABLED", False):
            logger.warning(f"Permission denied for '{action}': Microphone access is disabled by default.")
            raise DesktopPermissionDeniedError(
                action=action,
                reason="Microphone hardware access is disabled. Enable VOICE_MICROPHONE_ENABLED=true in configuration to permit."
            )

        # 4. Input automation specific check (Mouse & Keyboard)
        if action in {"desktop.input.mouse", "desktop.input.keyboard", "desktop.ui.activate"}:
            if not self.settings.DESKTOP_INPUT_AUTOMATION_ENABLED:
                logger.warning(f"Permission denied for '{action}': Input automation is disabled by default.")
                raise DesktopPermissionDeniedError(
                    action=action,
                    reason="Input automation (mouse/keyboard) is disabled. Set DESKTOP_INPUT_AUTOMATION_ENABLED=true in config to permit."
                )

        # 5. Application launch allowlist check
        if action == "desktop.applications.launch":
            if not resource_id:
                raise DesktopPermissionDeniedError(action=action, reason="Application ID must be specified for launch.")
            allowed_apps = self.settings.DESKTOP_APPROVED_APPLICATIONS
            if resource_id.lower() not in allowed_apps:
                logger.warning(f"Permission denied: Application '{resource_id}' is not in approved allowlist {list(allowed_apps.keys())}")
                raise DesktopPermissionDeniedError(
                    action=action,
                    reason=f"Application '{resource_id}' is not in approved allowlist. Permitted: {list(allowed_apps.keys())}"
                )

        logger.debug(f"Permission granted for action '{action}' (resource={resource_id})")

    def validate_key(self, key_name: str) -> str:
        """Validate key name against allowlist and return normalized key."""
        clean_key = key_name.strip().lower()
        if clean_key not in self.ALLOWED_KEYS:
            raise DesktopPermissionDeniedError(
                action="desktop.input.keyboard",
                reason=f"Key '{key_name}' is not in the approved keyboard allowlist."
            )
        return clean_key
