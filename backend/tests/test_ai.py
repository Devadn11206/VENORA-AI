"""Automated tests for Phase 3: AI Reasoning, Provider Abstraction, Tool Registry, and Assistant API."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

import pytest
from fastapi.testclient import TestClient

from app.ai.conversation import ConversationManager
from app.ai.openrouter_provider import OpenRouterProvider
from app.ai.prompts import VENORA_SYSTEM_INSTRUCTIONS
from app.ai.reasoning_service import ReasoningService
from app.ai.schemas import (
    AssistantResponse,
    ChatMessage,
    MessageRole,
    ResponseType,
    ToolCall,
    ToolResult,
)
from app.ai.tools import create_default_tool_registry
from app.ai.tools.base import BaseTool
from app.ai.tools.registry import ToolRegistry
from app.core.config import Settings
from app.core.errors import (
    AIAuthenticationError,
    AIMalformedResponseError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    ConfigurationError,
    DesktopPermissionDeniedError,
    ToolNotFoundError,
    ValidationError,
)
from app.desktop.schemas import VerificationStatus
from app.desktop.service import DesktopService


# =============================================================================
# 1. Provider Unit Tests (Mocked OpenRouter API)
# =============================================================================

@pytest.mark.asyncio
async def test_provider_missing_api_key_raises_configuration_error():
    """Verify that unconfigured API key yields a clean, actionable ConfigurationError without making requests."""
    settings = Settings(OPENROUTER_API_KEY="")
    provider = OpenRouterProvider(settings=settings)
    assert not provider.is_configured()

    with pytest.raises(ConfigurationError) as exc_info:
        await provider.generate_response(messages=[ChatMessage(role=MessageRole.USER, content="Hello")])
    assert "OPENROUTER_API_KEY" in str(exc_info.value)


@pytest.mark.asyncio
async def test_provider_successful_normalized_response():
    """Verify standard completion parsing into normalized AssistantResponse schema."""
    settings = Settings(OPENROUTER_API_KEY="sk-or-v1-mock-test-key")
    
    mock_response_data = {
        "id": "gen-12345",
        "model": "deepseek/deepseek-chat",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Reinforcement learning is a subfield of machine learning...",
                }
            }
        ],
        "usage": {"prompt_tokens": 15, "completion_tokens": 40, "total_tokens": 55},
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.json.return_value = mock_response_data
    mock_client.post.return_value = mock_post_res

    provider = OpenRouterProvider(settings=settings, http_client=mock_client)
    res = await provider.generate_response(
        messages=[ChatMessage(role=MessageRole.USER, content="Explain RL")]
    )

    assert res.response_id == "gen-12345"
    assert res.response_type == ResponseType.CONVERSATIONAL
    assert "Reinforcement learning" in res.message
    assert res.tool_calls == []
    assert res.usage_metadata["total_tokens"] == 55


@pytest.mark.asyncio
async def test_provider_tool_calls_normalized_parsing():
    """Verify provider parses structured tool calls correctly from model choices."""
    settings = Settings(OPENROUTER_API_KEY="sk-or-v1-mock-test-key")

    mock_response_data = {
        "id": "gen-tool-1",
        "model": "anthropic/claude-3.5-sonnet",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Opening Notepad for you.",
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "type": "function",
                            "function": {
                                "name": "launch_application",
                                "arguments": json.dumps({"app_id": "notepad"}),
                            },
                        }
                    ],
                }
            }
        ],
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.json.return_value = mock_response_data
    mock_client.post.return_value = mock_post_res

    provider = OpenRouterProvider(settings=settings, http_client=mock_client)
    res = await provider.generate_response(
        messages=[ChatMessage(role=MessageRole.USER, content="Open Notepad")]
    )

    assert res.response_type == ResponseType.PROPOSED_TOOL_CALL
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].tool_name == "launch_application"
    assert res.tool_calls[0].arguments == {"app_id": "notepad"}
    assert res.tool_calls[0].call_id == "call_abc123"


@pytest.mark.asyncio
async def test_provider_authentication_error():
    """Verify 401 response raises typed AIAuthenticationError without credential exposure."""
    settings = Settings(OPENROUTER_API_KEY="sk-invalid-key")
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_post_res = MagicMock()
    mock_post_res.status_code = 401
    mock_post_res.text = "Unauthorized"
    mock_client.post.return_value = mock_post_res

    provider = OpenRouterProvider(settings=settings, http_client=mock_client)
    with pytest.raises(AIAuthenticationError):
        await provider.generate_response(messages=[ChatMessage(role=MessageRole.USER, content="Hi")])


@pytest.mark.asyncio
async def test_provider_rate_limit_error():
    """Verify 429 response raises AIRateLimitError."""
    settings = Settings(OPENROUTER_API_KEY="sk-valid-key")
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_post_res = MagicMock()
    mock_post_res.status_code = 429
    mock_post_res.text = "Too Many Requests"
    mock_client.post.return_value = mock_post_res

    provider = OpenRouterProvider(settings=settings, http_client=mock_client)
    with pytest.raises(AIRateLimitError):
        await provider.generate_response(messages=[ChatMessage(role=MessageRole.USER, content="Hi")])


@pytest.mark.asyncio
async def test_provider_timeout_handling():
    """Verify httpx.TimeoutException maps cleanly to AITimeoutError."""
    settings = Settings(OPENROUTER_API_KEY="sk-valid-key")
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.TimeoutException("Timeout connecting")

    provider = OpenRouterProvider(settings=settings, http_client=mock_client)
    with pytest.raises(AITimeoutError):
        await provider.generate_response(messages=[ChatMessage(role=MessageRole.USER, content="Hi")])


@pytest.mark.asyncio
async def test_provider_malformed_response():
    """Verify malformed JSON choices array raises AIMalformedResponseError."""
    settings = Settings(OPENROUTER_API_KEY="sk-valid-key")
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.json.return_value = {"status": "ok"}  # Missing 'choices'
    mock_client.post.return_value = mock_post_res

    provider = OpenRouterProvider(settings=settings, http_client=mock_client)
    with pytest.raises(AIMalformedResponseError):
        await provider.generate_response(messages=[ChatMessage(role=MessageRole.USER, content="Hi")])


# =============================================================================
# 2. Tool Registry & Desktop Tools Tests
# =============================================================================

@pytest.mark.asyncio
async def test_tool_registry_registered_tools_accessible():
    """Verify registered tools can be discovered and schemas retrieved."""
    registry = create_default_tool_registry()
    names = registry.list_tool_names()
    assert "list_applications" in names
    assert "launch_application" in names
    assert "inspect_processes" in names
    assert "capture_screenshot" in names
    assert "desktop_capabilities" in names

    defs = registry.get_tool_definitions()
    assert len(defs) == 5
    launch_def = next(d for d in defs if d["function"]["name"] == "launch_application")
    assert "app_id" in launch_def["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_tool_registry_unknown_tool_rejected():
    """Verify attempts to invoke unknown tools or arbitrary commands are safely rejected."""
    registry = create_default_tool_registry()
    res = await registry.execute_tool(
        call_id="call_bad",
        tool_name="execute_powershell_script",
        arguments={"script": "dir"},
    )
    assert res.status == "rejected"
    assert res.error_code == "UNKNOWN_TOOL"
    assert res.verification_status == VerificationStatus.FAILED


@pytest.mark.asyncio
async def test_tool_registry_invalid_arguments_rejected():
    """Verify invalid tool arguments fail validation safely."""
    registry = create_default_tool_registry()
    res = await registry.execute_tool(
        call_id="call_bad_args",
        tool_name="inspect_processes",
        arguments={"limit": "not_a_number"},
    )
    # Pydantic fails validation and returns invalid_arguments status
    assert res.status == "invalid_arguments"
    assert res.error_code == "INVALID_ARGUMENTS"


@pytest.mark.asyncio
async def test_tool_registry_permission_denial():
    """Verify that disabled desktop automation halts tool execution immediately."""
    settings = Settings(DESKTOP_AUTOMATION_ENABLED=False)
    desktop_service = DesktopService(settings=settings)
    registry = create_default_tool_registry(desktop_service=desktop_service, settings=settings)

    res = await registry.execute_tool(
        call_id="call_perm_denied",
        tool_name="launch_application",
        arguments={"app_id": "notepad"},
    )
    assert res.status == "denied"
    assert res.error_code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_launch_application_unregistered_app_rejected():
    """Verify tool rejects applications not in allowlist without throwing unhandled exceptions."""
    registry = create_default_tool_registry()
    res = await registry.execute_tool(
        call_id="call_unapproved_app",
        tool_name="launch_application",
        arguments={"app_id": "malicious_app.exe"},
    )
    assert res.status == "denied"
    assert res.error_code == "PERMISSION_DENIED"
    assert "not in approved allowlist" in res.safe_error_message



# =============================================================================
# 3. Reasoning Service Tests
# =============================================================================

@pytest.mark.asyncio
async def test_reasoning_service_empty_message_validation():
    """Verify empty or whitespace user message is rejected."""
    service = ReasoningService()
    with pytest.raises(ValidationError):
        await service.chat("   ")


@pytest.mark.asyncio
async def test_reasoning_service_oversized_message_validation():
    """Verify user message exceeding MAX_USER_MESSAGE_CHARS is rejected."""
    service = ReasoningService()
    long_msg = "A" * (service.settings.MAX_USER_MESSAGE_CHARS + 10)
    with pytest.raises(ValidationError):
        await service.chat(long_msg)


@pytest.mark.asyncio
async def test_reasoning_service_conversational_response():
    """Verify reasoning service returns conversational response without tool execution."""
    mock_provider = AsyncMock()
    mock_provider.is_configured = MagicMock(return_value=True)

    mock_provider.generate_response.return_value = AssistantResponse(
        response_id="gen-test-1",
        conversation_id="test-conv",
        message="Hello! I am VENORA AI.",
        response_type=ResponseType.CONVERSATIONAL,
        tool_calls=[],
        created_at=datetime.now(timezone.utc),
    )

    service = ReasoningService(provider=mock_provider)
    resp = await service.chat("Hello there")

    assert resp.response_type == ResponseType.CONVERSATIONAL
    assert resp.message == "Hello! I am VENORA AI."
    assert resp.tool_results == []


@pytest.mark.asyncio
async def test_reasoning_service_tool_call_round_trip():
    """Verify reasoning service executes proposed tool and summarizes result in second round."""
    mock_provider = AsyncMock()
    mock_provider.is_configured = MagicMock(return_value=True)

    # Round 1: Model proposes list_applications

    round1_resp = AssistantResponse(
        response_id="gen-r1",
        conversation_id="conv-r1",
        message="",
        response_type=ResponseType.PROPOSED_TOOL_CALL,
        tool_calls=[
            ToolCall(
                call_id="call_list_apps_1",
                tool_name="list_applications",
                arguments={},
            )
        ],
        created_at=datetime.now(timezone.utc),
    )

    # Round 2: Model receives tool result and provides final summary
    round2_resp = AssistantResponse(
        response_id="gen-r2",
        conversation_id="conv-r1",
        message="I can open Notepad, Calculator, Paint, and CMD.",
        response_type=ResponseType.CONVERSATIONAL,
        tool_calls=[],
        created_at=datetime.now(timezone.utc),
    )

    mock_provider.generate_response.side_effect = [round1_resp, round2_resp]

    service = ReasoningService(provider=mock_provider)
    resp = await service.chat("What apps can you open?")

    assert resp.response_type == ResponseType.TOOL_RESULT
    assert "Notepad" in resp.message
    assert len(resp.tool_results) == 1
    assert resp.tool_results[0].tool_name == "list_applications"
    assert resp.tool_results[0].status == "success"


@pytest.mark.asyncio
async def test_reasoning_service_max_tool_rounds_bound():
    """Verify reasoning service strictly caps multi-round tool loops to MAX_TOOL_CALL_ROUNDS."""
    mock_provider = AsyncMock()
    mock_provider.is_configured = MagicMock(return_value=True)

    # Continually proposes list_applications in loop

    looping_resp = AssistantResponse(
        response_id="gen-loop",
        conversation_id="conv-loop",
        message="",
        response_type=ResponseType.PROPOSED_TOOL_CALL,
        tool_calls=[
            ToolCall(
                call_id="call_loop",
                tool_name="list_applications",
                arguments={},
            )
        ],
        created_at=datetime.now(timezone.utc),
    )
    mock_provider.generate_response.return_value = looping_resp

    settings = Settings(MAX_TOOL_CALL_ROUNDS=2)
    service = ReasoningService(provider=mock_provider, settings=settings)
    resp = await service.chat("Inspect everything repeatedly")

    assert resp.response_type == ResponseType.TOOL_RESULT
    assert "maximum allowed reasoning rounds" in resp.message
    assert len(resp.tool_results) == 2


@pytest.mark.asyncio
async def test_reasoning_prompt_injection_safety():
    """Verify system instructions enforce strict injection resistance and rules."""
    mock_provider = AsyncMock()
    mock_provider.is_configured.return_value = True

    service = ReasoningService(provider=mock_provider)
    assert "VENORA" in VENORA_SYSTEM_INSTRUCTIONS
    assert "Defense Against Adversarial Prompt Injection" in VENORA_SYSTEM_INSTRUCTIONS
    assert "CRITICAL SECURITY" in VENORA_SYSTEM_INSTRUCTIONS or "CORE OPERATIONAL PRINCIPLES" in VENORA_SYSTEM_INSTRUCTIONS


# =============================================================================
# 4. API Endpoint Integration Tests
# =============================================================================

def test_assistant_status_endpoint(client: TestClient):
    """Verify GET /api/v1/assistant/status returns safe diagnostic metadata."""
    response = client.get("/api/v1/assistant/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "openrouter"
    assert "model" in data
    assert "is_configured" in data
    assert data["tools_available_count"] >= 5
    assert "list_applications" in data["tools_registered"]
    # Never expose API keys or auth headers
    assert "key" not in data
    assert "api_key" not in data


def test_assistant_chat_endpoint_empty_message(client: TestClient):
    """Verify POST /api/v1/assistant/chat validates message presence."""
    response = client.post("/api/v1/assistant/chat", json={"message": "   "})
    assert response.status_code == 400


def test_assistant_chat_endpoint_unconfigured_provider(client: TestClient):
    """Verify unconfigured provider returns actionable status without 500 crash."""
    with patch.object(OpenRouterProvider, "is_configured", return_value=False):
        response = client.post(
            "/api/v1/assistant/chat",
            json={"message": "Open Notepad"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["response_type"] == "error"
        assert "OPENROUTER_API_KEY" in data["message"]


def test_assistant_chat_endpoint_successful_mocked_dialogue(client: TestClient):
    """Verify end-to-end conversational chat flow through FastAPI route using mock."""
    mock_resp = AssistantResponse(
        response_id="gen-api-1",
        conversation_id="conv-api-1",
        message="Hello! I am VENORA, ready to assist you.",
        response_type=ResponseType.CONVERSATIONAL,
        tool_calls=[],
        tool_results=[],
        requires_clarification=False,
        created_at=datetime.now(timezone.utc),
    )


    with patch.object(ReasoningService, "chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_resp
        response = client.post(
            "/api/v1/assistant/chat",
            json={"message": "Hello VENORA"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Hello! I am VENORA, ready to assist you."
        assert data["response_type"] == "conversational"
        assert data["conversation_id"] == "conv-api-1"
