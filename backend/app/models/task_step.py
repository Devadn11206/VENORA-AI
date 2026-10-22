"""TaskStep database model representing discrete executable steps within a structured task plan."""

from datetime import datetime
import enum
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utc_now
from app.desktop.schemas import VerificationStatus

if TYPE_CHECKING:
    from app.models.task import Task


class StepStatus(str, enum.Enum):
    """Lifecycle states for individual task execution steps."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    AWAITING_APPROVAL = "awaiting_approval"
    NEEDS_ATTENTION = "needs_attention"


class TaskStep(Base):
    """SQLAlchemy model for representing a step in an orchestrated task."""

    __tablename__ = "task_steps"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    step_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), default="tool_call", nullable=False)
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    arguments_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dependencies_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    required_permissions_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approval_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    timeout_seconds: Mapped[float] = mapped_column(default=30.0, nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, native_enum=False, length=50),
        default=StepStatus.PENDING,
        nullable=False,
        index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
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
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False, length=50),
        default=VerificationStatus.UNVERIFIED,
        nullable=False
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="steps")

    def __repr__(self) -> str:
        return f"<TaskStep id={self.id} step_id={self.step_id!r} task_id={self.task_id} status={self.status.value}>"
