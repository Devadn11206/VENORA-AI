"""Task management API routes for VENORA AI."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.task import TaskPriority, TaskStatus
from app.schemas.task import (
    PaginatedTasksResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])


class CancelTaskRequest(BaseModel):
    """Optional request body when cancelling a task."""
    reason: Optional[str] = Field(default=None, max_length=500, description="Reason for cancellation")


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
    description="Creates a task record with PENDING status and records an execution log."
)
def create_task(
    task_in: TaskCreate,
    db: Session = Depends(get_db)
):
    service = TaskService(db)
    return service.create_task(task_in)


@router.get(
    "",
    response_model=PaginatedTasksResponse,
    summary="List tasks with pagination",
    description="Retrieves a paginated list of tasks, optionally filtered by status and priority."
)
def list_tasks(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: Optional[TaskStatus] = Query(default=None, description="Filter by task status"),
    priority: Optional[TaskPriority] = Query(default=None, description="Filter by task priority"),
    db: Session = Depends(get_db)
):
    service = TaskService(db)
    tasks, total, total_pages = service.list_tasks(
        page=page,
        page_size=page_size,
        status=status,
        priority=priority,
    )
    return PaginatedTasksResponse(
        items=tasks,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Retrieve task by ID",
    description="Fetches detailed task information by unique task ID."
)
def get_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    service = TaskService(db)
    return service.get_task_by_id(task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update permitted task fields",
    description="Updates permitted fields (title, description, priority, status) with state validation."
)
def update_task(
    task_id: int,
    task_in: TaskUpdate,
    db: Session = Depends(get_db)
):
    service = TaskService(db)
    return service.update_task(task_id, task_in)


@router.post(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    summary="Cancel a pending task",
    description="Cancels an eligible task that has not yet started execution."
)
def cancel_task(
    task_id: int,
    body: Optional[CancelTaskRequest] = None,
    db: Session = Depends(get_db)
):
    service = TaskService(db)
    reason = body.reason if body else None
    return service.cancel_task(task_id, reason=reason)
