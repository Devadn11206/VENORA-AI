"""Task management and orchestration API routes for VENORA AI."""

from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import (
    DesktopEmergencyStopActiveError,
    InvalidTaskStateError,
    PlanValidationError,
    StepDependencyError,
    TaskApprovalRequiredError,
    TaskNotEligibleError,
    TaskNotFoundError,
    TaskTimeoutError,
)
from app.database.session import get_db
from app.models.task import TaskPriority, TaskStatus
from app.orchestration import (
    CreateTaskPlanRequest,
    OrchestratedTaskResponse,
    TaskApprovalRequest,
    TaskEventResponse,
    TaskOrchestrator,
)
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
    response_model=Union[OrchestratedTaskResponse, TaskResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task or structured task plan",
    description="Creates a task record, generates a structured execution plan, and optionally auto-executes.",
)

async def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
):
    # If explicit goal is provided or auto_execute is True, use Phase 4 planner
    if payload.goal or payload.auto_execute:
        orchestrator = TaskOrchestrator(db)
        goal_text = (payload.goal or payload.description or payload.title or "").strip()
        if not goal_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'goal', 'title', or 'description' must be provided.",
            )
        try:
            req = CreateTaskPlanRequest(
                goal=goal_text,
                priority=payload.priority,
                auto_execute=payload.auto_execute,
            )
            return await orchestrator.create_and_plan_task(req)
        except PlanValidationError as pve:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(pve))
        except StepDependencyError as sde:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(sde))

    # Traditional Phase 1 / Phase 2 task creation preserves PENDING status
    service = TaskService(db)
    return service.create_task(payload)



@router.get(
    "",
    response_model=PaginatedTasksResponse,
    summary="List tasks with pagination",
    description="Retrieves a paginated list of tasks, optionally filtered by status and priority.",
)
def list_tasks(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: Optional[TaskStatus] = Query(default=None, description="Filter by task status"),
    priority: Optional[TaskPriority] = Query(default=None, description="Filter by task priority"),
    db: Session = Depends(get_db),
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
        total_pages=total_pages,
    )


@router.get(
    "/{task_id}",
    response_model=OrchestratedTaskResponse,
    summary="Retrieve task details and step progress by ID",
    description="Fetches detailed task information, planned steps, execution status, and progress metrics.",
)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    orchestrator = TaskOrchestrator(db)
    return orchestrator.get_task_details(task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update permitted task fields",
    description="Updates permitted fields (title, description, priority, status) with state validation.",
)
def update_task(
    task_id: int,
    task_in: TaskUpdate,
    db: Session = Depends(get_db),
):
    service = TaskService(db)
    return service.update_task(task_id, task_in)


@router.post(
    "/{task_id}/start",
    response_model=OrchestratedTaskResponse,
    summary="Start task execution",
    description="Validates state, approvals, and permissions, then executes eligible steps sequentially.",
)
async def start_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    orchestrator = TaskOrchestrator(db)
    try:
        return await orchestrator.start_task(task_id)
    except TaskApprovalRequiredError as are:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(are))
    except TaskNotEligibleError as nee:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(nee))
    except DesktopEmergencyStopActiveError as ese:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(ese))


@router.post(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    summary="Cancel a task",
    description="Cancels an active or queued task and marks pending steps cancelled.",
)
def cancel_task(
    task_id: int,
    body: Optional[CancelTaskRequest] = None,
    db: Session = Depends(get_db),
):
    orchestrator = TaskOrchestrator(db)
    reason = body.reason if body else None
    task = orchestrator.repo.get_task(task_id)

    # If task cannot be cancelled, raise 400 InvalidTaskStateError
    if not task.can_be_cancelled():
        raise InvalidTaskStateError(
            f"Task {task_id} with status '{task.status.value}' cannot be cancelled.",
            current_status=task.status.value,
            target_status=TaskStatus.CANCELLED.value,
        )

    # For legacy PENDING tasks without steps, invoke TaskService for compatibility
    if task.status == TaskStatus.PENDING and not orchestrator.repo.get_task_steps(task_id):
        service = TaskService(db)
        return service.cancel_task(task_id, reason=reason)

    try:
        return orchestrator.cancel_task(task_id, reason=reason)
    except InvalidTaskStateError as itse:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(itse))




@router.post(
    "/{task_id}/approve",
    response_model=OrchestratedTaskResponse,
    summary="Approve a task requiring confirmation",
    description="Explicitly approves a task in AWAITING_APPROVAL state, transitioning it to READY.",
)
def approve_task(
    task_id: int,
    body: Optional[TaskApprovalRequest] = None,
    db: Session = Depends(get_db),
):
    orchestrator = TaskOrchestrator(db)
    reason = body.decision_reason if body else None
    try:
        return orchestrator.approve_task(task_id, reason=reason)
    except InvalidTaskStateError as itse:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(itse))


@router.post(
    "/{task_id}/deny",
    response_model=OrchestratedTaskResponse,
    summary="Deny a task requiring approval",
    description="Denies approval, preventing execution and cancelling pending steps.",
)
def deny_task(
    task_id: int,
    body: Optional[TaskApprovalRequest] = None,
    db: Session = Depends(get_db),
):
    orchestrator = TaskOrchestrator(db)
    reason = body.decision_reason if body else None
    try:
        return orchestrator.deny_task(task_id, reason=reason)
    except InvalidTaskStateError as itse:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(itse))


@router.get(
    "/{task_id}/events",
    response_model=List[TaskEventResponse],
    summary="Retrieve task lifecycle events",
    description="Returns ordered execution audit events for the task.",
)
def get_task_events(
    task_id: int,
    limit: int = Query(default=50, ge=1, le=100, description="Max event logs"),
    db: Session = Depends(get_db),
):
    orchestrator = TaskOrchestrator(db)
    return orchestrator.list_task_events(task_id=task_id, limit=limit)
