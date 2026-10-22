"""Controlled Phase 7 Long-Term Memory tools registered on ToolRegistry."""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.ai.schemas import ToolResult
from app.ai.tools.base import BaseTool
from app.desktop.schemas import VerificationStatus
from app.memory.service import MemoryService
from app.memory.schemas import (
    MemoryCreate,
    MemoryUpdate,
    MemorySearchRequest,
)
from app.models.memory import MemoryCategory, MemoryStatus

logger = logging.getLogger("venora.ai.tools.memory")


# -----------------------------------------------------------------------------
# Tool Arguments Schemas
# -----------------------------------------------------------------------------
class MemorySearchArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Search query string to find relevant memories.")
    categories: Optional[List[MemoryCategory]] = Field(None, description="Optional categories filter.")
    limit: int = Field(default=8, ge=1, le=50, description="Max memories to return.")
    min_relevance: float = Field(default=0.25, ge=0.0, le=1.0, description="Minimum relevance threshold.")


class MemoryGetArgs(BaseModel):
    memory_id: str = Field(..., description="ID of the memory record to retrieve.")


class MemorySaveArgs(BaseModel):
    category: MemoryCategory = Field(..., description="Category: USER_PREFERENCE, USER_FACT, PROJECT_CONTEXT, etc.")
    content: str = Field(..., min_length=3, max_length=5000, description="Factual information or preference to store.")
    summary: Optional[str] = Field(None, max_length=512, description="Short summary of the memory.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score.")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Importance score.")
    ttl_days: Optional[int] = Field(None, ge=1, le=365, description="Lifespan in days before automatic expiration.")


class MemoryUpdateArgs(BaseModel):
    memory_id: str = Field(..., description="ID of the memory record to update.")
    content: Optional[str] = Field(None, min_length=3, max_length=5000, description="Updated content.")
    summary: Optional[str] = Field(None, max_length=512, description="Updated summary.")
    category: Optional[MemoryCategory] = Field(None, description="Updated category.")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    ttl_days: Optional[int] = Field(None, ge=1, le=365)


class MemoryArchiveArgs(BaseModel):
    memory_id: str = Field(..., description="ID of the memory record to archive.")


class MemoryDeleteArgs(BaseModel):
    memory_id: str = Field(..., description="ID of the memory record to delete.")
    confirm: bool = Field(..., description="Explicit confirmation flag required to prevent accidental deletion.")


class MemoryListArgs(BaseModel):
    category: Optional[MemoryCategory] = Field(None, description="Optional category filter.")
    limit: int = Field(default=20, ge=1, le=100, description="Max items to list.")
    offset: int = Field(default=0, ge=0, description="Pagination offset.")


# -----------------------------------------------------------------------------
# Tool Implementations
# -----------------------------------------------------------------------------
class MemorySearchTool(BaseTool):
    """Search for relevant persistent memories using semantic and lexical matching."""
    name = "memory_search"
    description = "Search long-term memory for relevant past context, user preferences, and project facts."
    required_permission = "memory.search"
    args_schema = MemorySearchArgs
    is_read_only = True

    def __init__(self, service: MemoryService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            req = MemorySearchArgs(**arguments)
            res = self.service.search_memories(
                MemorySearchRequest(
                    query=req.query,
                    categories=req.categories,
                    limit=req.limit,
                    min_relevance=req.min_relevance,
                )
            )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={
                    "retrieval_mode": res.retrieval_mode,
                    "total_found": res.total_found,
                    "results": [r.model_dump() for r in res.results],
                },
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="MEMORY_SEARCH_FAILED",
                safe_error_message=f"Memory search failed: {str(exc)}",
                verification_status=VerificationStatus.FAILED,
            )


