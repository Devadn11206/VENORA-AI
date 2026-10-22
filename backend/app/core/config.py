"""Centralized configuration management for VENORA AI using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable loading and validation."""

    # Application Metadata
    APP_NAME: str = Field(default="VENORA AI", description="Application name")
    APP_VERSION: str = Field(default="0.3.0", description="Application semantic version")
    ENVIRONMENT: str = Field(default="development", description="Execution environment (development, testing, production)")
    DEBUG: bool = Field(default=False, description="Debug mode flag")

    # Networking & API Server
    HOST: str = Field(default="127.0.0.1", description="Host address to bind the server")
    PORT: int = Field(default=8000, ge=1024, le=65535, description="Port number to bind the server")
    API_V1_PREFIX: str = Field(default="/api/v1", description="URL prefix for version 1 API endpoints")

    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./data/venora.db",
        description="Database connection URL"
    )

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Standard logging level")
    LOG_DIR: str = Field(default="./logs", description="Directory where log files are stored")
    LOG_FILE_NAME: str = Field(default="venora.log", description="Primary application log file name")
    LOG_MAX_BYTES: int = Field(default=10 * 1024 * 1024, description="Maximum log file size before rotation (bytes)")
    LOG_BACKUP_COUNT: int = Field(default=5, description="Number of rotated log backups to retain")

    # Security & CORS
    CORS_ORIGINS: Union[List[str], str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        description="Allowed CORS origins"
    )
    MAX_REQUEST_SIZE_BYTES: int = Field(
        default=1 * 1024 * 1024,  # 1 MB
        description="Conservative maximum request payload size in bytes"
    )

    # =========================================================================
    # Phase 2: Desktop Automation Configuration
    # =========================================================================
    DESKTOP_AUTOMATION_ENABLED: bool = Field(
        default=True,
        description="Master switch for desktop observation & automation subsystem"
    )
    DESKTOP_INPUT_AUTOMATION_ENABLED: bool = Field(
        default=False,
        description="Explicit gate for mouse and keyboard simulation (disabled by default for safety)"
    )
    DESKTOP_EMERGENCY_STOP_ACTIVE: bool = Field(
        default=False,
        description="Emergency stop flag: when active, all input actions are blocked"
    )

    # Approved Application Allowlist mapping app_id -> executable command/path
    DESKTOP_APPROVED_APPLICATIONS: Dict[str, str] = Field(
        default={
            "notepad": "notepad.exe",
            "calc": "calc.exe",
            "explorer": "explorer.exe",
            "cmd": "cmd.exe",
        },
        description="Whitelist of permitted application identifiers and their system executables"
    )

    # Screenshot storage & restrictions
    SCREENSHOT_DIR: str = Field(
        default="./data/screenshots",
        description="Directory for local task-scoped desktop screenshots"
    )
    MAX_SCREENSHOT_BYTES: int = Field(
        default=5 * 1024 * 1024,  # 5 MB
        description="Maximum permissible screenshot file size"
    )

    # Bounded execution timeouts (seconds)
    ACTION_TIMEOUT_SECONDS: float = Field(
        default=10.0,
        description="Default timeout limit for desktop actions in seconds"
    )
    LAUNCH_TIMEOUT_SECONDS: float = Field(
        default=5.0,
        description="Maximum seconds to wait for launched application process confirmation"
    )

    # Mouse & Keyboard safety bounds
    MAX_TYPE_TEXT_LENGTH: int = Field(
        default=250,
        description="Maximum character length allowed per typed text action"
    )

    # =========================================================================
    # Phase 3: AI Reasoning & Tool Calling Configuration
    # =========================================================================
    OPENROUTER_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenRouter API key for remote LLM inference (never hardcode in code or git)"
    )
    VENORA_AI_MODEL: str = Field(
        default="anthropic/claude-3.5-sonnet",
        description="Configured AI reasoning model"
    )
    VENORA_AI_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API endpoint base URL"
    )
    VENORA_AI_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        description="Timeout for AI provider inference calls"
    )
    VENORA_AI_MAX_RETRIES: int = Field(
        default=2,
        description="Maximum retry attempts on transient network/provider errors"
    )
    MAX_TOOL_CALL_ROUNDS: int = Field(
        default=3,
        description="Maximum sequential tool-calling rounds per user turn to prevent infinite loops"
    )
    MAX_USER_MESSAGE_CHARS: int = Field(
        default=4000,
        description="Maximum permitted character length for user input messages"
    )

    # =========================================================================
    # Phase 4: Task Orchestration & Execution Limits
    # =========================================================================
    MAX_PLAN_STEPS: int = Field(
        default=10,
        description="Maximum number of steps permitted in a structured task plan"
    )
    MAX_TASK_DURATION_SECONDS: float = Field(
        default=300.0,  # 5 minutes
        description="Maximum wall-clock execution duration for an orchestrated task"
    )
    MAX_PLANNING_ATTEMPTS: int = Field(
        default=3,
        description="Maximum plan generation attempts permitted per user task"
    )
    STEP_DEFAULT_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        description="Default execution timeout per task step"
    )

    # =========================================================================
    # Phase 5: File Intelligence & Document Understanding Configuration
    # =========================================================================
    ALLOWED_DOCUMENT_DIRS: List[str] = Field(
        default=[],
        description="Explicit allowlist of absolute directory paths authorized for document discovery and indexing"
    )
    DOCUMENT_MAX_FILE_BYTES: int = Field(
        default=25 * 1024 * 1024,  # 25 MB
        description="Maximum allowed document file size in bytes"
    )
    DOCUMENT_MAX_FILES_PER_SCAN: int = Field(
        default=500,
        description="Maximum number of files scanned in a single directory pass"
    )
    DOCUMENT_MAX_PDF_PAGES: int = Field(
        default=500,
        description="Maximum number of PDF pages extracted per document"
    )
    DOCUMENT_MAX_CHUNK_CHARS: int = Field(
        default=2000,
        description="Maximum character length of each chunk for retrieval and embedding"
    )
    DOCUMENT_CHUNK_OVERLAP_CHARS: int = Field(
        default=200,
        description="Overlap character length between consecutive text chunks"
    )
    DOCUMENT_MAX_EXTRACTION_SECONDS: float = Field(
        default=60.0,
        description="Maximum time in seconds allowed for a single document extraction pass"
    )
    DOCUMENT_MAX_CSV_ROWS: int = Field(
        default=5000,
        description="Maximum rows processed from tabular CSV/XLSX files"
    )
    DOCUMENT_MAX_JSON_DEPTH: int = Field(
        default=10,
        description="Maximum allowed nesting depth for JSON document parsing"
    )
    DOCUMENT_EXPORT_DIR: str = Field(
        default="./data/exports",
        description="Directory for safe exported document analysis files"
    )


    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse comma-separated string into a list of trimmed origins."""
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    @field_validator("ALLOWED_DOCUMENT_DIRS", mode="before")
    @classmethod
    def assemble_allowed_dirs(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse comma-separated or semicolon-separated directory paths."""
        if isinstance(v, str):
            delimiter = ";" if ";" in v else ","
            return [i.strip() for i in v.split(delimiter) if i.strip()]
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level against standard names."""
        valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        upper_v = v.strip().upper()
        if upper_v not in valid_levels:
            raise ValueError(f"Invalid LOG_LEVEL '{v}'. Must be one of {valid_levels}")
        return upper_v

    @property
    def is_production(self) -> bool:
        """Check if current environment is production."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def resolved_log_dir(self) -> Path:
        """Return the absolute path of the log directory."""
        return Path(self.LOG_DIR).resolve()

    @property
    def resolved_screenshot_dir(self) -> Path:
        """Return the absolute path of the screenshots directory."""
        path = Path(self.SCREENSHOT_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def resolved_export_dir(self) -> Path:
        """Return the absolute path of the exports directory."""
        path = Path(self.DOCUMENT_EXPORT_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
