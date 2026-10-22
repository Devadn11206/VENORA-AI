"""Business logic service for Task management and execution tracking."""

import math
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.errors import TaskNotFoundError, InvalidTaskStateError
from app.core.logging import get_logger
from app.database.base import utc_now
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.execution_log import ExecutionLog, LogLevel
from app.schemas.task import TaskCreate, TaskUpdate

logger = get_logger("services.task")


class TaskService:
    """Service handling all task lifecycle operations and business constraints."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_task(self, task_in: TaskCreate) -> Task:
        """Create a new task with initial PENDING status and record creation event."""
        task_title = (task_in.title or task_in.goal or "Untitled Task").strip()
        task_desc = (task_in.description or task_in.goal or "").strip() or None
        task = Task(
            title=task_title[:255],
            description=task_desc,
            priority=task_in.priority,
            status=TaskStatus.PENDING,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.db.add(task)
        self.db.flush()  # Obtain task.id


        # Record creation event log
        log_entry = ExecutionLog(
            task_id=task.id,
            event_type="task_created",
            level=LogLevel.INFO,
            message=f"Task '{task.title}' created with priority '{task.priority.value}'.",
            created_at=utc_now(),
        )
        self.db.add(log_entry)
        self.db.commit()
        self.db.refresh(task)

        logger.info(f"Created task id={task.id} title={task.title!r}")
        return task

    def get_task_by_id(self, task_id: int) -> Task:
        """Retrieve a task by ID or raise TaskNotFoundError."""
        stmt = select(Task).where(Task.id == task_id)
        task = self.db.execute(stmt).scalar_one_or_none()
        if not task:
            raise TaskNotFoundError(task_id=task_id)
        return task

    def list_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
    ) -> Tuple[List[Task], int, int]:
        """List tasks with pagination and optional filtering."""
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 20
        page_size = min(page_size, 100)

        # Base query
        stmt = select(Task)
        count_stmt = select(func.count()).select_from(Task)

        # Filters
        if status:
            stmt = stmt.where(Task.status == status)
            count_stmt = count_stmt.where(Task.status == status)
        if priority:
            stmt = stmt.where(Task.priority == priority)
            count_stmt = count_stmt.where(Task.priority == priority)

        # Count total items
        total = self.db.execute(count_stmt).scalar() or 0
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        # Apply ordering and pagination
        offset = (page - 1) * page_size
        stmt = stmt.order_by(Task.created_at.desc()).offset(offset).limit(page_size)

        tasks = list(self.db.execute(stmt).scalars().all())
        return tasks, total, total_pages

    def update_task(self, task_id: int, task_in: TaskUpdate) -> Task:
        """Update permitted fields for an existing task with state validation."""
        task = self.get_task_by_id(task_id)

        # Prevent terminal tasks from being accidentally modified
        if task.is_terminal():
            raise InvalidTaskStateError(
                f"Task {task_id} is in terminal state '{task.status.value}' and cannot be updated.",
                current_status=task.status.value
            )

        updated_fields = []

        if task_in.title is not None:
            task.title = task_in.title.strip()
            updated_fields.append("title")

        if task_in.description is not None:
            task.description = task_in.description.strip() if task_in.description else None
            updated_fields.append("description")

        if task_in.priority is not None:
            task.priority = task_in.priority
            updated_fields.append("priority")

        if task_in.status is not None and task_in.status != task.status:
            old_status = task.status
            new_status = task_in.status

            # Handle transition timestamps
            if new_status == TaskStatus.RUNNING and not task.started_at:
                task.started_at = utc_now()
            elif new_status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                task.completed_at = utc_now()

            task.status = new_status
            updated_fields.append("status")

            # Record status change log
            log_entry = ExecutionLog(
                task_id=task.id,
                event_type="status_changed",
                level=LogLevel.INFO,
                message=f"Task status transitioned from '{old_status.value}' to '{new_status.value}'.",
                created_at=utc_now(),
            )
            self.db.add(log_entry)

        if updated_fields:
            task.updated_at = utc_now()
            self.db.commit()
            self.db.refresh(task)
            logger.info(f"Updated task {task.id}: {', '.join(updated_fields)}")

        return task

    def cancel_task(self, task_id: int, reason: Optional[str] = None) -> Task:
        """Cancel a pending/unstarted task."""
        task = self.get_task_by_id(task_id)

        if not task.can_be_cancelled():
            raise InvalidTaskStateError(
                f"Task {task_id} with status '{task.status.value}' cannot be cancelled via pending cancellation.",
                current_status=task.status.value,
                target_status=TaskStatus.CANCELLED.value
            )

        task.status = TaskStatus.CANCELLED
        task.completed_at = utc_now()
        task.updated_at = utc_now()

        cancel_msg = f"Task cancelled before execution. Reason: {reason}" if reason else "Task cancelled before execution."
        log_entry = ExecutionLog(
            task_id=task.id,
            event_type="task_cancelled",
            level=LogLevel.WARNING,
            message=cancel_msg,
            created_at=utc_now(),
        )
        self.db.add(log_entry)
        self.db.commit()
        self.db.refresh(task)

        logger.info(f"Task {task_id} successfully cancelled.")
        return task
