"""Assistant chat and AI reasoning status API endpoints."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.reasoning_service import ReasoningService
from app.ai.schemas import AssistantResponse, AssistantStatusResponse, ChatRequest
from app.core.config import Settings, get_settings
from app.core.errors import (
    AIAuthenticationError,
    AIMalformedResponseError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    ConfigurationError,
    ValidationError as VenoraValidationError,
)
from app.database.session import get_db

logger = logging.getLogger("venora.api.assistant")

router = APIRouter(prefix="/assistant", tags=["Assistant"])


def get_reasoning_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReasoningService:
    """Dependency provider injecting database session and settings into ReasoningService."""
    return ReasoningService(db=db, settings=settings)


@router.post(
    "/chat",
    response_model=AssistantResponse,
    status_code=status.HTTP_200_OK,
    summary="Process conversational interaction or structured tool calling",
    description="Send user message to VENORA AI reasoning engine. Coordinates multi-round tool execution and truthfulness validation.",
)
async def assistant_chat(
    payload: ChatRequest,
    service: ReasoningService = Depends(get_reasoning_service),
) -> AssistantResponse:
    """Handle conversational instruction and tool orchestration."""
    try:
        return await service.chat(
            message=payload.message,
            conversation_id=payload.conversation_id,
        )
    except VenoraValidationError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except AIAuthenticationError as auth_err:
        logger.error(f"Authentication failure with AI provider: {auth_err}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider authentication failure. Please check provider credentials.",
        )
    except AIRateLimitError as rate_err:
        logger.warning(f"Rate limit exceeded: {rate_err}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI provider rate limit reached. Please retry your request shortly.",
        )
    except AITimeoutError as to_err:
        logger.error(f"AI provider timeout: {to_err}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI provider request timed out. Please try again.",
        )
    except ConfigurationError as cfg_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(cfg_err),
        )
    except AIProviderError as prov_err:
        logger.error(f"AI Provider error: {prov_err}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI reasoning provider encountered an upstream error.",
        )
    except Exception as exc:
        logger.error(f"Unexpected error in assistant chat endpoint: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the assistant request.",
        )


@router.get(
    "/status",
    response_model=AssistantStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check AI reasoning subsystem status",
    description="Check whether AI provider is configured and inspect registered tools without revealing sensitive keys.",
)
async def assistant_status(
    service: ReasoningService = Depends(get_reasoning_service),
    settings: Settings = Depends(get_settings),
) -> AssistantStatusResponse:
    """Report readiness, active provider, configured model, and registered tools."""
    return AssistantStatusResponse(
        provider="openrouter",
        model=settings.VENORA_AI_MODEL,
        is_configured=service.provider.is_configured(),
        tools_available_count=len(service.tools.list_tool_names()),
        tools_registered=service.tools.list_tool_names(),
        max_tool_rounds=settings.MAX_TOOL_CALL_ROUNDS,
    )
