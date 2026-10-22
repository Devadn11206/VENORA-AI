"""FastAPI router for Phase 7 Long-Term Memory, Semantic Retrieval & Contextual Recall."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.config import get_settings, Settings
from app.core.errors import MemoryError, MemoryNotFoundError, MemoryValidationError
from app.models.memory import MemoryCategory, MemoryStatus
from app.memory.schemas import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
    MemoryListResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    ExtractionResult,
    MemoryStatusResponse,
)
from app.memory.service import MemoryService
from app.desktop.permissions import DesktopPermissionService
from app.core.logging import get_logger

logger = get_logger("api.memory")
router = APIRouter(prefix="/memory", tags=["Long-Term Memory"])


def get_memory_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemoryService:
    """Dependency provider for MemoryService."""
    return MemoryService(db=db, settings=settings)


def verify_memory_permission(action: str, settings: Settings = Depends(get_settings)) -> None:
    """Enforce default-deny action authorization for memory endpoints."""
    perm_service = DesktopPermissionService(settings=settings)
    perm_service.check_permission(action)


# -----------------------------------------------------------------------------
# Diagnostics & Status
# -----------------------------------------------------------------------------
@router.get("/status", response_model=MemoryStatusResponse, summary="Memory Subsystem Status")
def get_memory_status(
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> MemoryStatusResponse:
    """Return health, configuration, and capacity metrics for the memory subsystem."""
    verify_memory_permission("memory.read", settings=settings)
    return service.get_status()


@router.get("/diagnostics", response_model=MemoryStatusResponse, summary="Memory Subsystem Diagnostics")
def get_memory_diagnostics(
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> MemoryStatusResponse:
    """Alias for status diagnostics with safe observability metrics."""
    verify_memory_permission("memory.read", settings=settings)
    return service.get_status()


# -----------------------------------------------------------------------------
# Search & Retrieval
# -----------------------------------------------------------------------------
@router.post("/search", response_model=MemorySearchResponse, summary="Search Persistent Memories")
def search_memories(
    request: MemorySearchRequest,
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> MemorySearchResponse:
    """Search stored memories using natural language with hybrid/lexical matching."""
    verify_memory_permission("memory.search", settings=settings)
    return service.search_memories(request)


# -----------------------------------------------------------------------------
# Memory CRUD
# -----------------------------------------------------------------------------
@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED, summary="Create Memory")
def create_memory(
    payload: MemoryCreate,
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> MemoryResponse:
    """Explicitly save a new durable memory record with deduplication and validation."""
    verify_memory_permission("memory.create", settings=settings)
    try:
        record = service.save_memory(payload)
        return MemoryResponse.model_validate(record)
    except MemoryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=MemoryListResponse, summary="List Stored Memories")
def list_memories(
    category: Optional[MemoryCategory] = Query(None, description="Filter by memory category"),
    status_filter: Optional[MemoryStatus] = Query(MemoryStatus.ACTIVE, alias="status", description="Filter by status (default active)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> MemoryListResponse:
    """List memory records with pagination and status/category filters."""
    verify_memory_permission("memory.read", settings=settings)
    total, items = service.repository.list_memories(
        category=category,
        status=status_filter,
        limit=limit,
        offset=offset
    )
    return MemoryListResponse(
        total=total,
        items=[MemoryResponse.model_validate(item) for item in items],
        limit=limit,
        offset=offset,
    )


@router.get("/{memory_id}", response_model=MemoryResponse, summary="Get Memory by ID")
def get_memory(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> MemoryResponse:
    """Retrieve details for a single memory record."""
    verify_memory_permission("memory.read", settings=settings)
    record = service.repository.get_by_id(memory_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Memory '{memory_id}' not found.")
    return MemoryResponse.model_validate(record)


@router.patch("/{memory_id}", response_model=MemoryResponse, summary="Update Memory")
def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> MemoryResponse:
    """Update content, confidence, importance, or category of an existing memory record."""
    verify_memory_permission("memory.update", settings=settings)
    updated = service.repository.update(memory_id, payload)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Memory '{memory_id}' not found.")
    return MemoryResponse.model_validate(updated)


@router.post("/{memory_id}/archive", response_model=MemoryResponse, summary="Archive Memory")
def archive_memory(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> MemoryResponse:
    """Archive a memory record so it is excluded from default search results."""
    verify_memory_permission("memory.archive", settings=settings)
    archived = service.repository.archive(memory_id)
    if not archived:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Memory '{memory_id}' not found.")
    return MemoryResponse.model_validate(archived)


@router.post("/{memory_id}/restore", response_model=MemoryResponse, summary="Restore Memory")
def restore_memory(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> MemoryResponse:
    """Restore an archived or superseded memory record back to active status."""
    verify_memory_permission("memory.update", settings=settings)
    restored = service.repository.restore(memory_id)
    if not restored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Memory '{memory_id}' not found.")
    return MemoryResponse.model_validate(restored)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Memory")
def delete_memory(
    memory_id: str,
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> None:
    """Permanently delete a memory record and purge it from search indexes."""
    verify_memory_permission("memory.delete", settings=settings)
    deleted = service.repository.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Memory '{memory_id}' not found.")
    return None


# -----------------------------------------------------------------------------
# Conversation Extraction Trigger
# -----------------------------------------------------------------------------
@router.post("/extract", response_model=ExtractionResult, summary="Extract Memories from Conversation")
def extract_memories(
    messages: List[dict],
    source_reference: Optional[str] = Query(None, description="Optional conversation or task reference ID"),
    service: MemoryService = Depends(get_memory_service),
    settings: Settings = Depends(get_settings),
) -> ExtractionResult:
    """Run memory extraction on provided message turns and persist valid candidates."""
    verify_memory_permission("memory.create", settings=settings)
    return service.extract_and_save_from_conversation(messages=messages, source_reference=source_reference)

