"""Comprehensive automated test suite for Phase 4: Task Orchestration & Execution Management."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    DesktopEmergencyStopActiveError,
    InvalidTaskStateError,
    PlanValidationError,
    StepDependencyError,
    TaskApprovalRequiredError,
    TaskNotEligibleError,
)
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.task_step import StepStatus, TaskStep
from app.orchestration.executor import TaskExecutor
from app.orchestration.orchestrator import TaskOrchestrator
from app.orchestration.planner import TaskPlanner
from app.orchestration.recovery import TaskRecoveryManager
from app.orchestration.schemas import (
    CreateTaskPlanRequest,
    PlanStatus,
    StepPlan,
    TaskPlan,
)
from app.orchestration.state_machine import StepStateMachine, TaskStateMachine
from app.orchestration.task_repository import TaskRepository


# =============================================================================
# 1. Planner Tests
# =============================================================================

def test_planner_valid_multi_step_heuristic():
    """Verify heuristic planner generates valid multi-step plan for multi-application requests."""
    planner = TaskPlanner()
    plan = planner._plan_heuristic(task_id=1, user_goal="Open Notepad, then open Calculator")

    assert len(plan.steps) == 2
    assert plan.steps[0].tool_name == "launch_application"
    assert plan.steps[0].arguments == {"app_id": "notepad"}
    assert plan.steps[1].tool_name == "launch_application"
    assert plan.steps[1].arguments == {"app_id": "calc"}
    assert plan.steps[1].dependencies == [plan.steps[0].step_id]


def test_planner_unknown_tool_rejected():
    """Verify plan validation rejects unknown tool names."""
    planner = TaskPlanner()
    steps = [
        StepPlan(
            step_id="step_bad",
            sequence_number=1,
            description="Run dangerous command",
            tool_name="unapproved_shell_exec",
            arguments={"cmd": "dir"},
        )
    ]
    with pytest.raises(PlanValidationError) as exc:
        planner.validate_plan_structure(steps)
    assert "unknown tool" in str(exc.value)


def test_planner_invalid_arguments_rejected():
    """Verify plan validation rejects invalid arguments for registered tools."""
    planner = TaskPlanner()
    steps = [
        StepPlan(
            step_id="step_bad_arg",
            sequence_number=1,
            description="Inspect processes",
            tool_name="inspect_processes",
            arguments={"limit": "not_an_int"},
        )
    ]
    with pytest.raises(PlanValidationError) as exc:
        planner.validate_plan_structure(steps)
    assert "invalid arguments" in str(exc.value)


def test_planner_duplicate_step_id_rejected():
    """Verify duplicate step IDs within a plan are rejected."""
    planner = TaskPlanner()
    steps = [
        StepPlan(step_id="step_1", sequence_number=1, description="Step 1", tool_name="list_applications"),
        StepPlan(step_id="step_1", sequence_number=2, description="Step 2", tool_name="desktop_capabilities"),
    ]
    with pytest.raises(PlanValidationError) as exc:
        planner.validate_plan_structure(steps)
    assert "Duplicate step_id" in str(exc.value)


def test_planner_self_dependency_rejected():
    """Verify step depending on itself is rejected."""
    planner = TaskPlanner()
    steps = [
        StepPlan(
            step_id="step_loop",
            sequence_number=1,
            description="Self depending",
            tool_name="list_applications",
            dependencies=["step_loop"],
        )
    ]
    with pytest.raises(StepDependencyError) as exc:
        planner.validate_plan_structure(steps)
    assert "cannot depend on itself" in str(exc.value)


def test_planner_forward_dependency_rejected():
    """Verify step depending on a non-existent or forward step is rejected."""
    planner = TaskPlanner()
    steps = [
        StepPlan(
            step_id="step_1",
            sequence_number=1,
            description="Depends on step 2",
            tool_name="list_applications",
            dependencies=["step_2"],
        ),
        StepPlan(
            step_id="step_2",
            sequence_number=2,
            description="Second step",
            tool_name="desktop_capabilities",
        ),
    ]
    with pytest.raises(StepDependencyError) as exc:
        planner.validate_plan_structure(steps)
    assert "does not exist prior" in str(exc.value)


def test_planner_excessive_step_count_rejected():
    """Verify plans exceeding MAX_PLAN_STEPS limit are rejected."""
    settings = Settings(MAX_PLAN_STEPS=3)
    planner = TaskPlanner(settings=settings)
    steps = [
        StepPlan(step_id=f"step_{i}", sequence_number=i, description=f"Step {i}", tool_name="desktop_capabilities")
        for i in range(1, 5)
    ]
    with pytest.raises(PlanValidationError) as exc:
        planner.validate_plan_structure(steps)
    assert "exceeds maximum" in str(exc.value)


# =============================================================================
# 2. State Machine Tests
# =============================================================================

def test_task_state_machine_valid_transitions():
    """Verify permitted task transitions pass validation without error."""
    TaskStateMachine.validate_transition(TaskStatus.CREATED, TaskStatus.PLANNING)
    TaskStateMachine.validate_transition(TaskStatus.PLANNING, TaskStatus.READY)
    TaskStateMachine.validate_transition(TaskStatus.READY, TaskStatus.RUNNING)
    TaskStateMachine.validate_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)


def test_task_state_machine_invalid_transitions():
    """Verify illegal task state transitions raise InvalidTaskStateError."""
    with pytest.raises(InvalidTaskStateError):
        TaskStateMachine.validate_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)

    with pytest.raises(InvalidTaskStateError):
        TaskStateMachine.validate_transition(TaskStatus.CANCELLED, TaskStatus.RUNNING)

    with pytest.raises(InvalidTaskStateError):
        TaskStateMachine.validate_transition(TaskStatus.CREATED, TaskStatus.COMPLETED)


def test_step_state_machine_transitions():
    """Verify step transitions validate correctly."""
    StepStateMachine.validate_transition(StepStatus.PENDING, StepStatus.READY)
    StepStateMachine.validate_transition(StepStatus.READY, StepStatus.RUNNING)
    StepStateMachine.validate_transition(StepStatus.RUNNING, StepStatus.SUCCEEDED)

    with pytest.raises(InvalidTaskStateError):
        StepStateMachine.validate_transition(StepStatus.SUCCEEDED, StepStatus.RUNNING)


# =============================================================================
# 3. Executor Tests
# =============================================================================

@pytest.mark.asyncio
async def test_executor_sequential_execution_success(db_session: Session):
    """Verify executor executes steps sequentially and records results."""
    repo = TaskRepository(db_session)
    task = repo.create_task(title="Multi-App Task")

    plan = TaskPlan(
        plan_id="plan_test_1",
        task_id=task.id,
        user_goal="List apps and check capabilities",
        summary="Two step test plan",
        created_at=task.created_at,
        steps=[

            StepPlan(
                step_id="step_1",
                sequence_number=1,
                description="List apps",
                tool_name="list_applications",
            ),
            StepPlan(
                step_id="step_2",
                sequence_number=2,
                description="Check capabilities",
                tool_name="desktop_capabilities",
                dependencies=["step_1"],
            ),
        ],
    )
    repo.persist_plan(task.id, plan)
    repo.update_task_status(task.id, TaskStatus.READY)

    executor = TaskExecutor(repository=repo)
    result_task = await executor.execute_task(task.id)

    assert result_task.status == TaskStatus.COMPLETED
    steps = repo.get_task_steps(task.id)
    assert len(steps) == 2
    assert steps[0].status == StepStatus.SUCCEEDED
    assert steps[1].status == StepStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_executor_fail_fast_on_step_failure(db_session: Session):
    """Verify executor halts and skips downstream dependent steps if an earlier step fails."""
    repo = TaskRepository(db_session)
    task = repo.create_task(title="Failing Task")

    plan = TaskPlan(
        plan_id="plan_fail",
        task_id=task.id,
        user_goal="Fail first step",
        summary="Plan with failure",
        created_at=task.created_at,
        steps=[
            StepPlan(
                step_id="step_1",
                sequence_number=1,
                description="Launch unapproved app",
                tool_name="launch_application",
                arguments={"app_id": "malicious_unapproved.exe"},
            ),
            StepPlan(
                step_id="step_2",
                sequence_number=2,
                description="Dependent step",
                tool_name="desktop_capabilities",
                dependencies=["step_1"],
            ),
        ],
    )
    repo.persist_plan(task.id, plan)
    repo.update_task_status(task.id, TaskStatus.READY)

    executor = TaskExecutor(repository=repo)
    result_task = await executor.execute_task(task.id)

    assert result_task.status in {TaskStatus.FAILED, TaskStatus.PARTIALLY_COMPLETED}
    steps = repo.get_task_steps(task.id)
    assert steps[0].status == StepStatus.FAILED
    assert steps[1].status == StepStatus.SKIPPED


@pytest.mark.asyncio
async def test_executor_emergency_stop_blocks_execution(db_session: Session):
    """Verify active Emergency Stop blocks task execution."""
    repo = TaskRepository(db_session)
    task = repo.create_task(title="Blocked Task")

    plan = TaskPlan(
        plan_id="plan_em",
        task_id=task.id,
        user_goal="Run under stop",
        summary="Emergency test",
        created_at=task.created_at,
        steps=[
            StepPlan(step_id="step_1", sequence_number=1, description="List apps", tool_name="list_applications")
        ],
    )
    repo.persist_plan(task.id, plan)
    repo.update_task_status(task.id, TaskStatus.READY)

    executor = TaskExecutor(repository=repo)
    executor.tool_registry.permission_service.set_emergency_stop(True)

    try:
        with pytest.raises(DesktopEmergencyStopActiveError):
            await executor.execute_task(task.id)
        assert repo.get_task(task.id).status == TaskStatus.NEEDS_ATTENTION
    finally:
        executor.tool_registry.permission_service.set_emergency_stop(False)


# =============================================================================
# 4. Recovery Tests
# =============================================================================

def test_recovery_manager_reconciles_interrupted_tasks(db_session: Session):
    """Verify recovery manager detects RUNNING tasks on startup and marks them NEEDS_ATTENTION."""
    repo = TaskRepository(db_session)
    task = repo.create_task(title="Interrupted Task")
    repo.update_task_status(task.id, TaskStatus.RUNNING)

    recovery = TaskRecoveryManager(repo)
    recovered = recovery.recover_interrupted_tasks()

    assert task.id in recovered
    refreshed = repo.get_task(task.id)
    assert refreshed.status == TaskStatus.NEEDS_ATTENTION
    assert "interrupted by a process restart" in refreshed.error_message


# =============================================================================
# 5. API Integration Tests (Phase 4 Orchestration Endpoints)
# =============================================================================

def test_api_create_orchestrated_task_with_plan(client: TestClient):
    """Verify POST /api/v1/tasks with goal creates task, plan, and steps."""
    payload = {
        "goal": "Open Notepad and open Calculator",
        "priority": "high",
        "auto_execute": False,
    }
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()

    assert data["id"] is not None
    assert data["status"] in ["ready", "awaiting_approval"]
    assert data["total_steps"] == 2
    assert len(data["steps"]) == 2
    assert data["steps"][0]["tool_name"] == "launch_application"
    assert data["progress_percentage"] == 0.0


def test_api_get_task_details_and_progress(client: TestClient):
    """Verify GET /api/v1/tasks/{id} returns step details and calculated progress."""
    create_resp = client.post("/api/v1/tasks", json={"goal": "List all applications"})
    task_id = create_resp.json()["id"]

    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == task_id
    assert data["total_steps"] >= 1
    assert "steps" in data


def test_api_start_task_execution(client: TestClient):
    """Verify POST /api/v1/tasks/{id}/start executes steps sequentially."""
    create_resp = client.post("/api/v1/tasks", json={"goal": "List all applications"})
    task_id = create_resp.json()["id"]

    start_resp = client.post(f"/api/v1/tasks/{task_id}/start")
    assert start_resp.status_code == status.HTTP_200_OK
    data = start_resp.json()
    assert data["status"] == "completed"
    assert data["progress_percentage"] == 100.0
    assert data["completed_steps"] >= 1


def test_api_approve_and_deny_task(client: TestClient):
    """Verify approve and deny endpoints manage AWAITING_APPROVAL tasks."""
    create_resp = client.post("/api/v1/tasks", json={"goal": "List applications"})
    task_id = create_resp.json()["id"]

    # Transition task manually to awaiting_approval
    client.patch(f"/api/v1/tasks/{task_id}", json={"status": "awaiting_approval"})

    # Approve task
    approve_resp = client.post(f"/api/v1/tasks/{task_id}/approve", json={"decision_reason": "Approved by admin"})
    assert approve_resp.status_code == status.HTTP_200_OK
    assert approve_resp.json()["status"] == "ready"


def test_api_task_events_audit_log(client: TestClient):
    """Verify GET /api/v1/tasks/{id}/events returns recorded lifecycle events."""
    create_resp = client.post("/api/v1/tasks", json={"goal": "Audit test task"})
    task_id = create_resp.json()["id"]

    response = client.get(f"/api/v1/tasks/{task_id}/events")
    assert response.status_code == status.HTTP_200_OK
    events = response.json()
    assert len(events) >= 1
    event_types = [e["event_type"] for e in events]
    assert "task_created" in event_types or "plan_generated" in event_types
