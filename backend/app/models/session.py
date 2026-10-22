"""Session database model representing application interaction sessions."""

from datetime import datetime
import enum
from typing import Optional
from sqlalchemy import String, Text, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, utc_now


class SessionType(str, enum.Enum):
    """Types of interaction sessions."""
    API = "api"
    CLI = "cli"
    WEB = "web"
    VOICE = "voice"
    SYSTEM = "system"


class SessionStatus(str, enum.Enum):
    """Lifecycle statuses for interaction sessions."""
    ACTIVE = "active"
    IDLE = "idle"
    TERMINATED = "terminated"
    EXPIRED = "expired"


class Session(Base):
    """SQLAlchemy model for tracking application interaction sessions."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    session_type: Mapped[SessionType] = mapped_column(
        Enum(SessionType, native_enum=False, length=50),
        default=SessionType.API,
        nullable=False,
        index=True
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, native_enum=False, length=50),
        default=SessionStatus.ACTIVE,
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
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Session id={self.id} type={self.session_type.value} status={self.status.value}>"
