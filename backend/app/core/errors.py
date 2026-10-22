"""Core error classes and exception definitions for VENORA AI."""

from typing import Any, Optional


class VenoraError(Exception):
    """Base exception class for all VENORA application errors."""

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ConfigurationError(VenoraError):
    """Raised when application configuration is invalid or missing."""
    pass


class DatabaseConnectionError(VenoraError):
    """Raised when database connectivity cannot be established or fails."""
    pass


class TaskNotFoundError(VenoraError):
    """Raised when a requested task does not exist."""

    def __init__(self, task_id: int) -> None:
        super().__init__(f"Task with ID {task_id} not found", details={"task_id": task_id})
        self.task_id = task_id


class InvalidTaskStateError(VenoraError):
    """Raised when an operation is invalid for the current task state."""

    def __init__(self, message: str, current_status: Optional[str] = None, target_status: Optional[str] = None) -> None:
        super().__init__(
            message,
            details={"current_status": current_status, "target_status": target_status}
        )
        self.current_status = current_status
        self.target_status = target_status
