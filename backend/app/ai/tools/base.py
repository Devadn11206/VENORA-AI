"""Base classes for controlled tools within the VENORA AI reasoning subsystem."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

from app.ai.schemas import ToolResult
from app.desktop.schemas import VerificationStatus


class ToolDefinition(BaseModel):
    """Schema metadata describing a registered tool for LLM function calling."""
    name: str
    description: str
    parameters: Dict[str, Any]
    required_permission: Optional[str] = None
    timeout_seconds: float = 30.0
    requires_approval: bool = False
    is_read_only: bool = True


class BaseTool(ABC):
    """Abstract base class for all strictly controlled executable tools."""

    name: str
    description: str
    args_schema: Optional[Type[BaseModel]] = None
    required_permission: Optional[str] = None
    timeout_seconds: float = 30.0
    requires_approval: bool = False
    is_read_only: bool = True

    def get_definition(self) -> Dict[str, Any]:
        """Produce OpenAI / OpenRouter function calling compatible definition."""
        parameters: Dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        if self.args_schema:
            schema = self.args_schema.model_json_schema()
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            parameters = {
                "type": "object",
                "properties": properties,
                "required": required,
            }

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }

    @abstractmethod
    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute the tool safely and return a normalized ToolResult."""
        pass
