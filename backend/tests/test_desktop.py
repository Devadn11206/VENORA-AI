"""Unit, integration, and safety tests for Phase 2 desktop automation subsystem."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import (
    DesktopEmergencyStopActiveError,
    DesktopPermissionDeniedError,
)
from app.desktop.application_launcher import ApplicationLauncherService
from app.desktop.capability import DesktopCapabilityService
from app.desktop.permissions import DesktopPermissionService
from app.desktop.schemas import (
    ActionStatus,
    DesktopActionRequest,
    DesktopActionType,
    KeyboardKeyRequest,
    KeyboardTypeRequest,
    MouseMoveRequest,
    VerificationStatus,
)
from app.desktop.service import DesktopService


# =============================================================================
# 1. Capability Detection Tests
# =============================================================================
def test_desktop_capabilities_detection():
    """Verify that desktop capabilities return structured, truthful environment data."""
    service = DesktopCapabilityService()
    caps = service.detect_capabilities()
    assert caps.os_name != ""
    assert isinstance(caps.is_windows, bool)
    assert isinstance(caps.screenshot_available, bool)
    assert isinstance(caps.mouse_keyboard_available, bool)
    assert "notepad" in caps.supported_applications
    assert not caps.input_automation_enabled  # Safe default: disabled


def test_capabilities_api_endpoint(client: TestClient):
    """Test GET /api/v1/desktop/capabilities."""
    response = client.get("/api/v1/desktop/capabilities")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "is_windows" in data
    assert "screenshot_available" in data
    assert "input_automation_enabled" in data
    assert data["input_automation_enabled"] is False


# =============================================================================
# 2. Permission and Allowlist Enforcement Tests
# =============================================================================
def test_permission_default_deny_unknown_action():
    """Verify default-deny behavior for unknown or unlisted action categories."""
    perm_service = DesktopPermissionService()
    with pytest.raises(DesktopPermissionDeniedError):
        perm_service.check_permission("desktop.arbitrary.command")


def test_permission_input_automation_disabled_by_default():
    """Verify that mouse/keyboard actions are blocked when input automation is disabled."""
    perm_service = DesktopPermissionService()
    with pytest.raises(DesktopPermissionDeniedError) as exc_info:
        perm_service.check_permission("desktop.input.mouse")
    assert "Input automation (mouse/keyboard) is disabled" in str(exc_info.value)


def test_application_allowlist_enforcement():
    """Verify that launching unapproved applications is blocked."""
    launcher = ApplicationLauncherService()
    with pytest.raises(DesktopPermissionDeniedError) as exc_info:
        launcher.launch_application(app_id="malicious_binary")
    assert "not in approved allowlist" in str(exc_info.value)


def test_list_applications_endpoint(client: TestClient):
    """Test GET /api/v1/desktop/applications returns whitelisted apps."""
    response = client.get("/api/v1/desktop/applications")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] >= 1
    app_ids = [app["app_id"] for app in data["applications"]]
    assert "notepad" in app_ids


def test_launch_unapproved_application_via_api(client: TestClient):
    """Test POST /api/v1/desktop/applications/{app_id}/launch with unapproved app yields 403."""
    response = client.post("/api/v1/desktop/applications/powershell/launch")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    data = response.json()
    assert data["error_type"] == "permission_denied"


# =============================================================================
# 3. Process Inspection Tests
# =============================================================================
def test_list_processes_api_endpoint(client: TestClient):
    """Test GET /api/v1/desktop/processes returns bounded process list without secrets."""
    response = client.get("/api/v1/desktop/processes?limit=10")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["processes"]) <= 10
    if len(data["processes"]) > 0:
        first = data["processes"][0]
        assert "pid" in first
        assert "name" in first
        assert "cmdline" not in first  # Secrets hygiene: commandline not exposed
        assert "environ" not in first


def test_get_process_not_found(client: TestClient):
    """Test GET /api/v1/desktop/processes/{pid} with invalid PID returns 404."""
    response = client.get("/api/v1/desktop/processes/99999999")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error_type"] == "process_not_found"


# =============================================================================
# 4. Screenshot Capture and Path Isolation Tests
# =============================================================================
def test_screenshot_capture_and_retrieval(client: TestClient, tmp_path):
    """Test capturing a screenshot and verifying the image can be retrieved."""
    # Test capturing via endpoint
    response = client.post("/api/v1/desktop/screenshots")
    if response.status_code == status.HTTP_201_CREATED:
        data = response.json()
        assert "screenshot_id" in data
        assert data["verification_status"] == "verified"
        assert data["file_size_bytes"] > 0

        # Retrieve image via endpoint
        get_resp = client.get(f"/api/v1/desktop/screenshots/{data['screenshot_id']}")
        assert get_resp.status_code == status.HTTP_200_OK
        assert get_resp.headers["content-type"] == "image/png"
    else:
        # In headless environments, verify handled with 501
        assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED


def test_screenshot_path_traversal_prevention(client: TestClient):
    """Verify that directory traversal attempts in screenshot retrieval return 404."""
    response = client.get("/api/v1/desktop/screenshots/../../etc/passwd")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    response2 = client.get("/api/v1/desktop/screenshots/snap_invalid_token")
    assert response2.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# 5. Mouse and Keyboard Input Safety Tests
# =============================================================================
def test_mouse_out_of_bounds_validation():
    """Verify coordinates outside screen resolution are rejected."""
    settings = Settings(DESKTOP_INPUT_AUTOMATION_ENABLED=True)
    service = DesktopService(settings=settings)

    # Dispatch out-of-bounds mouse move action
    req = DesktopActionRequest(
        action_type=DesktopActionType.MOVE_MOUSE,
        parameters={"x": 999999, "y": 999999}
    )
    res = service.execute_action(req)
    assert res.status == ActionStatus.FAILED
    assert res.error_code == "EXECUTION_FAILED"
    assert "less than or equal" in res.safe_error_message or "exceed" in res.safe_error_message


def test_keyboard_unapproved_key_rejected():
    """Verify unapproved key names are rejected by permission service."""
    settings = Settings(DESKTOP_INPUT_AUTOMATION_ENABLED=True)
    service = DesktopService(settings=settings)

    req = DesktopActionRequest(
        action_type=DesktopActionType.PRESS_KEY,
        parameters={"key": "unapproved_super_key"}
    )
    res = service.execute_action(req)
    assert res.status == ActionStatus.BLOCKED
    assert res.error_code == "PERMISSION_DENIED"


def test_keyboard_text_length_limit():
    """Verify typing text exceeding MAX_TYPE_TEXT_LENGTH is rejected."""
    settings = Settings(DESKTOP_INPUT_AUTOMATION_ENABLED=True, MAX_TYPE_TEXT_LENGTH=50)
    service = DesktopService(settings=settings)

    long_text = "A" * 100
    req = DesktopActionRequest(
        action_type=DesktopActionType.TYPE_TEXT,
        parameters={"text": long_text}
    )
    res = service.execute_action(req)
    assert res.status == ActionStatus.FAILED
    assert "exceeds allowed limit" in res.safe_error_message


# =============================================================================
# 6. Emergency Stop Tests
# =============================================================================
def test_emergency_stop_toggle_and_action_blocking(client: TestClient):
    """Test activating emergency stop blocks input actions and reporting."""
    # Activate emergency stop
    stop_resp = client.post("/api/v1/desktop/emergency-stop?active=true")
    assert stop_resp.status_code == status.HTTP_200_OK
    assert stop_resp.json()["emergency_stop_active"] is True

    # Attempt action while emergency stop is active
    action_req = {
        "action_type": "move_mouse",
        "parameters": {"x": 100, "y": 100}
    }
    action_resp = client.post("/api/v1/desktop/actions", json=action_req)
    assert action_resp.status_code == status.HTTP_200_OK
    action_data = action_resp.json()
    assert action_data["status"] == "blocked"
    assert "Emergency stop" in action_data["result_summary"]

    # Reset emergency stop
    reset_resp = client.post("/api/v1/desktop/emergency-stop?active=false")
    assert reset_resp.status_code == status.HTTP_200_OK
    assert reset_resp.json()["emergency_stop_active"] is False


# =============================================================================
# 7. Mocked Application Launch Test
# =============================================================================
def test_mocked_safe_application_launch():
    """Test application launch lifecycle using mock subprocess."""
    launcher = ApplicationLauncherService()

    mock_proc = MagicMock()
    mock_proc.pid = 4321
    mock_proc.poll.return_value = None

    with patch("subprocess.Popen", return_value=mock_proc):
        with patch("psutil.pid_exists", return_value=True):
            res = launcher.launch_application(app_id="notepad")
            assert res.pid == 4321
            assert res.status == ActionStatus.COMPLETED
            assert res.verification_status == VerificationStatus.VERIFIED
