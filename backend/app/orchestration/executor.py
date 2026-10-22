"""Task executor for safe, sequential execution of planned steps through Phase 3 tool registry."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.ai.tools import create_default_tool_registry
from app.ai.tools.registry import ToolRegistry
from app.core.config import Settings, get_settings
from app.core.errors import (
    DesktopEmergencyStopActiveError,
    DesktopPermissionDeniedError,
    StepDependencyError,
    TaskApprovalRequiredError,
    TaskCancelledError,
    TaskNotEligibleError,
    TaskTimeoutError,
)
from app.desktop.schemas import VerificationStatus
from app.models.task import Task, TaskStatus
from app.models.task_step import TaskStep, StepStatus
from app.models.execution_log import LogLevel
from app.orchestration.state_machine import StepStateMachine, TaskStateMachine
from app.orchestration.task_repository import TaskRepository

logger = logging.getLogger("venora.orchestration.executor")


class TaskExecutor:
    """Safely executes validated steps sequentially with dependency checking, timeouts, and permission gates."""

    def __init__(
        self,
        repository: TaskRepository,
        tool_registry: Optional[ToolRegistry] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.repo = repository
        self.settings = settings or get_settings()
        self.tool_registry = tool_registry or create_default_tool_registry(settings=self.settings)

    async def execute_task(self, task_id: int) -> Task:
        """Run eligible steps for task_id sequentially to completion, failure, or cancellation."""
        task = self.repo.get_task(task_id)

        # 1. State machine validation: Check if task can transition to RUNNING
        TaskStateMachine.validate_transition(task.status, TaskStatus.RUNNING)

        # 2. Check Emergency Stop before starting
        if (
            self.tool_registry.permission_service
            and self.tool_registry.permission_service.emergency_stop_active
        ):
            logger.warning(f"Task {task_id} execution blocked: Emergency Stop is active.")
            self.repo.update_task_status(
                task_id=task_id,
                status=TaskStatus.NEEDS_ATTENTION,
                error_message="Emergency Stop is currently active. Desktop operations blocked.",
            )
            raise DesktopEmergencyStopActiveError()

        # 3. Transition to RUNNING
        task = self.repo.update_task_status(task_id=task_id, status=TaskStatus.RUNNING)
        logger.info(f"Task {task_id} execution started.")

        start_time = datetime.now(timezone.utc)
        max_duration = self.settings.MAX_TASK_DURATION_SECONDS

        steps = self.repo.get_task_steps(task_id)
        if not steps:
            logger.warning(f"Task {task_id} has no steps to execute.")
            return self.repo.update_task_status(task_id=task_id, status=TaskStatus.COMPLETED)

        succeeded_step_ids: set[str] = set()
        failed_step_encountered = False

        for step in steps:
            # Refresh task to detect dynamic cancellation request
            task = self.repo.get_task(task_id)
            if task.cancellation_requested or task.status == TaskStatus.CANCELLING:
                logger.info(f"Task {task_id} cancellation requested. Stopping step execution.")
                self._cancel_remaining_steps(steps, step.sequence_number)
                return self.repo.update_task_status(task_id=task_id, status=TaskStatus.CANCELLED)

            # Check overall task timeout
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed > max_duration:
                msg = f"Task {task_id} exceeded maximum execution limit of {max_duration}s."
                logger.error(msg)
                self._cancel_remaining_steps(steps, step.sequence_number, reason="Task execution timed out")
                return self.repo.update_task_status(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error_message=msg,
                )

            # Check if previous failure occurred (fail-fast policy)
            if failed_step_encountered:
                self.repo.update_step_status(
                    step_db_id=step.id,
                    status=StepStatus.SKIPPED,
                    error_message="Skipped due to failure of an earlier step in sequential plan.",
                )
                continue

            # Check dependencies
            deps = json.loads(step.dependencies_json) if step.dependencies_json else []
            unmet = [d for d in deps if d not in succeeded_step_ids]
            if unmet:
                msg = f"Step '{step.step_id}' blocked by unmet dependencies: {unmet}"
                logger.warning(msg)
                self.repo.update_step_status(
                    step_db_id=step.id,
                    status=StepStatus.FAILED,
                    error_code="UNMET_DEPENDENCY",
                    error_message=msg,
                )
                failed_step_encountered = True
                continue

            # Check step approval requirement
            if step.approval_required:
                logger.info(f"Step '{step.step_id}' requires explicit approval. Pausing task {task_id}.")
                self.repo.update_step_status(step_db_id=step.id, status=StepStatus.AWAITING_APPROVAL)
                return self.repo.update_task_status(
                    task_id=task_id,
                    status=TaskStatus.AWAITING_APPROVAL,
                    current_step_id=step.step_id,
                )

            # Execute step safely
            step_success = await self._execute_step(task_id, step)
            if step_success:
                succeeded_step_ids.add(step.step_id)
            else:
                failed_step_encountered = True

        # Final task status evaluation
        updated_steps = self.repo.get_task_steps(task_id)
        all_succeeded = all(s.status == StepStatus.SUCCEEDED for s in updated_steps)
        any_succeeded = any(s.status == StepStatus.SUCCEEDED for s in updated_steps)
        any_failed = any(s.status in {StepStatus.FAILED, StepStatus.TIMED_OUT} for s in updated_steps)

        if all_succeeded:
            return self.repo.update_task_status(task_id=task_id, status=TaskStatus.COMPLETED)
        elif any_failed and any_succeeded:
            return self.repo.update_task_status(
                task_id=task_id,
                status=TaskStatus.PARTIALLY_COMPLETED,
                error_message="Some steps succeeded while other steps failed or were skipped.",
            )
        else:
            return self.repo.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error_message="One or more steps failed during execution.",
            )

    async def _execute_step(self, task_id: int, step: TaskStep) -> bool:
        """Execute a single step through ToolRegistry with step-level timeout."""
        # Update state: READY -> RUNNING
        StepStateMachine.validate_transition(step.status, StepStatus.RUNNING)
        self.repo.update_step_status(step_db_id=step.id, status=StepStatus.RUNNING)
        self.repo.update_task_status(task_id=task_id, status=TaskStatus.RUNNING, current_step_id=step.step_id)

        # Parse arguments
        args = json.loads(step.arguments_json) if step.arguments_json else {}

        # Re-check tool validity
        if not step.tool_name or not self.tool_registry.has_tool(step.tool_name):
            err_msg = f"Tool '{step.tool_name}' is not recognized or permitted in tool registry."
            self.repo.update_step_status(
                step_db_id=step.id,
                status=StepStatus.FAILED,
                error_code="UNKNOWN_TOOL",
                error_message=err_msg,
                verification_status=VerificationStatus.FAILED,
            )
            return False

        # Execute with timeout
        timeout = step.timeout_seconds or self.settings.STEP_DEFAULT_TIMEOUT_SECONDS
        call_id = f"step_{step.step_id}"

        try:
            tool_res = await asyncio.wait_for(
                self.tool_registry.execute_tool(call_id=call_id, tool_name=step.tool_name, arguments=args),
                timeout=timeout,
            )

            # Evaluate tool outcome
            if tool_res.status == "success":
                summary = (
                    f"Tool '{step.tool_name}' executed successfully. "
                    f"Result: {json.dumps(tool_res.result)[:200]}"
                )
                self.repo.update_step_status(
                    step_db_id=step.id,
                    status=StepStatus.SUCCEEDED,
                    result_summary=summary,
                    verification_status=tool_res.verification_status,
                )
                return True
            else:
                err_msg = tool_res.safe_error_message or f"Tool returned status '{tool_res.status}'."
                self.repo.update_step_status(
                    step_db_id=step.id,
                    status=StepStatus.FAILED,
                    error_code=tool_res.error_code or "TOOL_ERROR",
                    error_message=err_msg,
                    verification_status=tool_res.verification_status,
                )
                return False

        except asyncio.TimeoutError:
            err_msg = f"Step '{step.step_id}' timed out after {timeout} seconds."
            logger.error(err_msg)
            self.repo.update_step_status(
                step_db_id=step.id,
                status=StepStatus.TIMED_OUT,
                error_code="STEP_TIMEOUT",
                error_message=err_msg,
                verification_status=VerificationStatus.FAILED,
            )
            return False
        except Exception as exc:
            err_msg = f"Unexpected error during step '{step.step_id}' execution: {exc}"
            logger.error(err_msg, exc_info=True)
            self.repo.update_step_status(
                step_db_id=step.id,
                status=StepStatus.FAILED,
                error_code="EXECUTION_EXCEPTION",
                error_message=err_msg,
                verification_status=VerificationStatus.FAILED,
            )
            return False

    def _cancel_remaining_steps(self, steps: List[TaskStep], from_sequence: int, reason: Optional[str] = None) -> None:
        """Mark all unexecuted steps from a sequence number onward as CANCELLED."""
        for step in steps:
            if step.sequence_number >= from_sequence and step.status in {StepStatus.PENDING, StepStatus.READY}:
                self.repo.update_step_status(
                    step_db_id=step.id,
                    status=StepStatus.CANCELLED,
                    error_message=reason or "Cancelled by user or task lifecycle interruption.",
                )
