"""Main FastAPI application module for VENORA AI."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes.desktop import router as desktop_router
from app.api.routes.health import router as health_router
from app.api.routes.tasks import router as tasks_router
from app.core.config import Settings, get_settings
from app.core.errors import (
    DesktopApplicationLaunchError,
    DesktopCapabilityUnavailableError,
    DesktopEmergencyStopActiveError,
    DesktopPermissionDeniedError,
    InvalidTaskStateError,
    ProcessNotFoundError,
    ScreenshotNotFoundError,
    TaskNotFoundError,
    VenoraError,
)
from app.core.logging import get_logger, setup_logging
from app.database.init_db import init_db

settings = get_settings()
logger = setup_logging(settings)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Conservative request body size limiter to protect against oversized payloads."""

    def __init__(self, app, max_bytes: int):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    return JSONResponse(
                        status_code=getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413),
                        content={"detail": "Request payload exceeds size limit", "error_type": "payload_too_large"}
                    )
            except ValueError:
                pass
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle management: startup and shutdown."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")
    logger.info(f"Binding configuration: {settings.HOST}:{settings.PORT}")
    try:
        init_db()
        logger.info("Database schema validated and ready.")
    except Exception as exc:
        logger.error(f"Database initialization failed during startup: {exc}", exc_info=True)

    yield

    logger.info(f"Shutting down {settings.APP_NAME}...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="VENORA AI",
        description="Virtual Environment for Neural Operations, Reasoning & Assistance - Core Backend API",
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Request size limit middleware
    application.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.MAX_REQUEST_SIZE_BYTES)

    # Restrict CORS to configured development origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Exception Handlers
    @application.exception_handler(TaskNotFoundError)
    async def task_not_found_handler(request: Request, exc: TaskNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message, "error_type": "not_found", "details": exc.details}
        )

    @application.exception_handler(ProcessNotFoundError)
    async def process_not_found_handler(request: Request, exc: ProcessNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message, "error_type": "process_not_found", "details": exc.details}
        )

    @application.exception_handler(ScreenshotNotFoundError)
    async def screenshot_not_found_handler(request: Request, exc: ScreenshotNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message, "error_type": "screenshot_not_found", "details": exc.details}
        )

    @application.exception_handler(InvalidTaskStateError)
    async def invalid_task_state_handler(request: Request, exc: InvalidTaskStateError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message, "error_type": "invalid_state", "details": exc.details}
        )

    @application.exception_handler(DesktopPermissionDeniedError)
    async def desktop_permission_denied_handler(request: Request, exc: DesktopPermissionDeniedError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message, "error_type": "permission_denied", "details": exc.details}
        )

    @application.exception_handler(DesktopEmergencyStopActiveError)
    async def desktop_emergency_stop_handler(request: Request, exc: DesktopEmergencyStopActiveError):
        return JSONResponse(
            status_code=status.HTTP_423_LOCKED,
            content={"detail": exc.message, "error_type": "emergency_stop_active", "details": exc.details}
        )

    @application.exception_handler(DesktopCapabilityUnavailableError)
    async def desktop_capability_unavailable_handler(request: Request, exc: DesktopCapabilityUnavailableError):
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content={"detail": exc.message, "error_type": "capability_unavailable", "details": exc.details}
        )

    @application.exception_handler(DesktopApplicationLaunchError)
    async def desktop_application_launch_handler(request: Request, exc: DesktopApplicationLaunchError):
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": exc.message, "error_type": "application_launch_failed", "details": exc.details}
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            content={"detail": exc.errors(), "error_type": "validation_error"}
        )

    @application.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
        # Never expose internal stack traces or secrets to the client
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected internal server error occurred.", "error_type": "internal_server_error"}
        )

    # Include Versioned Routers
    application.include_router(health_router, prefix=settings.API_V1_PREFIX)
    application.include_router(tasks_router, prefix=settings.API_V1_PREFIX)
    application.include_router(desktop_router, prefix=settings.API_V1_PREFIX)

    return application


app = create_app()
