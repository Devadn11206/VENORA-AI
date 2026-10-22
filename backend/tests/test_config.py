"""Tests for configuration parsing, validation, and security safeguards."""

import pytest
from pydantic import ValidationError
from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import Settings


def test_settings_safe_defaults():
    """Verify that settings default to safe, local execution values."""
    settings = Settings()
    assert settings.APP_NAME == "VENORA AI"
    assert settings.HOST == "127.0.0.1"
    assert settings.PORT == 8000
    assert "sqlite" in settings.DATABASE_URL
    assert not settings.is_production
    assert "http://localhost:3000" in settings.CORS_ORIGINS


def test_settings_cors_comma_separated_parsing():
    """Verify that comma-separated CORS_ORIGINS string is cleanly parsed."""
    settings = Settings(CORS_ORIGINS="http://localhost:3000, http://127.0.0.1:8080")
    assert "http://localhost:3000" in settings.CORS_ORIGINS
    assert "http://127.0.0.1:8080" in settings.CORS_ORIGINS
    assert len(settings.CORS_ORIGINS) == 2


def test_settings_invalid_log_level_rejected():
    """Verify that invalid log level triggers a validation error."""
    with pytest.raises(ValidationError):
        Settings(LOG_LEVEL="INVALID_LEVEL")


def test_settings_invalid_port_rejected():
    """Verify that out-of-range ports are rejected."""
    with pytest.raises(ValidationError):
        Settings(PORT=999999)


def test_request_size_limit_middleware(client: TestClient):
    """Test that requests exceeding MAX_REQUEST_SIZE_BYTES are rejected with 413."""
    # Send a payload with content-length header exceeding limit (1MB default limit)
    oversized_headers = {"content-length": "2000000"}  # 2MB header
    response = client.post("/api/v1/tasks", json={"title": "Oversized"}, headers=oversized_headers)
    assert response.status_code == getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413)
    data = response.json()
    assert data["error_type"] == "payload_too_large"
