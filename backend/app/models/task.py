"""Task database model representing units of work in VENORA AI."""

from datetime import datetime
import enum
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.execution_log import ExecutionLog
    from app.models.task_step import TaskStep



class TaskStatus(str, enum.Enum):
    """Lifecycle statuses for a Task."""
    PENDING = "pending"
    CREATED = "created"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"
    NEEDS_ATTENTION = "needs_attention"



class TaskPriority(str, enum.Enum):
    """Priority classifications for a Task."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Task(Base):
    """SQLAlchemy model for Tasks."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=50),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, native_enum=False, length=50),
        default=TaskPriority.NORMAL,
        nullable=False,
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_step_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Relationships
    execution_logs: Mapped[List["ExecutionLog"]] = relationship(
        "ExecutionLog",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ExecutionLog.created_at.asc()"
    )
    steps: Mapped[List["TaskStep"]] = relationship(
        "TaskStep",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskStep.sequence_number.asc()"
    )

    def is_terminal(self) -> bool:
        """Check if task is in a terminal state that cannot be reopened."""
        return self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PARTIALLY_COMPLETED,
        }

    def can_be_cancelled(self) -> bool:
        """Check if task is eligible to be cancelled before execution."""
        return self.status in {
            TaskStatus.PENDING,
            TaskStatus.CREATED,
            TaskStatus.PLANNING,
            TaskStatus.AWAITING_APPROVAL,
            TaskStatus.READY,
        }



    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r} status={self.status.value}>"
