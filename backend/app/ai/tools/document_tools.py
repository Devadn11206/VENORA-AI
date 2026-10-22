"""Controlled Phase 5 Document Intelligence tools registered on ToolRegistry."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.ai.schemas import ToolResult
from app.ai.tools.base import BaseTool
from app.desktop.schemas import VerificationStatus
from app.file_intelligence.service import DocumentIntelligenceService


# -----------------------------------------------------------------------------
# Tool Arguments Schemas
# -----------------------------------------------------------------------------
class ListDocumentsArgs(BaseModel):
    directory_id: Optional[str] = Field(None, description="Optional authorized directory ID filter")
    limit: int = Field(default=20, ge=1, le=100, description="Max documents to return")


class ExtractDocumentTextArgs(BaseModel):
    document_id: str = Field(..., description="ID of the authorized document to extract")


class SearchDocumentsArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search query string")
    directory_id: Optional[str] = Field(None, description="Optional directory ID to constrain search")
    limit: int = Field(default=5, ge=1, le=20, description="Max search results to return")


class SummarizeDocumentArgs(BaseModel):
    document_id: str = Field(..., description="ID of the authorized document to summarize")
    detail_level: str = Field(default="standard", description="Summary detail: brief, standard, or detailed")


class AskDocumentQuestionArgs(BaseModel):
    document_id: str = Field(..., description="ID of the authorized document to inspect")
    question: str = Field(..., min_length=2, max_length=1000, description="Question about the document")


class CompareDocumentsArgs(BaseModel):
    document_a_id: str = Field(..., description="First document ID to compare")
    document_b_id: str = Field(..., description="Second document ID to compare")


# -----------------------------------------------------------------------------
# Tool Implementations
# -----------------------------------------------------------------------------
class ListAuthorizedDocumentsTool(BaseTool):
    """Tool to discover and list documents in authorized directories."""
    name = "list_authorized_documents"
    description = "List supported files and documents within authorized local directories."
    args_schema = ListDocumentsArgs
    required_permission = "document.read"
    is_read_only = True

    def __init__(self, service: DocumentIntelligenceService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            self.service.scan_authorized_directory(arguments.get("directory_id"))
            docs = self.service.list_documents(
                directory_id=arguments.get("directory_id"),
                limit=arguments.get("limit", 20)
            )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=[d.model_dump(mode="json") for d in docs],
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="DOCUMENT_LIST_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class ExtractDocumentTextTool(BaseTool):
    """Tool to extract text and structure from an authorized document."""
    name = "extract_document_text"
    description = "Extract text and structural pages from an authorized document."
    args_schema = ExtractDocumentTextArgs
    required_permission = "document.extract"
    is_read_only = False

    def __init__(self, service: DocumentIntelligenceService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            resp = self.service.process_and_index_document(arguments["document_id"])
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=resp.model_dump(mode="json"),
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="EXTRACTION_FAILED",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class SearchDocumentsTool(BaseTool):
    """Tool to search indexed documents using lexical full-text search."""
    name = "search_documents"
    description = "Search across authorized and indexed documents for relevant content."
    args_schema = SearchDocumentsArgs
    required_permission = "document.search"
    is_read_only = True

    def __init__(self, service: DocumentIntelligenceService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            results = self.service.search_documents(
                query=arguments["query"],
                directory_id=arguments.get("directory_id"),
                limit=arguments.get("limit", 5),
            )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=results.model_dump(mode="json"),
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="SEARCH_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class SummarizeDocumentTool(BaseTool):
    """Tool to summarize an authorized document."""
    name = "summarize_document"
    description = "Generate a grounded summary of an authorized document."
    args_schema = SummarizeDocumentArgs
    required_permission = "document.summarize"
    is_read_only = True

    def __init__(self, service: DocumentIntelligenceService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            summary = await self.service.summarize_document(
                document_id=arguments["document_id"],
                detail_level=arguments.get("detail_level", "standard"),
            )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=summary.model_dump(mode="json"),
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="SUMMARIZE_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class AskDocumentQuestionTool(BaseTool):
    """Tool to ask a question about an authorized document and retrieve supporting citations."""
    name = "ask_document_question"
    description = "Ask a question about a document and retrieve grounded answers with citations."
    args_schema = AskDocumentQuestionArgs
    required_permission = "document.read"
    is_read_only = True

    def __init__(self, service: DocumentIntelligenceService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            ans = await self.service.ask_question(
                document_id=arguments["document_id"],
                question=arguments["question"],
            )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=ans.model_dump(mode="json"),
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="QUESTION_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class CompareDocumentsTool(BaseTool):
    """Tool to compare two authorized documents."""
    name = "compare_documents"
    description = "Compare two authorized documents and identify similarities, differences, and citations."
    args_schema = CompareDocumentsArgs
    required_permission = "document.compare"
    is_read_only = True

    def __init__(self, service: DocumentIntelligenceService) -> None:
        self.service = service

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            comp = await self.service.compare_documents(
                doc_a_id=arguments["document_a_id"],
                doc_b_id=arguments["document_b_id"],
            )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=comp.model_dump(mode="json"),
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="COMPARE_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )
