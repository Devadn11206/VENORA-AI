"""Pydantic v2 schemas for Document Intelligence & Understanding."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.document import DocumentProcessingStatus


class AuthorizedDirectoryCreate(BaseModel):
    """Request schema for registering an authorized directory."""
    path: str = Field(..., description="Absolute path of the directory to authorize")
    label: Optional[str] = Field(None, description="Optional friendly label for the directory")


class AuthorizedDirectoryResponse(BaseModel):
    """Response schema for an authorized directory."""
    id: str
    path: str
    label: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentMetadataResponse(BaseModel):
    """Metadata response for a registered document (safe, without leaking sensitive paths)."""
    document_id: str
    directory_id: str
    filename: str
    relative_path: str
    file_type: str
    file_size_bytes: int
    content_hash: str
    status: DocumentProcessingStatus
    page_count: int
    created_at: datetime
    updated_at: datetime
    last_extracted_at: Optional[datetime] = None
    last_indexed_at: Optional[datetime] = None
    error_summary: Optional[str] = None

    model_config = {"from_attributes": True}


class DocumentChunkResponse(BaseModel):
    """Schema for an extracted text chunk."""
    chunk_id: str
    document_id: str
    chunk_index: int
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    content: str
    char_count: int

    model_config = {"from_attributes": True}


class DocumentExtractionResponse(BaseModel):
    """Response for extracted text from a document."""
    document_id: str
    filename: str
    file_type: str
    page_count: int
    total_characters: int
    text_sample: str
    status: DocumentProcessingStatus
    warnings: List[str] = Field(default_factory=list)


class DocumentSummaryRequest(BaseModel):
    """Request schema for summarizing a document."""
    detail_level: str = Field(default="standard", description="Summary detail level: brief, standard, or detailed")


class DocumentSummaryResponse(BaseModel):
    """Response schema for document summary."""
    document_id: str
    filename: str
    detail_level: str
    summary: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    extraction_status: DocumentProcessingStatus


class DocumentSearchRequest(BaseModel):
    """Search query across authorized indexed documents."""
    query: str = Field(..., min_length=1, max_length=500, description="Search terms")
    directory_id: Optional[str] = Field(None, description="Optional directory ID filter")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results to return")


class SearchResultItem(BaseModel):
    """Individual search match item."""
    chunk_id: str
    document_id: str
    filename: str
    relative_path: str
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    snippet: str
    score: Optional[float] = None


class DocumentSearchResponse(BaseModel):
    """Search results response."""
    query: str
    total_matches: int
    results: List[SearchResultItem]


class DocumentQuestionRequest(BaseModel):
    """Question answering request against a document."""
    question: str = Field(..., min_length=2, max_length=1000, description="User question")


class SourceCitation(BaseModel):
    """Source citation reference supporting an answer."""
    document_id: str
    filename: str
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    excerpt: str


class DocumentQuestionResponse(BaseModel):
    """Question answering response with citations."""
    document_id: str
    question: str
    answer: str
    evidence_sufficient: bool
    citations: List[SourceCitation]


class DocumentCompareRequest(BaseModel):
    """Request to compare two authorized documents."""
    document_ids: List[str] = Field(..., min_length=2, max_length=2, description="Exactly two document IDs to compare")


class DocumentCompareResponse(BaseModel):
    """Comparison response identifying similarities and differences."""
    document_a_id: str
    document_b_id: str
    document_a_name: str
    document_b_name: str
    similarities: List[str]
    differences: List[str]
    citations: List[SourceCitation] = Field(default_factory=list)


class DocumentExportRequest(BaseModel):
    """Request schema to export analysis or summary to an authorized file."""
    content: str = Field(..., min_length=1, description="Content to export")
    filename: str = Field(..., min_length=1, max_length=100, description="Destination filename")
    format: str = Field(default="txt", description="Format: txt, md, or json")


class DocumentExportResponse(BaseModel):
    """Response schema for exported document file."""
    exported_filename: str
    relative_path: str
    file_size_bytes: int
    created_at: datetime
