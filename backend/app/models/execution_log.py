"""ExecutionLog database model representing task and operational events."""

from datetime import datetime
import enum
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.task import Task


class LogLevel(str, enum.Enum):
    """Log level severity for execution logs."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ExecutionLog(Base):
    """SQLAlchemy model for structured task execution event records."""

    __tablename__ = "execution_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    level: Mapped[LogLevel] = mapped_column(
        Enum(LogLevel, native_enum=False, length=20),
        default=LogLevel.INFO,
        nullable=False,
        index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    task: Mapped[Optional["Task"]] = relationship("Task", back_populates="execution_logs")

    def __repr__(self) -> str:
        return f"<ExecutionLog id={self.id} task_id={self.task_id} event={self.event_type} level={self.level.value}>"
