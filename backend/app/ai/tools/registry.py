"""Controlled tool registry with strict validation, security policies, and permission enforcement."""

import logging
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from app.ai.schemas import ToolResult
from app.ai.tools.base import BaseTool
from app.core.errors import (
    DesktopPermissionDeniedError,
    ToolNotFoundError,
    ToolValidationError,
)
from app.desktop.permissions import DesktopPermissionService
from app.desktop.schemas import VerificationStatus

logger = logging.getLogger("venora.ai.tools.registry")


class ToolRegistry:
    """Central registry managing strictly controlled AI tools, schema validation, and permissions."""

    def __init__(self, permission_service: Optional[DesktopPermissionService] = None) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self.permission_service = permission_service

    def register(self, tool: BaseTool) -> None:
        """Register an approved tool instance."""
        if tool.name in self._tools:
            logger.warning(f"Overwriting previously registered tool: '{tool.name}'")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool '{tool.name}' (permission={tool.required_permission})")

    def get_tool(self, tool_name: str) -> BaseTool:
        """Retrieve tool by name or raise ToolNotFoundError."""
        if tool_name not in self._tools:
            raise ToolNotFoundError(f"Tool '{tool_name}' is not registered or allowed.")
        return self._tools[tool_name]

    def has_tool(self, tool_name: str) -> bool:
        """Check if tool exists in registry."""
        return tool_name in self._tools

    def list_tool_names(self) -> List[str]:
        """List registered tool names."""
        return sorted(list(self._tools.keys()))

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return list of OpenAPI / OpenRouter function calling definitions for registered tools."""
        return [tool.get_definition() for tool in self._tools.values()]

    def validate_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Validate proposed arguments against tool's Pydantic schema."""
        tool = self.get_tool(tool_name)
        if not tool.args_schema:
            return {}

        try:
            validated = tool.args_schema.model_validate(arguments)
            return validated.model_dump()
        except ValidationError as val_err:
            logger.warning(f"Argument validation failed for tool '{tool_name}': {val_err}")
            raise ToolValidationError(tool_name=tool_name, reason=str(val_err.errors()))

    async def execute_tool(self, call_id: str, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Strictly validate, authorize, and execute a tool call."""
        # 1. Existence check (rejection of arbitrary tool names or commands)
        if not self.has_tool(tool_name):
            logger.warning(f"Attempted execution of unapproved or unknown tool: '{tool_name}'")
            return ToolResult(
                call_id=call_id,
                tool_name=tool_name,
                status="rejected",
                result=None,
                error_code="UNKNOWN_TOOL",
                safe_error_message=f"Tool '{tool_name}' is not an approved tool.",
                verification_status=VerificationStatus.FAILED,
            )

        tool = self.get_tool(tool_name)

        # 2. Argument validation before permission check so resource_id (like app_id) is available
        try:
            validated_args = self.validate_arguments(tool_name, arguments)
        except ToolValidationError as tve:
            return ToolResult(
                call_id=call_id,
                tool_name=tool_name,
                status="invalid_arguments",
                result=None,
                error_code="INVALID_ARGUMENTS",
                safe_error_message=str(tve),
                verification_status=VerificationStatus.FAILED,
            )

        # 3. Permission check
        if tool.required_permission and self.permission_service:
            try:
                res_id = validated_args.get("app_id") if isinstance(validated_args, dict) else None
                self.permission_service.check_permission(tool.required_permission, resource_id=res_id)
            except DesktopPermissionDeniedError as perm_err:
                logger.warning(f"Permission denied executing '{tool_name}': {perm_err}")
                return ToolResult(
                    call_id=call_id,
                    tool_name=tool_name,
                    status="denied",
                    result=None,
                    error_code="PERMISSION_DENIED",
                    safe_error_message=f"Permission '{tool.required_permission}' was denied: {perm_err.reason}",
                    verification_status=VerificationStatus.FAILED,
                )


        # 4. Safe dispatch
        try:
            logger.info(f"Executing tool '{tool_name}' (call_id='{call_id}')")
            return await tool.execute(call_id, validated_args)
        except Exception as exc:
            logger.error(f"Unhandled exception during tool '{tool_name}' execution: {exc}", exc_info=True)
            return ToolResult(
                call_id=call_id,
                tool_name=tool_name,
                status="error",
                result=None,
                error_code="INTERNAL_TOOL_ERROR",
                safe_error_message="Tool encountered an internal execution error.",
                verification_status=VerificationStatus.FAILED,
            )
