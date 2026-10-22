"""SQLAlchemy models for Phase 7 Long-Term Memory, Semantic Retrieval & Contextual Recall."""

from datetime import datetime, timezone
import enum
from typing import Optional
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Enum as SQLEnum,
    Text,
    Index,
)

from app.database.base import Base


class MemoryCategory(str, enum.Enum):
    """Categorization for persistent memory records."""
    USER_PREFERENCE = "USER_PREFERENCE"
    USER_FACT = "USER_FACT"
    PROJECT_CONTEXT = "PROJECT_CONTEXT"
    TASK_CONTEXT = "TASK_CONTEXT"
    PROCEDURAL_MEMORY = "PROCEDURAL_MEMORY"
    CONVERSATION_SUMMARY = "CONVERSATION_SUMMARY"
    EPISODIC_MEMORY = "EPISODIC_MEMORY"


class MemoryStatus(str, enum.Enum):
    """Lifecycle status for a memory record."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"
    SUPERSEDED = "superseded"


class MemoryRecord(Base):
    """Durable long-term memory record."""
    __tablename__ = "memories"

    id = Column(String(36), primary_key=True)
    category = Column(SQLEnum(MemoryCategory), nullable=False, index=True)
    content = Column(Text, nullable=False)
    summary = Column(String(512), nullable=True)

    # Scoring & tracking
    confidence = Column(Float, default=1.0, nullable=False)
    importance = Column(Float, default=0.5, nullable=False)
    access_count = Column(Integer, default=0, nullable=False)

    # Deduplication & provenance
    content_hash = Column(String(64), nullable=False, index=True)  # SHA-256 of normalized content
    source_type = Column(String(64), default="user_explicit", nullable=False, index=True)
    source_reference = Column(String(255), nullable=True, index=True)  # e.g., session_id, task_id
    superseded_by = Column(String(36), nullable=True)  # Memory ID of the superseding record

    # Lifecycle state
    status = Column(SQLEnum(MemoryStatus), default=MemoryStatus.ACTIVE, nullable=False, index=True)

    # Embedding representation (JSON serialized float array or NULL)
    embedding_json = Column(Text, nullable=True)
    embedding_model = Column(String(128), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index("ix_memories_status_category", "status", "category"),
        Index("ix_memories_status_expires", "status", "expires_at"),
    )
