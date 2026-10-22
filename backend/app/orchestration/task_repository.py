"""Task and Step persistence repository integrating with SQLAlchemy database models."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from app.core.errors import TaskNotFoundError
from app.database.base import utc_now
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.task_step import TaskStep, StepStatus
from app.models.execution_log import ExecutionLog, LogLevel
from app.orchestration.schemas import StepPlan, StepResponse, TaskPlan

logger = logging.getLogger("venora.orchestration.repository")


class TaskRepository:
    """Manages transactional persistence for Tasks, Steps, and Execution Events."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_task(self, task_id: int) -> Task:
        """Fetch Task by ID or raise TaskNotFoundError."""
        stmt = select(Task).where(Task.id == task_id)
        task = self.db.execute(stmt).scalar_one_or_none()
        if not task:
            raise TaskNotFoundError(task_id=task_id)
        return task

    def get_task_steps(self, task_id: int) -> List[TaskStep]:
        """Fetch all TaskStep records for a task, ordered by sequence."""
        stmt = select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.sequence_number.asc())
        return list(self.db.execute(stmt).scalars().all())

    def create_task(self, title: str, description: Optional[str] = None, priority: TaskPriority = TaskPriority.NORMAL) -> Task:
        """Create a new Task record in CREATED state."""
        task = Task(
            title=title.strip(),
            description=description.strip() if description else None,
            priority=priority,
            status=TaskStatus.CREATED,
            created_at=utc_now(),
            updated_at=utc_now(),
            cancellation_requested=False,
        )
        self.db.add(task)
        self.db.flush()

        self.record_event(
            task_id=task.id,
            event_type="task_created",
            message=f"Task '{task.title}' created in state '{task.status.value}'.",
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def persist_plan(self, task_id: int, plan: TaskPlan) -> None:
        """Store plan summary and create step records in task_steps table."""
        task = self.get_task(task_id)
        task.plan_summary = plan.summary
        task.updated_at = utc_now()

        # Delete any pre-existing draft steps if re-planning
        for existing_step in self.get_task_steps(task_id):
            self.db.delete(existing_step)
        self.db.flush()

        for step in plan.steps:
            db_step = TaskStep(
                step_id=step.step_id,
                task_id=task_id,
                sequence_number=step.sequence_number,
                description=step.description,
                action_type=step.action_type,
                tool_name=step.tool_name,
                arguments_json=json.dumps(step.arguments) if step.arguments else None,
                dependencies_json=json.dumps(step.dependencies) if step.dependencies else None,
                required_permissions_json=json.dumps(step.required_permissions) if step.required_permissions else None,
                approval_required=step.approval_required,
                timeout_seconds=step.timeout_seconds,
                status=step.status,
                attempt_count=0,
                created_at=utc_now(),
            )
            self.db.add(db_step)

        self.record_event(
            task_id=task_id,
            event_type="plan_generated",
            message=f"Plan generated with {len(plan.steps)} steps: {plan.summary}",
        )
        self.db.commit()

    def update_task_status(
        self,
        task_id: int,
        status: TaskStatus,
        error_message: Optional[str] = None,
        current_step_id: Optional[str] = None,
    ) -> Task:
        """Update task lifecycle status and timestamps."""
        task = self.get_task(task_id)
        task.status = status
        task.updated_at = utc_now()

        if status == TaskStatus.RUNNING and not task.started_at:
            task.started_at = utc_now()
        if status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.PARTIALLY_COMPLETED}:
            task.completed_at = utc_now()

        if error_message:
            task.error_message = error_message
        if current_step_id is not None:
            task.current_step_id = current_step_id

        self.record_event(
            task_id=task_id,
            event_type="task_status_changed",
            message=f"Task status changed to '{status.value}'.",
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def update_step_status(
        self,
        step_db_id: int,
        status: StepStatus,
        result_summary: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        verification_status: Optional[Any] = None,
    ) -> TaskStep:
        """Update step lifecycle status, output, and execution metrics."""
        stmt = select(TaskStep).where(TaskStep.id == step_db_id)
        step = self.db.execute(stmt).scalar_one_or_none()
        if not step:
            raise ValueError(f"TaskStep with DB ID {step_db_id} not found.")

        step.status = status
        if status == StepStatus.RUNNING:
            step.started_at = utc_now()
            step.attempt_count += 1
        elif status in {StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.TIMED_OUT, StepStatus.SKIPPED, StepStatus.CANCELLED}:
            step.completed_at = utc_now()

        if result_summary:
            step.result_summary = result_summary
        if error_code:
            step.error_code = error_code
        if error_message:
            step.error_message = error_message
        if verification_status:
            step.verification_status = verification_status

        self.record_event(
            task_id=step.task_id,
            event_type=f"step_{status.value}",
            message=f"Step '{step.step_id}' ({step.sequence_number}) transitioned to '{status.value}'.",
        )
        self.db.commit()
        self.db.refresh(step)
        return step

    def record_event(
        self,
        task_id: int,
        event_type: str,
        message: str,
        level: LogLevel = LogLevel.INFO,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionLog:
        """Record an execution event log entry."""
        log = ExecutionLog(
            task_id=task_id,
            event_type=event_type,
            level=level,
            message=message,
            created_at=utc_now(),
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.db.add(log)
        return log

    def list_events(self, task_id: int, limit: int = 50) -> List[ExecutionLog]:
        """Fetch ordered event logs for a given task."""
        stmt = select(ExecutionLog).where(ExecutionLog.task_id == task_id).order_by(ExecutionLog.created_at.asc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def list_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
    ) -> Tuple[List[Task], int, int]:
        """Fetch paginated tasks with optional filters."""
        query = select(Task)
        count_query = select(func.count(Task.id))

        if status:
            query = query.where(Task.status == status)
            count_query = count_query.where(Task.status == status)
        if priority:
            query = query.where(Task.priority == priority)
            count_query = count_query.where(Task.priority == priority)

        total = self.db.execute(count_query).scalar() or 0
        total_pages = max(1, (total + page_size - 1) // page_size)
        offset = (page - 1) * page_size

        stmt = query.order_by(desc(Task.created_at)).offset(offset).limit(page_size)
        items = list(self.db.execute(stmt).scalars().all())
        return items, total, total_pages
