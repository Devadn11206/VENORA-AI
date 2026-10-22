"""Lifecycle recovery manager detecting interrupted tasks after restart and resolving state."""

import logging
from typing import List
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.base import utc_now
from app.models.task import Task, TaskStatus
from app.models.task_step import TaskStep, StepStatus
from app.models.execution_log import LogLevel
from app.orchestration.task_repository import TaskRepository

logger = logging.getLogger("venora.orchestration.recovery")


class TaskRecoveryManager:
    """Detects and reconciles tasks and steps that were abruptly interrupted by server restarts or crashes."""

    def __init__(self, repository: TaskRepository) -> None:
        self.repo = repository

    def recover_interrupted_tasks(self) -> List[int]:
        """Scan database for tasks left in non-terminal transient states (RUNNING, CANCELLING, PLANNING).
        
        Conservative Safety Policy:
        - Never automatically replay side-effect operations whose outcome is uncertain.
        - Transition transient tasks to NEEDS_ATTENTION or CANCELLED with audit log entry.
        - Mark running steps as FAILED with recovery error code.
        """
        stmt = select(Task).where(
            Task.status.in_([TaskStatus.RUNNING, TaskStatus.CANCELLING, TaskStatus.PLANNING])
        )
        interrupted_tasks = list(self.repo.db.execute(stmt).scalars().all())
        recovered_ids: List[int] = []

        for task in interrupted_tasks:
            logger.warning(f"Detected interrupted task {task.id} in state '{task.status.value}' upon startup.")

            # Look for steps left in RUNNING state
            steps = self.repo.get_task_steps(task.id)
            for step in steps:
                if step.status == StepStatus.RUNNING:
                    self.repo.update_step_status(
                        step_db_id=step.id,
                        status=StepStatus.FAILED,
                        error_code="INTERRUPTED_BY_SHUTDOWN",
                        error_message="Step execution was interrupted by an application restart or crash.",
                    )

            # Reconcile task state
            if task.status == TaskStatus.CANCELLING:
                new_status = TaskStatus.CANCELLED
                msg = "Task transitioned to CANCELLED during startup recovery."
            else:
                new_status = TaskStatus.NEEDS_ATTENTION
                msg = (
                    "Task execution was interrupted by a process restart. Outcome of the current step is uncertain. "
                    "Manual inspection is required before resuming."
                )

            self.repo.update_task_status(
                task_id=task.id,
                status=new_status,
                error_message=msg,
            )
            self.repo.record_event(
                task_id=task.id,
                event_type="recovery_reconciliation",
                message=msg,
                level=LogLevel.WARNING,
            )
            recovered_ids.append(task.id)

        if recovered_ids:
            logger.info(f"Reconciled {len(recovered_ids)} interrupted tasks during startup recovery: {recovered_ids}")

        return recovered_ids