class MemoryGetTool(BaseTool):
    """Retrieve details for a specific memory record by ID."""
    name = "memory_get"
    description = "Retrieve a specific persistent memory record by its unique ID."
    required_permission = "memory.read"
    args_schema = MemoryGetArgs
    is_read_only = True

    def __init__(self, service: MemoryService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            args = MemoryGetArgs(**arguments)
            record = self.service.repository.get_by_id(args.memory_id)
            if not record:
                return ToolResult(
                    call_id=call_id,
                    tool_name=self.name,
                    status="error",
                    result=None,
                    error_code="MEMORY_NOT_FOUND",
                    safe_error_message=f"Memory '{args.memory_id}' not found.",
                    verification_status=VerificationStatus.FAILED,
                )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={
                    "id": record.id,
                    "category": record.category.value,
                    "content": record.content,
                    "summary": record.summary,
                    "confidence": record.confidence,
                    "importance": record.importance,
                    "status": record.status.value,
                    "created_at": record.created_at.isoformat(),
                },
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="MEMORY_GET_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class MemorySaveTool(BaseTool):
    """Explicitly save a new durable memory record."""
    name = "memory_save"
    description = "Save a durable user preference, fact, or project decision into persistent memory."
    required_permission = "memory.create"
    args_schema = MemorySaveArgs
    is_read_only = False

    def __init__(self, service: MemoryService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            args = MemorySaveArgs(**arguments)
            create_schema = MemoryCreate(
                category=args.category,
                content=args.content,
                summary=args.summary,
                confidence=args.confidence,
                importance=args.importance,
                source_type="assistant_tool",
                ttl_days=args.ttl_days,
            )
            rec = self.service.save_memory(create_schema)
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={"id": rec.id, "category": rec.category.value, "status": rec.status.value},
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="MEMORY_SAVE_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class MemoryUpdateTool(BaseTool):
    """Update an existing memory record."""
    name = "memory_update"
    description = "Update the content, category, or importance of an existing memory record."
    required_permission = "memory.update"
    args_schema = MemoryUpdateArgs
    is_read_only = False

    def __init__(self, service: MemoryService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            args = MemoryUpdateArgs(**arguments)
            update_data = MemoryUpdate(
                content=args.content,
                summary=args.summary,
                category=args.category,
                confidence=args.confidence,
                importance=args.importance,
                ttl_days=args.ttl_days,
            )
            rec = self.service.repository.update(args.memory_id, update_data)
            if not rec:
                return ToolResult(
                    call_id=call_id,
                    tool_name=self.name,
                    status="error",
                    result=None,
                    error_code="MEMORY_NOT_FOUND",
                    safe_error_message=f"Memory '{args.memory_id}' not found.",
                    verification_status=VerificationStatus.FAILED,
                )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={"id": rec.id, "status": rec.status.value, "updated_at": rec.updated_at.isoformat()},
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="MEMORY_UPDATE_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class MemoryArchiveTool(BaseTool):
    """Archive a memory record so it is excluded from ordinary retrieval."""
    name = "memory_archive"
    description = "Archive an outdated memory record."
    required_permission = "memory.archive"
    args_schema = MemoryArchiveArgs
    is_read_only = False

    def __init__(self, service: MemoryService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            args = MemoryArchiveArgs(**arguments)
            rec = self.service.repository.archive(args.memory_id)
            if not rec:
                return ToolResult(
                    call_id=call_id,
                    tool_name=self.name,
                    status="error",
                    result=None,
                    error_code="MEMORY_NOT_FOUND",
                    safe_error_message=f"Memory '{args.memory_id}' not found.",
                    verification_status=VerificationStatus.FAILED,
                )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={"id": rec.id, "status": rec.status.value},
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="MEMORY_ARCHIVE_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class MemoryDeleteTool(BaseTool):
    """Permanently delete a memory record with confirmation."""
    name = "memory_delete"
    description = "Permanently delete a specific memory record. Requires confirm=true."
    required_permission = "memory.delete"
    args_schema = MemoryDeleteArgs
    is_read_only = False

    def __init__(self, service: MemoryService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            args = MemoryDeleteArgs(**arguments)
            if not args.confirm:
                return ToolResult(
                    call_id=call_id,
                    tool_name=self.name,
                    status="error",
                    result=None,
                    error_code="CONFIRMATION_REQUIRED",
                    safe_error_message="Memory deletion requires explicit confirmation (confirm=True).",
                    verification_status=VerificationStatus.FAILED,
                )
            ok = self.service.repository.delete(args.memory_id)
            if not ok:
                return ToolResult(
                    call_id=call_id,
                    tool_name=self.name,
                    status="error",
                    result=None,
                    error_code="MEMORY_NOT_FOUND",
                    safe_error_message=f"Memory '{args.memory_id}' not found.",
                    verification_status=VerificationStatus.FAILED,
                )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={"id": args.memory_id, "deleted": True},
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="MEMORY_DELETE_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class MemoryListTool(BaseTool):
    """List stored memory records."""
    name = "memory_list"
    description = "List stored memory records with optional category filtering and pagination."
    required_permission = "memory.read"
    args_schema = MemoryListArgs
    is_read_only = True

    def __init__(self, service: MemoryService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            args = MemoryListArgs(**arguments)
            total, items = self.service.repository.list_memories(
                category=args.category,
                limit=args.limit,
                offset=args.offset
            )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={
                    "total": total,
                    "items": [
                        {
                            "id": r.id,
                            "category": r.category.value,
                            "content": r.content,
                            "status": r.status.value,
                            "confidence": r.confidence,
                        }
                        for r in items
                    ],
                },
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                result=None,
                error_code="MEMORY_LIST_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )
