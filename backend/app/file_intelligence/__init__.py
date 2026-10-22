"""Phase 5 File Intelligence and Document Understanding Package."""

from app.file_intelligence.file_access import FileAccessController, SUPPORTED_EXTENSIONS
from app.file_intelligence.text_extraction import DocumentExtractor, ExtractionResult, ExtractedPageOrSection
from app.file_intelligence.chunker import DocumentChunker, TextChunk
from app.file_intelligence.index_manager import DocumentIndexManager
from app.file_intelligence.understanding import DocumentUnderstandingEngine
from app.file_intelligence.export_service import DocumentExportService
from app.file_intelligence.service import DocumentIntelligenceService

__all__ = [
    "FileAccessController",
    "SUPPORTED_EXTENSIONS",
    "DocumentExtractor",
    "ExtractionResult",
    "ExtractedPageOrSection",
    "DocumentChunker",
    "TextChunk",
    "DocumentIndexManager",
    "DocumentUnderstandingEngine",
    "DocumentExportService",
    "DocumentIntelligenceService",
]
