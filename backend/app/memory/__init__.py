"""Package exports for the VENORA AI long-term memory subsystem."""

from app.memory.schemas import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
    MemoryListResponse,
    MemorySearchRequest,
    MemorySearchResult,
    MemorySearchResponse,
    CandidateMemory,
    ExtractionResult,
    MemoryStatusResponse,
)
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.memory.embeddings import BaseEmbeddingProvider, MockEmbeddingProvider, get_embedding_provider
from app.memory.ranking import score_memory, compute_lexical_score
from app.memory.deduplication import compute_content_hash, detect_memory_conflict
from app.memory.privacy import sanitize_and_redact_secrets, contains_sensitive_secrets

__all__ = [
    "MemoryCreate",
    "MemoryUpdate",
    "MemoryResponse",
    "MemoryListResponse",
    "MemorySearchRequest",
    "MemorySearchResult",
    "MemorySearchResponse",
    "CandidateMemory",
    "ExtractionResult",
    "MemoryStatusResponse",
    "MemoryRepository",
    "MemoryService",
    "BaseEmbeddingProvider",
    "MockEmbeddingProvider",
    "get_embedding_provider",
    "score_memory",
    "compute_lexical_score",
    "compute_content_hash",
    "detect_memory_conflict",
    "sanitize_and_redact_secrets",
    "contains_sensitive_secrets",
]
