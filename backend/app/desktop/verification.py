"""Outcome verification and state validation logic for desktop operations."""

import logging
from typing import Any, Dict, Optional
import psutil
from app.desktop.schemas import VerificationStatus

logger = logging.getLogger("venora.desktop.verification")


class DesktopOutcomeVerifier:
    """Evaluates whether desktop actions produced empirical verified outcomes."""

    @staticmethod
    def verify_process_running(pid: int) -> VerificationStatus:
        """Verify that a launched process is active and recognized by the OS."""
        try:
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    return VerificationStatus.VERIFIED
            return VerificationStatus.FAILED
        except Exception as exc:
            logger.debug(f"Verification error for PID {pid}: {exc}")
            return VerificationStatus.UNVERIFIED

    @staticmethod
    def verify_file_exists_and_readable(path_str: str) -> VerificationStatus:
        """Verify that an artifact file (e.g. screenshot) was written and can be read."""
        from pathlib import Path
        try:
            p = Path(path_str)
            if p.exists() and p.is_file() and p.stat().st_size > 0:
                return VerificationStatus.VERIFIED
            return VerificationStatus.FAILED
        except Exception:
            return VerificationStatus.FAILED
