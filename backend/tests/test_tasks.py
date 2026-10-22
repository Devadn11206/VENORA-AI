"""Tests for Task service and API endpoints."""

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.task import Task, TaskPriority, TaskStatus


def test_create_task_success(client: TestClient):
    """Test valid task creation via POST /api/v1/tasks."""
    payload = {
        "title": "Build File Watcher",
        "description": "Monitor system file events for memory ingest",
        "priority": "high"
    }
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["id"] is not None
    assert data["title"] == "Build File Watcher"
    assert data["description"] == "Monitor system file events for memory ingest"
    assert data["priority"] == "high"
    assert data["status"] == "pending"
    assert data["created_at"] is not None


def test_create_task_validation_error(client: TestClient):
    """Test that creating a task with invalid/empty fields yields 422."""
    # Empty title
    response = client.post("/api/v1/tasks", json={"title": ""})
    assert response.status_code == getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)

    # Invalid priority enum
    response = client.post("/api/v1/tasks", json={"title": "Valid", "priority": "extreme"})
    assert response.status_code == getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)


def test_get_task_by_id_success(client: TestClient):
    """Test retrieving an existing task by ID."""
    create_resp = client.post("/api/v1/tasks", json={"title": "Fetchable Task"})
    task_id = create_resp.json()["id"]

    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == task_id
    assert response.json()["title"] == "Fetchable Task"


def test_get_task_not_found(client: TestClient):
    """Test that fetching a nonexistent task ID returns 404."""
    response = client.get("/api/v1/tasks/99999")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error_type"] == "not_found"


def test_list_tasks_pagination(client: TestClient):
    """Test listing tasks with pagination and total count."""
    for i in range(15):
        client.post("/api/v1/tasks", json={"title": f"Task Batch {i+1}"})

    # Page 1, page_size 10
    resp_p1 = client.get("/api/v1/tasks?page=1&page_size=10")
    assert resp_p1.status_code == status.HTTP_200_OK
    data_p1 = resp_p1.json()
    assert data_p1["total"] == 15
    assert data_p1["page"] == 1
    assert data_p1["page_size"] == 10
    assert data_p1["total_pages"] == 2
    assert len(data_p1["items"]) == 10

    # Page 2, page_size 10
    resp_p2 = client.get("/api/v1/tasks?page=2&page_size=10")
    assert resp_p2.status_code == status.HTTP_200_OK
    data_p2 = resp_p2.json()
    assert len(data_p2["items"]) == 5


def test_update_task_fields(client: TestClient):
    """Test updating permitted task fields."""
    create_resp = client.post("/api/v1/tasks", json={"title": "Old Title", "priority": "low"})
    task_id = create_resp.json()["id"]

    update_payload = {
        "title": "New Title",
        "priority": "urgent",
        "description": "Updated details"
    }
    response = client.patch(f"/api/v1/tasks/{task_id}", json=update_payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["title"] == "New Title"
    assert data["priority"] == "urgent"
    assert data["description"] == "Updated details"


def test_terminal_task_cannot_be_updated(client: TestClient, db_session: Session):
    """Test that terminal tasks cannot be updated or accidentally reopened."""
    create_resp = client.post("/api/v1/tasks", json={"title": "Terminal Task"})
    task_id = create_resp.json()["id"]

    # Transition to completed
    client.patch(f"/api/v1/tasks/{task_id}", json={"status": "completed"})

    # Attempt to update completed task
    attempt_resp = client.patch(f"/api/v1/tasks/{task_id}", json={"title": "Reopened Title"})
    assert attempt_resp.status_code == status.HTTP_400_BAD_REQUEST
    data = attempt_resp.json()
    assert data["error_type"] == "invalid_state"


def test_cancel_pending_task(client: TestClient):
    """Test cancelling an eligible pending task."""
    create_resp = client.post("/api/v1/tasks", json={"title": "To Be Cancelled"})
    task_id = create_resp.json()["id"]

    cancel_resp = client.post(f"/api/v1/tasks/{task_id}/cancel", json={"reason": "User requested abort"})
    assert cancel_resp.status_code == status.HTTP_200_OK
    data = cancel_resp.json()
    assert data["status"] == "cancelled"
    assert data["completed_at"] is not None


def test_cancel_non_eligible_task_rejected(client: TestClient):
    """Test that completed or running tasks cannot be cancelled via pending cancellation endpoint."""
    create_resp = client.post("/api/v1/tasks", json={"title": "Running Task"})
    task_id = create_resp.json()["id"]

    # Move to running
    client.patch(f"/api/v1/tasks/{task_id}", json={"status": "running"})

    # Attempt cancel
    cancel_resp = client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert cancel_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert cancel_resp.json()["error_type"] == "invalid_state"
