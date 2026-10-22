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


# =========================================================================
# Phase 2: Desktop Subsystem Exceptions
# =========================================================================
class DesktopPermissionDeniedError(VenoraError):
    """Raised when an operation violates permission policies or allowlists."""
    def __init__(self, action: str, reason: str) -> None:
        super().__init__(f"Permission denied for '{action}': {reason}", details={"action": action, "reason": reason})
        self.action = action
        self.reason = reason


class DesktopEmergencyStopActiveError(VenoraError):
    """Raised when an automation action is requested while emergency stop is active."""
    def __init__(self) -> None:
        super().__init__("Desktop action blocked: Emergency stop is active.", details={"emergency_stop": True})


class DesktopCapabilityUnavailableError(VenoraError):
    """Raised when a requested capability is not supported or missing required libraries."""
    def __init__(self, capability: str, reason: str) -> None:
        super().__init__(f"Desktop capability '{capability}' unavailable: {reason}", details={"capability": capability, "reason": reason})
        self.capability = capability
        self.reason = reason


class DesktopApplicationLaunchError(VenoraError):
    """Raised when an authorized application fails to start or verify."""
    def __init__(self, app_id: str, reason: str) -> None:
        super().__init__(f"Failed to launch application '{app_id}': {reason}", details={"app_id": app_id, "reason": reason})
        self.app_id = app_id
        self.reason = reason


class ProcessNotFoundError(VenoraError):
    """Raised when inspecting a process that does not exist or has terminated."""
    def __init__(self, pid: int) -> None:
        super().__init__(f"Process with PID {pid} not found", details={"pid": pid})
        self.pid = pid


class ScreenshotNotFoundError(VenoraError):
    """Raised when requested screenshot ID cannot be located on disk."""
    def __init__(self, screenshot_id: str) -> None:
        super().__init__(f"Screenshot '{screenshot_id}' not found", details={"screenshot_id": screenshot_id})
        self.screenshot_id = screenshot_id


class DesktopActionExecutionError(VenoraError):
    """Raised when a desktop action execution fails or encounters invalid parameters."""
    def __init__(self, action_type: str, reason: str) -> None:
        super().__init__(f"Action '{action_type}' failed: {reason}", details={"action_type": action_type, "reason": reason})
        self.action_type = action_type
        self.reason = reason


# =========================================================================
# Phase 3: AI Provider & Tool Calling Exceptions
# =========================================================================
class AIProviderError(VenoraError):
    """Base exception for AI provider communication issues."""
    pass


class AIAuthenticationError(AIProviderError):
    """Raised when the AI provider authentication fails or API key is invalid."""
    pass


class AIRateLimitError(AIProviderError):
    """Raised when the AI provider returns a rate limit response (429)."""
    pass


class AITimeoutError(AIProviderError):
    """Raised when an AI provider inference request times out."""
    pass


class AIMalformedResponseError(AIProviderError):
    """Raised when the AI provider returns an unparseable or unexpected response."""
    pass


class ToolValidationError(VenoraError):
    """Raised when proposed tool arguments fail validation schemas."""
    def __init__(self, tool_name: str, reason: str) -> None:
        super().__init__(f"Tool '{tool_name}' argument validation failed: {reason}", details={"tool_name": tool_name, "reason": reason})
        self.tool_name = tool_name
        self.reason = reason


class ToolNotFoundError(VenoraError):
    """Raised when an unapproved or unregistered tool name is requested."""
    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Tool '{tool_name}' is not recognized or registered in the controlled tool registry.", details={"tool_name": tool_name})
        self.tool_name = tool_name


class MaxToolRoundsExceededError(VenoraError):
    """Raised when reasoning tool-call sequence exceeds safety bounds."""
    def __init__(self, max_rounds: int) -> None:
        super().__init__(f"Maximum tool-call rounds ({max_rounds}) exceeded for single user request.", details={"max_rounds": max_rounds})
        self.max_rounds = max_rounds


class ValidationError(VenoraError):
    """Raised when request payload or input parameter fails semantic validation."""
    pass


# =========================================================================
# Phase 4: Task Orchestration & Execution Exceptions
# =========================================================================
class PlanValidationError(VenoraError):
    """Raised when a generated or submitted task plan violates structural/dependency rules."""
    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(f"Task plan validation error: {message}", details=details)


class StepDependencyError(VenoraError):
    """Raised when step dependencies are unmet, cyclic, or missing."""
    pass


class TaskNotEligibleError(VenoraError):
    """Raised when a task cannot execute in its current lifecycle state."""
    pass


class TaskApprovalRequiredError(VenoraError):
    """Raised when attempting to execute a task or step requiring explicit approval."""
    pass


class TaskTimeoutError(VenoraError):
    """Raised when task or step exceeds configured execution timeout."""
    pass


class TaskCancelledError(VenoraError):
    """Raised when execution halts due to user or system cancellation."""
    pass


# =========================================================================
# Phase 5: File Intelligence & Document Understanding Exceptions
# =========================================================================
class DocumentError(VenoraError):
    """Base exception for document intelligence operations."""
    pass


class DocumentAccessDeniedError(DocumentError):
    """Raised when attempting to access a file or directory outside authorized paths."""
    def __init__(self, path: str, reason: str = "Path is not in the authorized directory allowlist.") -> None:
        super().__init__(f"Access denied to '{path}': {reason}", details={"path": path, "reason": reason})
        self.path = path
        self.reason = reason


class DocumentNotFoundError(DocumentError):
    """Raised when a requested document cannot be found."""
    def __init__(self, document_id: str) -> None:
        super().__init__(f"Document '{document_id}' not found.", details={"document_id": document_id})
        self.document_id = document_id


class DocumentSizeLimitError(DocumentError):
    """Raised when document size exceeds configured bounds."""
    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(
            f"Document size ({size_bytes} bytes) exceeds limit ({max_bytes} bytes).",
            details={"size_bytes": size_bytes, "max_bytes": max_bytes}
        )


class UnsupportedDocumentTypeError(DocumentError):
    """Raised when attempting to process an unsupported file extension or format."""
    def __init__(self, file_type: str) -> None:
        super().__init__(f"Document type '{file_type}' is unsupported.", details={"file_type": file_type})
        self.file_type = file_type


class DocumentExtractionError(DocumentError):
    """Raised when parsing or extracting text from a document fails."""
    def __init__(self, document_id: str, reason: str) -> None:
        super().__init__(f"Failed to extract document '{document_id}': {reason}", details={"document_id": document_id, "reason": reason})
        self.document_id = document_id
        self.reason = reason


class DocumentTimeoutError(DocumentError):
    """Raised when document processing exceeds timeout bounds."""
    pass



