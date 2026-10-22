"""Tests for health and readiness diagnostic endpoints."""

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database.session import get_db
from app.main import app


def test_health_endpoint(client: TestClient):
    """Test that health endpoint returns HTTP 200 with application metadata."""
    response = client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert "app_name" in data
    assert "version" in data
    assert "environment" in data


def test_readiness_endpoint_success(client: TestClient):
    """Test readiness endpoint when database is reachable."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"


def test_readiness_endpoint_db_failure(client: TestClient):
    """Test readiness endpoint returns 503 when database connection fails."""
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("Connection refused", params=None, orig=Exception("Simulated DB connection failure"))

    def broken_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    try:
        response = client.get("/api/v1/health/ready")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "disconnected"
    finally:
        app.dependency_overrides.clear()


def test_health_no_secrets_exposed(client: TestClient):
    """Test that health response does not leak internal DB paths or configuration secrets."""
    response = client.get("/api/v1/health")
    data = response.json()
    # Check that database URLs, password fields, or file paths are not exposed
    forbidden_keys = {"database_url", "db_url", "secret", "password", "token", "api_key"}
    assert not any(k in data for k in forbidden_keys)
