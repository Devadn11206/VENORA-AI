"""Pydantic schemas for Phase 7 Long-Term Memory, Semantic Retrieval & Contextual Recall."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from app.models.memory import MemoryCategory, MemoryStatus


# ---------------------------------------------------------
# Memory CRUD & Read Schemas
# ---------------------------------------------------------

class MemoryCreate(BaseModel):
    """Payload to explicitly create or record a new memory."""
    category: MemoryCategory = Field(..., description="Classification category for the memory record.")
    content: str = Field(..., min_length=3, max_length=10000, description="Durable factual context or preference to store.")
    summary: Optional[str] = Field(None, max_length=512, description="Short summary for rapid inspection.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in accuracy of this fact.")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Subjective priority or longevity weight.")
    source_type: str = Field(default="user_explicit", max_length=64, description="Origin: user_explicit, conversation_extract, task_execution, etc.")
    source_reference: Optional[str] = Field(None, max_length=255, description="Source conversation ID or task ID.")
    ttl_days: Optional[int] = Field(None, ge=1, le=365, description="Optional lifespan in days before automatic expiration.")


class MemoryUpdate(BaseModel):
    """Payload to update an existing memory record."""
    content: Optional[str] = Field(None, min_length=3, max_length=10000, description="Updated content.")
    summary: Optional[str] = Field(None, max_length=512, description="Updated summary.")
    category: Optional[MemoryCategory] = Field(None, description="Updated category.")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: Optional[MemoryStatus] = Field(None, description="Status update (active, archived, superseded).")
    ttl_days: Optional[int] = Field(None, ge=1, le=365)


class MemoryResponse(BaseModel):
    """Public serialized representation of a memory record."""
    id: str
    category: MemoryCategory
    content: str
    summary: Optional[str] = None
    confidence: float
    importance: float
    access_count: int
    content_hash: str
    source_type: str
    source_reference: Optional[str] = None
    superseded_by: Optional[str] = None
    status: MemoryStatus
    embedding_model: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_accessed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MemoryListResponse(BaseModel):
    """Paginated collection of memory records."""
    total: int
    items: List[MemoryResponse]
    limit: int
    offset: int


# ---------------------------------------------------------
# Search & Retrieval Schemas
# ---------------------------------------------------------

class MemorySearchRequest(BaseModel):
    """Query payload for hybrid / semantic / lexical memory search."""
    query: str = Field(..., min_length=1, max_length=1000, description="Natural language search phrase.")
    categories: Optional[List[MemoryCategory]] = Field(None, description="Filter to specific memory categories.")
    limit: int = Field(default=8, ge=1, le=50, description="Maximum number of relevant items to return.")
    min_relevance: float = Field(default=0.25, ge=0.0, le=1.0, description="Minimum combined relevance threshold.")
    include_archived: bool = Field(default=False, description="Whether to include archived memories in search.")


class MemorySearchResult(BaseModel):
    """A scored memory item returned from search or retrieval."""
    id: str
    content: str
    category: MemoryCategory
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Combined hybrid relevance score.")
    semantic_score: Optional[float] = None
    lexical_score: Optional[float] = None
    confidence: float
    importance: float
    source_reference: Optional[str] = None
    created_at: datetime
    explanation: Optional[str] = None


class MemorySearchResponse(BaseModel):
    """Search response with metadata about the retrieval strategy used."""
    query: str
    retrieval_mode: str = Field(..., description="'hybrid', 'semantic', or 'lexical_only'")
    total_found: int
    results: List[MemorySearchResult]


# ---------------------------------------------------------
# Extraction Schemas
# ---------------------------------------------------------

class CandidateMemory(BaseModel):
    """Extracted candidate memory before validation and persistence."""
    content: str = Field(..., min_length=3, max_length=5000)
    category: MemoryCategory
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    reason_for_retention: str = Field(default="", description="Why this fact or preference should be remembered.")
    ttl_days: Optional[int] = Field(None, ge=1, le=365)


class ExtractionResult(BaseModel):
    """Outcome of an automatic conversation memory extraction run."""
    total_candidates: int
    saved_count: int
    updated_count: int
    skipped_count: int
    saved_memories: List[MemoryResponse] = Field(default_factory=list)


# ---------------------------------------------------------
# System Diagnostics & Status
# ---------------------------------------------------------

class MemoryStatusResponse(BaseModel):
    """Health, sizing, and configuration diagnostics for memory subsystem."""
    enabled: bool
    auto_extract_enabled: bool
    total_active: int
    total_archived: int
    total_superseded: int
    total_expired: int
    retrieval_mode: str
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    recent_extraction_failures: int = 0
    recent_retrieval_failures: int = 0
