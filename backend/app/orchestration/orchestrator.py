"""Task orchestrator coordinating planning, approval, sequential execution, and progress calculation."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.ai.openrouter_provider import OpenRouterProvider
from app.ai.provider import BaseAIProvider
from app.ai.tools import create_default_tool_registry
from app.ai.tools.registry import ToolRegistry
from app.core.config import Settings, get_settings
from app.core.errors import (
    DesktopEmergencyStopActiveError,
    InvalidTaskStateError,
    TaskApprovalRequiredError,
    TaskNotEligibleError,
)
from app.desktop.schemas import VerificationStatus
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.task_step import TaskStep, StepStatus
from app.orchestration.executor import TaskExecutor
from app.orchestration.planner import TaskPlanner
from app.orchestration.recovery import TaskRecoveryManager
from app.orchestration.schemas import (
    CreateTaskPlanRequest,
    OrchestratedTaskResponse,
    StepResponse,
    TaskEventResponse,
    TaskPlan,
)
from app.orchestration.state_machine import TaskStateMachine
from app.orchestration.task_repository import TaskRepository

logger = logging.getLogger("venora.orchestration.service")


class TaskOrchestrator:
    """Coordinates task creation, planning, approval workflow, execution, and progress metrics."""

    def __init__(
        self,
        db: Session,
        provider: Optional[BaseAIProvider] = None,
        tool_registry: Optional[ToolRegistry] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = TaskRepository(db)
        self.provider = provider or OpenRouterProvider(settings=self.settings)
        self.tool_registry = tool_registry or create_default_tool_registry(settings=self.settings, db=db)
        self.planner = TaskPlanner(provider=self.provider, tool_registry=self.tool_registry, settings=self.settings)
        self.executor = TaskExecutor(repository=self.repo, tool_registry=self.tool_registry, settings=self.settings)
        self.recovery = TaskRecoveryManager(self.repo)

    async def create_and_plan_task(self, request: CreateTaskPlanRequest) -> OrchestratedTaskResponse:
        """Create a new task, formulate its structured plan, and optionally auto-execute."""
        # 1. Create task record
        task = self.repo.create_task(
            title=request.goal[:100],
            description=request.goal,
            priority=request.priority,
        )

        # 2. Transition state to PLANNING
        TaskStateMachine.validate_transition(task.status, TaskStatus.PLANNING)
        self.repo.update_task_status(task_id=task.id, status=TaskStatus.PLANNING)

        # 3. Generate structured execution plan
        try:
            plan: TaskPlan = await self.planner.plan(task_id=task.id, user_goal=request.goal)
            self.repo.persist_plan(task_id=task.id, plan=plan)

            # Check if any step requires approval
            has_approval_step = any(s.approval_required for s in plan.steps)
            next_status = TaskStatus.AWAITING_APPROVAL if has_approval_step else TaskStatus.READY

            TaskStateMachine.validate_transition(TaskStatus.PLANNING, next_status)
            task = self.repo.update_task_status(task_id=task.id, status=next_status)

        except Exception as exc:
            logger.error(f"Planning failed for task {task.id}: {exc}", exc_info=True)
            self.repo.update_task_status(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error_message=f"Plan generation failed: {exc}",
            )
            return self.get_task_details(task.id)

        # 4. Optional Auto-execution if READY and auto_execute requested
        if request.auto_execute and task.status == TaskStatus.READY:
            logger.info(f"Auto-executing task {task.id} in background task.")
            # Launch async execution task
            asyncio.create_task(self.executor.execute_task(task.id))

        return self.get_task_details(task.id)

    async def start_task(self, task_id: int) -> OrchestratedTaskResponse:
        """Start execution of an eligible READY task."""
        task = self.repo.get_task(task_id)

        if task.status == TaskStatus.AWAITING_APPROVAL:
            raise TaskApprovalRequiredError(
                f"Task {task_id} requires explicit user approval before execution can start."
            )

        if task.status != TaskStatus.READY and task.status != TaskStatus.PAUSED:
            raise TaskNotEligibleError(
                f"Task {task_id} is in status '{task.status.value}', which cannot be started. Must be 'ready' or 'paused'."
            )

        # Execute task sequentially
        await self.executor.execute_task(task_id)
        return self.get_task_details(task_id)

    def cancel_task(self, task_id: int, reason: Optional[str] = None) -> OrchestratedTaskResponse:
        """Cancel a pending, ready, running, or paused task safely."""
        task = self.repo.get_task(task_id)

        if task.is_terminal():
            raise InvalidTaskStateError(
                message=f"Task {task_id} is already in terminal state '{task.status.value}' and cannot be cancelled.",
                current_status=task.status.value,
                target_status="cancelled",
            )

        # Set cancellation flag and transition
        task.cancellation_requested = True
        self.db.commit()

        if task.status == TaskStatus.RUNNING:
            # Transition to CANCELLING; running executor loop will observe and transition to CANCELLED
            self.repo.update_task_status(task_id=task_id, status=TaskStatus.CANCELLING)
        else:
            # Immediate cancellation for non-running tasks
            steps = self.repo.get_task_steps(task_id)
            for s in steps:
                if s.status in {StepStatus.PENDING, StepStatus.READY, StepStatus.AWAITING_APPROVAL}:
                    self.repo.update_step_status(
                        step_db_id=s.id,
                        status=StepStatus.CANCELLED,
                        error_message=reason or "Task cancelled by user.",
                    )
            self.repo.update_task_status(task_id=task_id, status=TaskStatus.CANCELLED, error_message=reason)

        return self.get_task_details(task_id)

    def approve_task(self, task_id: int, reason: Optional[str] = None) -> OrchestratedTaskResponse:
        """Grant approval to a task waiting in AWAITING_APPROVAL state."""
        task = self.repo.get_task(task_id)

        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise InvalidTaskStateError(
                message=f"Task {task_id} is not awaiting approval (current status: '{task.status.value}').",
                current_status=task.status.value,
                target_status="ready",
            )

        # Mark awaiting approval steps as ready
        steps = self.repo.get_task_steps(task_id)
        for s in steps:
            if s.status == StepStatus.AWAITING_APPROVAL:
                self.repo.update_step_status(step_db_id=s.id, status=StepStatus.READY)

        self.repo.record_event(
            task_id=task_id,
            event_type="task_approval_granted",
            message=f"Task approval granted. Reason: {reason or 'User confirmed'}",
        )
        self.repo.update_task_status(task_id=task_id, status=TaskStatus.READY)
        return self.get_task_details(task_id)

    def deny_task(self, task_id: int, reason: Optional[str] = None) -> OrchestratedTaskResponse:
        """Deny approval to a task, marking it CANCELLED with audit record."""
        task = self.repo.get_task(task_id)

        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise InvalidTaskStateError(
                message=f"Task {task_id} is not awaiting approval (current status: '{task.status.value}').",
                current_status=task.status.value,
                target_status="cancelled",
            )

        steps = self.repo.get_task_steps(task_id)
        for s in steps:
            if s.status in {StepStatus.PENDING, StepStatus.AWAITING_APPROVAL}:
                self.repo.update_step_status(
                    step_db_id=s.id,
                    status=StepStatus.CANCELLED,
                    error_message=f"Approval denied: {reason or 'User rejected'}",
                )

        self.repo.record_event(
            task_id=task_id,
            event_type="task_approval_denied",
            message=f"Task approval denied. Reason: {reason or 'User rejected'}",
        )
        self.repo.update_task_status(
            task_id=task_id,
            status=TaskStatus.CANCELLED,
            error_message=f"Task approval denied: {reason or 'User rejected'}",
        )
        return self.get_task_details(task_id)

    def get_task_details(self, task_id: int) -> OrchestratedTaskResponse:
        """Fetch task record, assemble steps, and compute exact progress percentage."""
        task = self.repo.get_task(task_id)
        db_steps = self.repo.get_task_steps(task_id)

        total_steps = len(db_steps)
        completed_steps = sum(1 for s in db_steps if s.status == StepStatus.SUCCEEDED)
        failed_steps = sum(1 for s in db_steps if s.status in {StepStatus.FAILED, StepStatus.TIMED_OUT})
        skipped_steps = sum(1 for s in db_steps if s.status in {StepStatus.SKIPPED, StepStatus.CANCELLED})

        progress_pct = round((completed_steps / total_steps) * 100.0, 1) if total_steps > 0 else 0.0

        step_responses: List[StepResponse] = []
        for s in db_steps:
            args = json.loads(s.arguments_json) if s.arguments_json else {}
            deps = json.loads(s.dependencies_json) if s.dependencies_json else []
            perms = json.loads(s.required_permissions_json) if s.required_permissions_json else []

            step_responses.append(
                StepResponse(
                    step_id=s.step_id,
                    sequence_number=s.sequence_number,
                    description=s.description,
                    action_type=s.action_type,
                    tool_name=s.tool_name,
                    arguments=args,
                    dependencies=deps,
                    required_permissions=perms,
                    approval_required=s.approval_required,
                    timeout_seconds=s.timeout_seconds,
                    status=s.status,
                    attempt_count=s.attempt_count,
                    created_at=s.created_at,
                    started_at=s.started_at,
                    completed_at=s.completed_at,
                    result_summary=s.result_summary,
                    error_code=s.error_code,
                    error_message=s.error_message,
                    verification_status=s.verification_status,
                )
            )

        return OrchestratedTaskResponse(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            created_at=task.created_at,
            updated_at=task.updated_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            error_message=task.error_message,
            plan_summary=task.plan_summary,
            current_step_id=task.current_step_id,
            cancellation_requested=task.cancellation_requested,
            total_steps=total_steps,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            skipped_steps=skipped_steps,
            progress_percentage=progress_pct,
            steps=step_responses,
        )

    def list_task_events(self, task_id: int, limit: int = 50) -> List[TaskEventResponse]:
        """Retrieve audit execution events for a task."""
        # Ensure task exists
        self.repo.get_task(task_id)
        events = self.repo.list_events(task_id=task_id, limit=limit)
        return [
            TaskEventResponse(
                id=e.id,
                task_id=e.task_id or task_id,
                event_type=e.event_type,
                level=e.level.value,
                message=e.message,
                created_at=e.created_at,
                metadata=json.loads(e.metadata_json) if e.metadata_json else None,
            )
            for e in events
        ]
