"""Abstract base provider interface for AI reasoning engines."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from app.ai.schemas import AssistantResponse, ChatMessage


class BaseAIProvider(ABC):
    """Abstract interface defining required capabilities for AI reasoning backends."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Check whether the provider has the required configuration/credentials."""
        pass

    @abstractmethod
    async def generate_response(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> AssistantResponse:
        """Generate a reasoning response with optional structured tool definitions."""
        pass
