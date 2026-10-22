"""SQLAlchemy models for Phase 5 Document Intelligence & Vectorless FTS Indexing."""

from datetime import datetime, timezone
import enum
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import relationship

from app.database.base import Base


class DocumentProcessingStatus(str, enum.Enum):
    """Processing lifecycle states for registered documents."""
    DISCOVERED = "discovered"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    INDEXED = "indexed"
    ERROR = "error"
    STALE = "stale"


class AuthorizedDirectory(Base):
    """Explicitly authorized directory root for document discovery."""
    __tablename__ = "authorized_directories"

    id = Column(String(36), primary_key=True)
    path = Column(String(512), unique=True, nullable=False, index=True)
    label = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    documents = relationship("Document", back_populates="directory", cascade="all, delete-orphan")


class Document(Base):
    """Metadata record for a discovered, extracted, and indexed document."""
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True)
    directory_id = Column(String(36), ForeignKey("authorized_directories.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False, index=True)
    relative_path = Column(String(512), nullable=False)
    absolute_path = Column(String(1024), nullable=False)
    file_type = Column(String(32), nullable=False, index=True)
    file_size_bytes = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)  # SHA-256
    status = Column(SQLEnum(DocumentProcessingStatus), default=DocumentProcessingStatus.DISCOVERED, nullable=False, index=True)
    page_count = Column(Integer, default=1, nullable=False)
    extracted_text = Column(Text, nullable=True)  # Normalized text summary or sample
    error_summary = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_extracted_at = Column(DateTime, nullable=True)
    last_indexed_at = Column(DateTime, nullable=True)

    directory = relationship("AuthorizedDirectory", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_documents_dir_relpath", "directory_id", "relative_path", unique=True),
    )


class DocumentChunk(Base):
    """Structural text chunk for retrieval and local search."""
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    section_title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_doc_index", "document_id", "chunk_index"),
    )
