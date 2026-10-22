"""OpenRouter API client implementation supporting chat completions and native tool calling."""

import json
import logging
import secrets
import httpx
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.ai.provider import BaseAIProvider
from app.ai.prompts import VENORA_SYSTEM_INSTRUCTIONS
from app.ai.schemas import (
    AssistantResponse,
    ChatMessage,
    MessageRole,
    ResponseType,
    ToolCall,
)
from app.core.config import Settings, get_settings
from app.core.errors import (
    AIAuthenticationError,
    AIMalformedResponseError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    ConfigurationError,
)

logger = logging.getLogger("venora.ai.openrouter")


class OpenRouterProvider(BaseAIProvider):
    """Client for OpenRouter LLM API with structured tool calling and normalized outputs."""

    def __init__(self, settings: Optional[Settings] = None, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client
        self.base_url = self.settings.VENORA_AI_BASE_URL.rstrip("/")
        self.model = self.settings.VENORA_AI_MODEL
        self.timeout = self.settings.VENORA_AI_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        """Verify if OpenRouter API key is provided and non-empty."""
        return bool(self.settings.OPENROUTER_API_KEY and self.settings.OPENROUTER_API_KEY.strip())

    def _get_headers(self) -> Dict[str, str]:
        """Construct sanitized authorization headers without logging credentials."""
        if not self.is_configured():
            raise ConfigurationError("OpenRouter API key is not configured. Set OPENROUTER_API_KEY in environment or .env.")

        return {
            "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY.strip()}",
            "HTTP-Referer": "http://127.0.0.1:8000",
            "X-Title": self.settings.APP_NAME,
            "Content-Type": "application/json",
        }

    async def generate_response(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> AssistantResponse:
        """Call OpenRouter completions endpoint with normalized message structures."""
        if not self.is_configured():
            raise ConfigurationError("AI provider is not configured. Please supply an OPENROUTER_API_KEY in .env to enable AI reasoning.")

        headers = self._get_headers()
        system_prompt = system_instruction or VENORA_SYSTEM_INSTRUCTIONS

        # Assemble messages payload
        api_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

        for msg in messages:
            msg_dict: Dict[str, Any] = {"role": msg.role.value}
            if msg.content is not None:
                msg_dict["content"] = msg.content
            if msg.name:
                msg_dict["name"] = msg.name
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                msg_dict["tool_calls"] = msg.tool_calls
            api_messages.append(msg_dict)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
        }
        if tools:
            payload["tools"] = tools

        endpoint = f"{self.base_url}/chat/completions"
        logger.info(f"Dispatching AI request to OpenRouter model='{self.model}' (messages={len(api_messages)}, tools={len(tools) if tools else 0})")

        # Execute request using provided or dedicated AsyncClient
        try:
            client_ctx = self.http_client or httpx.AsyncClient(timeout=self.timeout)
            if self.http_client:
                response = await self.http_client.post(endpoint, json=payload, headers=headers)
            else:
                async with client_ctx as client:
                    response = await client.post(endpoint, json=payload, headers=headers)

            # Status code evaluation
            if response.status_code == 401 or response.status_code == 403:
                logger.error("OpenRouter authentication failed: Invalid or expired API key.")
                raise AIAuthenticationError("Authentication with AI provider failed. Please verify OPENROUTER_API_KEY.")

            if response.status_code == 429:
                logger.warning("OpenRouter rate limit reached.")
                raise AIRateLimitError("AI provider rate limit reached. Please retry after a brief delay.")

            if response.status_code >= 500:
                logger.error(f"OpenRouter upstream server error: {response.status_code} {response.text}")
                raise AIProviderError(f"AI provider upstream error ({response.status_code}).")

            if response.status_code != 200:
                logger.error(f"OpenRouter unexpected status: {response.status_code} {response.text}")
                raise AIProviderError(f"AI provider returned unexpected status code: {response.status_code}")

            data = response.json()
            return self._parse_provider_response(data)

        except httpx.TimeoutException:
            logger.error(f"AI request timed out after {self.timeout}s.")
            raise AITimeoutError(f"Request to AI provider timed out after {self.timeout} seconds.")
        except httpx.RequestError as req_err:
            logger.error(f"Network error communicating with AI provider: {req_err}")
            raise AIProviderError(f"Network error connecting to AI provider: {req_err}")

    def _parse_provider_response(self, data: Dict[str, Any]) -> AssistantResponse:
        """Parse and normalize OpenRouter response into AssistantResponse schema."""
        try:
            choices = data.get("choices")
            if not choices or not isinstance(choices, list):
                raise AIMalformedResponseError("Response missing 'choices' array from provider.")

            choice = choices[0]
            message_obj = choice.get("message", {})
            raw_content = message_obj.get("content") or ""
            raw_tool_calls = message_obj.get("tool_calls") or []

            tool_calls: List[ToolCall] = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                call_id = tc.get("id") or f"call_{secrets.token_hex(6)}"
                tool_name = fn.get("name")
                raw_args = fn.get("arguments")

                parsed_args: Dict[str, Any] = {}
                if isinstance(raw_args, dict):
                    parsed_args = raw_args
                elif isinstance(raw_args, str) and raw_args.strip():
                    try:
                        parsed_args = json.loads(raw_args)
                    except json.JSONDecodeError as jde:
                        logger.warning(f"Failed to parse tool arguments JSON for {tool_name}: {jde}")
                        parsed_args = {"_raw_arguments": raw_args}

                tool_calls.append(
                    ToolCall(
                        call_id=call_id,
                        tool_name=tool_name,
                        arguments=parsed_args,
                        purpose=None,
                    )
                )

            # Determine response type
            if tool_calls:
                response_type = ResponseType.PROPOSED_TOOL_CALL
            else:
                response_type = ResponseType.CONVERSATIONAL

            return AssistantResponse(
                response_id=data.get("id") or f"gen_{secrets.token_hex(8)}",
                conversation_id="conv_default",
                message=raw_content.strip(),
                response_type=response_type,
                tool_calls=tool_calls,
                tool_results=[],
                requires_clarification=False,
                usage_metadata=data.get("usage"),
                provider_metadata={"model": data.get("model", self.model)},
                created_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            if isinstance(exc, AIProviderError):
                raise
            logger.error(f"Failed to normalize provider response: {exc}", exc_info=True)
            raise AIMalformedResponseError(f"Could not parse valid structure from AI response: {exc}")
