"""Task-scoped desktop screenshot capture and secure retrieval service."""

import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageGrab

from app.core.config import Settings, get_settings
from app.core.errors import (
    DesktopCapabilityUnavailableError,
    ScreenshotNotFoundError,
)
from app.desktop.permissions import DesktopPermissionService
from app.desktop.schemas import ScreenshotInfo, VerificationStatus

logger = logging.getLogger("venora.desktop.screenshot")


class ScreenshotService:
    """Manages secure, task-scoped screenshot capture and localized file retrieval."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        permission_service: Optional[DesktopPermissionService] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.permissions = permission_service or DesktopPermissionService(self.settings)

    def capture_screenshot(
        self,
        task_id: Optional[int] = None,
        label: Optional[str] = None,
    ) -> ScreenshotInfo:
        """Capture an on-demand desktop screenshot, save it with an unguessable filename, and verify integrity."""
        self.permissions.check_permission("desktop.screenshot.capture")

        storage_dir = self.settings.resolved_screenshot_dir

        # Generate unguessable screenshot identifier
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        rand_token = secrets.token_hex(8)
        screenshot_id = f"snap_{timestamp_str}_{rand_token}"
        filename = f"{screenshot_id}.png"
        file_path = storage_dir / filename

        logger.info(f"Initiating screenshot capture -> {file_path}")

        try:
            # Capture image using Pillow
            image = ImageGrab.grab()
            if image is None:
                raise DesktopCapabilityUnavailableError(
                    capability="screenshot",
                    reason="Screen capture returned None (desktop may be locked or running in a headless session)."
                )

            width, height = image.size

            # Save PNG to disk
            image.save(str(file_path), format="PNG", optimize=True)

            # Verification step: ensure file exists and is readable
            if not file_path.exists():
                raise FileNotFoundError(f"Screenshot file was not saved: {file_path}")

            file_size = file_path.stat().st_size
            if file_size == 0:
                raise ValueError("Captured screenshot resulted in an empty 0-byte file.")

            # Verify image can be reopened
            with Image.open(str(file_path)) as verified_img:
                verified_img.verify()

            captured_dt = datetime.now(timezone.utc)
            logger.info(f"Screenshot successfully verified ({width}x{height}, {file_size} bytes)")

            return ScreenshotInfo(
                screenshot_id=screenshot_id,
                filename=filename,
                captured_at=captured_dt,
                file_size_bytes=file_size,
                width=width,
                height=height,
                task_id=task_id,
                verification_status=VerificationStatus.VERIFIED,
            )
        except DesktopCapabilityUnavailableError:
            raise
        except Exception as exc:
            logger.error(f"Screenshot capture failed: {exc}", exc_info=True)
            raise DesktopCapabilityUnavailableError(
                capability="screenshot",
                reason=f"Failed to capture or verify screenshot: {exc}"
            )

    def get_screenshot_path(self, screenshot_id: str) -> Path:
        """Locate and validate screenshot file on disk, enforcing directory containment."""
        self.permissions.check_permission("desktop.screenshot.read")

        # Sanitize screenshot_id: prevent directory traversal
        clean_id = os.path.basename(screenshot_id.strip())
        if not clean_id.startswith("snap_") or clean_id != screenshot_id.strip():
            raise ScreenshotNotFoundError(screenshot_id=screenshot_id)

        filename = f"{clean_id}.png" if not clean_id.endswith(".png") else clean_id
        storage_dir = self.settings.resolved_screenshot_dir
        target_path = (storage_dir / filename).resolve()

        # Strict boundary enforcement: target path must reside strictly inside storage_dir
        if not str(target_path).startswith(str(storage_dir)):
            logger.warning(f"Directory traversal attempt detected: {screenshot_id}")
            raise ScreenshotNotFoundError(screenshot_id=screenshot_id)

        if not target_path.exists() or not target_path.is_file():
            raise ScreenshotNotFoundError(screenshot_id=screenshot_id)

        return target_path
