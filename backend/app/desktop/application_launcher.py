"""Safe application launching service with strict allowlist and process verification."""

import logging
import os
import shutil
import subprocess
import time
from typing import Dict, List, Optional, Tuple
from app.core.config import Settings, get_settings
from app.core.errors import DesktopApplicationLaunchError, DesktopPermissionDeniedError
from app.desktop.permissions import DesktopPermissionService
from app.desktop.schemas import ActionStatus, ApplicationInfo, LaunchApplicationResponse, VerificationStatus

logger = logging.getLogger("venora.desktop.launcher")


class ApplicationLauncherService:
    """Manages whitelisted desktop application launching with process verification."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        permission_service: Optional[DesktopPermissionService] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.permissions = permission_service or DesktopPermissionService(self.settings)

    def list_applications(self) -> List[ApplicationInfo]:
        """Return all configured applications and verify whether their executable is discoverable."""
        self.permissions.check_permission("desktop.applications.list")
        apps: List[ApplicationInfo] = []

        for app_id, exe_name in self.settings.DESKTOP_APPROVED_APPLICATIONS.items():
            # Check if binary is in PATH or exists as an absolute path
            path = shutil.which(exe_name)
            is_available = path is not None or os.path.exists(exe_name)
            apps.append(
                ApplicationInfo(
                    app_id=app_id,
                    executable=exe_name,
                    is_available=is_available,
                    description=f"System binary: {exe_name}",
                )
            )

        return apps

    def launch_application(
        self,
        app_id: str,
        arguments: Optional[List[str]] = None,
        task_id: Optional[int] = None,
    ) -> LaunchApplicationResponse:
        """Launch an approved application safely using subprocess without shell injection."""
        app_key = app_id.lower().strip()
        self.permissions.check_permission("desktop.applications.launch", resource_id=app_key)

        executable = self.settings.DESKTOP_APPROVED_APPLICATIONS.get(app_key)
        if not executable:
            raise DesktopPermissionDeniedError(
                action="desktop.applications.launch",
                reason=f"Application '{app_id}' is not configured in the allowlist."
            )

        # Build clean command arguments list (never use shell=True)
        command_args = [executable]
        if arguments:
            # Only allow non-empty string arguments; reject dangerous shell redirections
            for arg in arguments:
                clean_arg = str(arg).strip()
                if any(c in clean_arg for c in ["&", "|", ";", "`", "$", "\n", "\r", ">", "<"]):
                    raise DesktopApplicationLaunchError(
                        app_id=app_key,
                        reason=f"Argument contains prohibited shell redirection/control characters: {clean_arg!r}"
                    )
                command_args.append(clean_arg)

        logger.info(f"Launching approved application '{app_key}' via command: {command_args}")
        started_at = time.time()

        try:
            # Spawn process without shell
            process = subprocess.Popen(
                command_args,
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            pid = process.pid

            # Bounded verification: verify process PID is active
            time.sleep(0.2)  # Brief delay to allow OS process initialization
            poll_status = process.poll()

            # For GUI apps, if process has already exited with code 0 or != 0 immediately, check
            is_alive = True
            try:
                import psutil
                is_alive = psutil.pid_exists(pid)
            except Exception:
                is_alive = poll_status is None

            if not is_alive and poll_status is not None and poll_status != 0:
                raise DesktopApplicationLaunchError(
                    app_id=app_key,
                    reason=f"Process terminated immediately after launch with exit code {poll_status}"
                )

            verification = VerificationStatus.VERIFIED if is_alive else VerificationStatus.PARTIALLY_VERIFIED

            from app.database.base import utc_now
            return LaunchApplicationResponse(
                app_id=app_key,
                pid=pid,
                status=ActionStatus.COMPLETED,
                verification_status=verification,
                message=f"Application '{app_key}' launched successfully with PID {pid}.",
                started_at=utc_now(),
            )
        except DesktopApplicationLaunchError:
            raise
        except Exception as exc:
            logger.error(f"Failed to launch application '{app_key}': {exc}", exc_info=True)
            raise DesktopApplicationLaunchError(app_id=app_key, reason=str(exc))
