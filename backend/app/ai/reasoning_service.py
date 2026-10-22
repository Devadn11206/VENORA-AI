"""Reasoning and tool-execution engine coordinating LLM provider, tool registry, and permissions."""

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.ai.conversation import ConversationManager, get_conversation_manager
from app.ai.prompts import VENORA_SYSTEM_INSTRUCTIONS
from app.ai.provider import BaseAIProvider
from app.ai.openrouter_provider import OpenRouterProvider
from app.ai.schemas import (
    AssistantResponse,
    ChatMessage,
    MessageRole,
    ResponseType,
    ToolCall,
    ToolResult,
)
from app.ai.tools.registry import ToolRegistry
from app.ai.tools import create_default_tool_registry
from app.core.config import Settings, get_settings
from app.core.errors import (
    AIProviderError,
    ConfigurationError,
    MaxToolRoundsExceededError,
    ValidationError,
)
from app.desktop.schemas import VerificationStatus

logger = logging.getLogger("venora.ai.reasoning")


class ReasoningService:
    """Coordinates conversational requests, model interaction, tool validation, and multi-round execution."""

    def __init__(
        self,
        provider: Optional[BaseAIProvider] = None,
        tool_registry: Optional[ToolRegistry] = None,
        conversation_manager: Optional[ConversationManager] = None,
        settings: Optional[Settings] = None,
        db: Optional[Session] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db
        self.provider = provider or OpenRouterProvider(settings=self.settings)
        self.tools = tool_registry or create_default_tool_registry(settings=self.settings, db=db)
        self.conversation_manager = conversation_manager or get_conversation_manager()
        self.max_tool_rounds = self.settings.MAX_TOOL_CALL_ROUNDS

    async def chat(self, message: str, conversation_id: Optional[str] = None) -> AssistantResponse:
        """Execute a full reasoning cycle for an incoming user prompt.
        
        Steps:
        1. Validate user message constraints.
        2. Resolve or create bounded conversation context.
        3. Assemble conversation thread with system instructions.
        4. Query AI provider with approved tool definitions.
        5. If conversational, return response.
        6. If tool call(s) requested:
           - Validate and execute via ToolRegistry.
           - Feed normalized results back to provider for subsequent reasoning.
           - Respect max tool rounds bound.
        7. Return normalized, truthful AssistantResponse.
        """
        # Step 1: Validate input
        clean_msg = message.strip()
        if not clean_msg:
            raise ValidationError("User message cannot be empty or purely whitespace.")
        if len(clean_msg) > self.settings.MAX_USER_MESSAGE_CHARS:
            raise ValidationError(
                f"User message exceeds maximum allowed limit of {self.settings.MAX_USER_MESSAGE_CHARS} characters."
            )

        # Step 2: Resolve context
        context = self.conversation_manager.get_or_create(conversation_id)
        conv_id = context.conversation_id

        # Record user turn in context
        user_chat_msg = ChatMessage(role=MessageRole.USER, content=clean_msg)
        context.add_message(user_chat_msg)

        logger.info(f"Reasoning cycle initiated for conversation='{conv_id}'")

        # Step 3: Check provider availability
        if not self.provider.is_configured():
            logger.warning("AI provider is not configured. Returning actionable status.")
            response = AssistantResponse(
                response_id=f"res_{secrets.token_hex(8)}",
                conversation_id=conv_id,
                message=(
                    "VENORA AI provider is not configured. Please configure an OPENROUTER_API_KEY in your "
                    "environment or .env file to enable intelligent reasoning and tool calling."
                ),
                response_type=ResponseType.ERROR,
                tool_calls=[],
                tool_results=[],
                requires_clarification=False,
                created_at=datetime.now(timezone.utc),
            )
            context.add_message(ChatMessage(role=MessageRole.ASSISTANT, content=response.message))
            return response

        # Step 4: Iterative reasoning loop with bounded rounds
        accumulated_tool_results: List[ToolResult] = []
        all_tool_calls: List[ToolCall] = []
        current_messages = context.get_messages()
        round_count = 0

        while round_count < self.max_tool_rounds:
            round_count += 1
            tool_definitions = self.tools.get_tool_definitions()

            try:
                ai_resp = await self.provider.generate_response(
                    messages=current_messages,
                    tools=tool_definitions if tool_definitions else None,
                    system_instruction=VENORA_SYSTEM_INSTRUCTIONS,
                )
            except AIProviderError as aie:
                logger.error(f"AI Provider error during round {round_count}: {aie}")
                error_resp = AssistantResponse(
                    response_id=f"res_{secrets.token_hex(8)}",
                    conversation_id=conv_id,
                    message=f"I encountered an error communicating with my reasoning provider: {aie}",
                    response_type=ResponseType.ERROR,
                    tool_calls=all_tool_calls,
                    tool_results=accumulated_tool_results,
                    requires_clarification=False,
                    created_at=datetime.now(timezone.utc),
                )
                context.add_message(ChatMessage(role=MessageRole.ASSISTANT, content=error_resp.message))
                return error_resp

            # Check if provider produced tool calls
            if not ai_resp.tool_calls:
                # Normal conversational termination
                final_response = AssistantResponse(
                    response_id=ai_resp.response_id,
                    conversation_id=conv_id,
                    message=ai_resp.message or "I have completed processing your request.",
                    response_type=ResponseType.TOOL_RESULT if accumulated_tool_results else ResponseType.CONVERSATIONAL,
                    tool_calls=all_tool_calls,
                    tool_results=accumulated_tool_results,
                    requires_clarification=ai_resp.requires_clarification,
                    usage_metadata=ai_resp.usage_metadata,
                    provider_metadata=ai_resp.provider_metadata,
                    created_at=datetime.now(timezone.utc),
                )
                context.add_message(ChatMessage(role=MessageRole.ASSISTANT, content=final_response.message))
                return final_response

            # Process tool calls proposed by provider
            logger.info(f"Round {round_count}: Provider proposed {len(ai_resp.tool_calls)} tool call(s)")
            all_tool_calls.extend(ai_resp.tool_calls)

            # Record assistant message containing tool calls in the message chain
            assistant_tool_msg = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=ai_resp.message or "",
                tool_calls=[
                    {
                        "id": tc.call_id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in ai_resp.tool_calls
                ],
            )
            current_messages.append(assistant_tool_msg)
            context.add_message(assistant_tool_msg)

            # Execute each proposed tool safely through registry
            for tc in ai_resp.tool_calls:
                res = await self.tools.execute_tool(
                    call_id=tc.call_id,
                    tool_name=tc.tool_name,
                    arguments=tc.arguments,
                )
                accumulated_tool_results.append(res)

                # Format tool output for provider consumption
                # Tool outputs are treated as untrusted strings and never execute as code
                tool_payload_str = json.dumps(
                    {
                        "status": res.status,
                        "result": res.result,
                        "error_code": res.error_code,
                        "safe_error_message": res.safe_error_message,
                        "verification_status": res.verification_status.value,
                    }
                )

                tool_chat_msg = ChatMessage(
                    role=MessageRole.TOOL,
                    content=tool_payload_str,
                    name=tc.tool_name,
                    tool_call_id=tc.call_id,
                )
                current_messages.append(tool_chat_msg)
                context.add_message(tool_chat_msg)

        # If loop exited due to exceeding max tool rounds
        logger.warning(f"Exceeded maximum reasoning tool call rounds ({self.max_tool_rounds}) for conversation '{conv_id}'")
        bounded_response = AssistantResponse(
            response_id=f"res_{secrets.token_hex(8)}",
            conversation_id=conv_id,
            message=(
                f"I performed {len(accumulated_tool_results)} tool actions, but reached the maximum allowed reasoning "
                f"rounds ({self.max_tool_rounds}). Here is what has been accomplished so far."
            ),
            response_type=ResponseType.TOOL_RESULT,
            tool_calls=all_tool_calls,
            tool_results=accumulated_tool_results,
            requires_clarification=False,
            created_at=datetime.now(timezone.utc),
        )
        context.add_message(ChatMessage(role=MessageRole.ASSISTANT, content=bounded_response.message))
        return bounded_response
