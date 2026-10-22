"""State machine defining and enforcing valid lifecycle transitions for Tasks and Steps."""

import logging
from typing import Dict, Set

from app.core.errors import InvalidTaskStateError
from app.models.task import TaskStatus
from app.models.task_step import StepStatus

logger = logging.getLogger("venora.orchestration.state_machine")


class TaskStateMachine:
    """Enforces strict, validated state transitions for Tasks."""

    # Explicit mapping of current_state -> set of valid next states
    VALID_TASK_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
        TaskStatus.CREATED: {TaskStatus.PLANNING, TaskStatus.CANCELLED},
        TaskStatus.PLANNING: {TaskStatus.READY, TaskStatus.AWAITING_APPROVAL, TaskStatus.FAILED, TaskStatus.CANCELLED},
        TaskStatus.AWAITING_APPROVAL: {TaskStatus.READY, TaskStatus.CANCELLED, TaskStatus.FAILED},
        TaskStatus.READY: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.PAUSED},
        TaskStatus.RUNNING: {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.PARTIALLY_COMPLETED,
            TaskStatus.CANCELLING,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
            TaskStatus.NEEDS_ATTENTION,
        },
        TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.NEEDS_ATTENTION},
        TaskStatus.CANCELLING: {TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.NEEDS_ATTENTION},
        TaskStatus.NEEDS_ATTENTION: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
        # Legacy compatibility state mapping
        TaskStatus.PENDING: {TaskStatus.PLANNING, TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.CANCELLED},
        # Terminal states have no valid onward transitions
        TaskStatus.COMPLETED: set(),
        TaskStatus.FAILED: set(),
        TaskStatus.CANCELLED: set(),
        TaskStatus.PARTIALLY_COMPLETED: set(),
    }

    @classmethod
    def validate_transition(cls, current: TaskStatus, target: TaskStatus) -> None:
        """Verify that transitioning from current to target status is valid."""
        if current == target:
            return  # Idempotent no-op

        valid_targets = cls.VALID_TASK_TRANSITIONS.get(current, set())
        if target not in valid_targets:
            msg = f"Invalid task state transition: Cannot change status from '{current.value}' to '{target.value}'."
            logger.warning(msg)
            raise InvalidTaskStateError(message=msg, current_status=current.value, target_status=target.value)


class StepStateMachine:
    """Enforces strict, validated state transitions for Task Steps."""

    VALID_STEP_TRANSITIONS: Dict[StepStatus, Set[StepStatus]] = {
        StepStatus.PENDING: {StepStatus.READY, StepStatus.RUNNING, StepStatus.AWAITING_APPROVAL, StepStatus.SKIPPED, StepStatus.CANCELLED},
        StepStatus.AWAITING_APPROVAL: {StepStatus.READY, StepStatus.SKIPPED, StepStatus.CANCELLED},
        StepStatus.READY: {StepStatus.RUNNING, StepStatus.CANCELLED, StepStatus.SKIPPED},

        StepStatus.RUNNING: {
            StepStatus.SUCCEEDED,
            StepStatus.FAILED,
            StepStatus.TIMED_OUT,
            StepStatus.CANCELLED,
            StepStatus.NEEDS_ATTENTION,
        },
        StepStatus.NEEDS_ATTENTION: {StepStatus.READY, StepStatus.FAILED, StepStatus.CANCELLED},
        # Terminal states
        StepStatus.SUCCEEDED: set(),
        StepStatus.FAILED: set(),
        StepStatus.SKIPPED: set(),
        StepStatus.CANCELLED: set(),
        StepStatus.TIMED_OUT: set(),
    }

    @classmethod
    def validate_transition(cls, current: StepStatus, target: StepStatus) -> None:
        """Verify that transitioning a step from current to target status is valid."""
        if current == target:
            return

        valid_targets = cls.VALID_STEP_TRANSITIONS.get(current, set())
        if target not in valid_targets:
            msg = f"Invalid step state transition: Cannot change status from '{current.value}' to '{target.value}'."
            logger.warning(msg)
            raise InvalidTaskStateError(message=msg, current_status=current.value, target_status=target.value)
