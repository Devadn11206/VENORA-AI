"""API endpoints for Phase 5 File Intelligence & Document Understanding."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.errors import DocumentAccessDeniedError, DocumentNotFoundError, DocumentSizeLimitError, UnsupportedDocumentTypeError
from app.file_intelligence.schemas import (
    AuthorizedDirectoryCreate,
    AuthorizedDirectoryResponse,
    DocumentCompareRequest,
    DocumentCompareResponse,
    DocumentExportRequest,
    DocumentExportResponse,
    DocumentExtractionResponse,
    DocumentMetadataResponse,
    DocumentQuestionRequest,
    DocumentQuestionResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentSummaryRequest,
    DocumentSummaryResponse,
)
from app.file_intelligence.service import DocumentIntelligenceService
from app.models.document import DocumentProcessingStatus

router = APIRouter(prefix="/documents", tags=["documents"])


def get_doc_service(db: Session = Depends(get_db)) -> DocumentIntelligenceService:
    """Dependency provider for DocumentIntelligenceService."""
    return DocumentIntelligenceService(db=db)


# -----------------------------------------------------------------------------
# Directory Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/directories",
    response_model=AuthorizedDirectoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an authorized document directory",
)
def register_directory(
    request: AuthorizedDirectoryCreate,
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """Explicitly authorize a local directory root for document discovery."""
    try:
        return service.register_authorized_directory(request)
    except DocumentAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/directories",
    response_model=List[AuthorizedDirectoryResponse],
    summary="List authorized document directories",
)
def list_directories(
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """List all directories currently permitted for document scanning."""
    return service.list_authorized_directories()


@router.post(
    "/scan",
    response_model=List[DocumentMetadataResponse],
    summary="Scan authorized directory for supported documents",
)
def scan_documents(
    directory_id: Optional[str] = Query(None, description="Optional directory ID filter"),
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """Scan authorized directories, discovering new and detecting modified documents."""
    return service.scan_authorized_directory(directory_id=directory_id)


# -----------------------------------------------------------------------------
# Document Queries & Metadata
# -----------------------------------------------------------------------------
@router.get(
    "",
    response_model=List[DocumentMetadataResponse],
    summary="List discovered and indexed documents",
)
def list_documents(
    directory_id: Optional[str] = Query(None, description="Filter by directory ID"),
    doc_status: Optional[DocumentProcessingStatus] = Query(None, alias="status", description="Filter by processing status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """Paginated list of registered documents."""
    return service.list_documents(directory_id=directory_id, status=doc_status, limit=limit, offset=offset)


@router.get(
    "/{document_id}",
    response_model=DocumentMetadataResponse,
    summary="Get document metadata",
)
def get_document_metadata(
    document_id: str,
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """Retrieve metadata for a specific document without exposing sensitive paths."""
    try:
        return service.get_document_metadata(document_id)
    except DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found.")


# -----------------------------------------------------------------------------
# Processing, Extraction & Indexing
# -----------------------------------------------------------------------------
@router.post(
    "/{document_id}/extract",
    response_model=DocumentExtractionResponse,
    summary="Extract text and index document",
)
def extract_document(
    document_id: str,
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """Extract text from the document, decompose into chunks, and store in search index."""
    try:
        return service.process_and_index_document(document_id)
    except DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found.")
    except DocumentAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (DocumentSizeLimitError, UnsupportedDocumentTypeError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# -----------------------------------------------------------------------------
# Search & Understanding
# -----------------------------------------------------------------------------
@router.post(
    "/search",
    response_model=DocumentSearchResponse,
    summary="Full-text lexical search across indexed documents",
)
def search_documents(
    request: DocumentSearchRequest,
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """Search for relevant chunks across authorized documents with match snippets."""
    return service.search_documents(
        query=request.query,
        directory_id=request.directory_id,
        limit=request.limit,
    )


@router.post(
    "/{document_id}/summarize",
    response_model=DocumentSummaryResponse,
    summary="Summarize document",
)
async def summarize_document(
    document_id: str,
    request: DocumentSummaryRequest = DocumentSummaryRequest(),
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """Generate a grounded summary of the document with source citations."""
    try:
        return await service.summarize_document(
            document_id=document_id,
            detail_level=request.detail_level,
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found.")


@router.post(
    "/{document_id}/ask",
    response_model=DocumentQuestionResponse,
    summary="Ask a question about a document",
)
async def ask_document_question(
    document_id: str,
    request: DocumentQuestionRequest,
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """Answer questions grounded in document text with specific page/section citations."""
    try:
        return await service.ask_question(
            document_id=document_id,
            question=request.question,
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found.")


@router.post(
    "/compare",
    response_model=DocumentCompareResponse,
    summary="Compare two documents",
)
async def compare_documents(
    request: DocumentCompareRequest,
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """Compare two documents for content similarities and differences."""
    try:
        return await service.compare_documents(
            doc_a_id=request.document_ids[0],
            doc_b_id=request.document_ids[1],
        )
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/export",
    response_model=DocumentExportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Export analysis or summary to safe output directory",
)
def export_document_analysis(
    request: DocumentExportRequest,
    service: DocumentIntelligenceService = Depends(get_doc_service),
):
    """Safely write analysis content to the export directory."""
    try:
        return service.export_service.export_content(
            content=request.content,
            filename=request.filename,
            format_type=request.format,
        )
    except DocumentAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
