"""Centralized configuration management for VENORA AI using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable loading and validation."""

    # Application Metadata
    APP_NAME: str = Field(default="VENORA AI", description="Application name")
    APP_VERSION: str = Field(default="0.1.0", description="Application semantic version")
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

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse comma-separated string into a list of trimmed origins."""
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
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
