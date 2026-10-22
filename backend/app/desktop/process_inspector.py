"""Read-only, sanitized process inspection service."""

import logging
from datetime import datetime, timezone
from typing import List, Optional
import psutil

from app.core.config import Settings, get_settings
from app.core.errors import ProcessNotFoundError
from app.desktop.permissions import DesktopPermissionService
from app.desktop.schemas import ProcessInfo

logger = logging.getLogger("venora.desktop.processes")


class ProcessInspectorService:
    """Provides read-only inspection of running system processes without exposing secrets."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        permission_service: Optional[DesktopPermissionService] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.permissions = permission_service or DesktopPermissionService(self.settings)

    def list_processes(self, limit: int = 50) -> List[ProcessInfo]:
        """List running system processes with sanitized metadata."""
        self.permissions.check_permission("desktop.processes.read")
        results: List[ProcessInfo] = []
        bound_limit = max(1, min(limit, 200))

        for proc in psutil.process_iter(['pid', 'name', 'status', 'create_time']):
            try:
                info = proc.info
                created_dt = None
                if info.get('create_time'):
                    created_dt = datetime.fromtimestamp(info['create_time'], tz=timezone.utc)

                results.append(
                    ProcessInfo(
                        pid=info['pid'],
                        name=info.get('name') or "unknown",
                        status=str(info.get('status') or "running"),
                        created_at=created_dt,
                    )
                )
                if len(results) >= bound_limit:
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as exc:
                logger.debug(f"Error inspecting process: {exc}")
                continue

        return results

    def get_process_by_pid(self, pid: int) -> ProcessInfo:
        """Inspect a specific process by PID or raise ProcessNotFoundError."""
        self.permissions.check_permission("desktop.processes.read")
        try:
            proc = psutil.Process(pid)
            created_dt = None
            try:
                created_dt = datetime.fromtimestamp(proc.create_time(), tz=timezone.utc)
            except Exception:
                pass

            cpu_pct = None
            mem_pct = None
            try:
                cpu_pct = proc.cpu_percent(interval=None)
                mem_pct = proc.memory_percent()
            except Exception:
                pass

            return ProcessInfo(
                pid=proc.pid,
                name=proc.name(),
                status=str(proc.status()),
                cpu_percent=round(cpu_pct, 2) if cpu_pct is not None else None,
                memory_percent=round(mem_pct, 2) if mem_pct is not None else None,
                created_at=created_dt,
            )
        except psutil.NoSuchProcess:
            raise ProcessNotFoundError(pid=pid)
        except psutil.AccessDenied:
            # Report restricted visibility without failing
            return ProcessInfo(
                pid=pid,
                name="[Access Denied]",
                status="restricted",
            )
        except Exception as exc:
            logger.error(f"Error reading PID {pid}: {exc}")
            raise ProcessNotFoundError(pid=pid)
