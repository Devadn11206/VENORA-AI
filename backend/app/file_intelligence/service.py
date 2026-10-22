"""High-level document intelligence service coordinating discovery, parsing, chunking, indexing, and AI reasoning."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy.orm import Session

from app.ai.provider import BaseAIProvider
from app.core.config import Settings, get_settings
from app.core.errors import DocumentAccessDeniedError, DocumentNotFoundError
from app.file_intelligence.chunker import DocumentChunker
from app.file_intelligence.export_service import DocumentExportService
from app.file_intelligence.file_access import FileAccessController, SUPPORTED_EXTENSIONS
from app.file_intelligence.index_manager import DocumentIndexManager
from app.file_intelligence.schemas import (
    AuthorizedDirectoryCreate,
    AuthorizedDirectoryResponse,
    DocumentCompareResponse,
    DocumentExtractionResponse,
    DocumentMetadataResponse,
    DocumentQuestionResponse,
    DocumentSearchResponse,
    DocumentSummaryResponse,
    SearchResultItem,
)
from app.file_intelligence.text_extraction import DocumentExtractor
from app.file_intelligence.understanding import DocumentUnderstandingEngine
from app.models.document import (
    AuthorizedDirectory,
    Document,
    DocumentChunk,
    DocumentProcessingStatus,
)

logger = logging.getLogger("venora.file_intelligence.service")


class DocumentIntelligenceService:
    """Coordinates the document lifecycle from registration and extraction to search and understanding."""

    def __init__(
        self,
        db: Session,
        settings: Optional[Settings] = None,
        ai_provider: Optional[BaseAIProvider] = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.file_access = FileAccessController(db=db, settings=self.settings)
        self.extractor = DocumentExtractor(settings=self.settings)
        self.chunker = DocumentChunker(settings=self.settings)
        self.index_manager = DocumentIndexManager(db=db)
        self.understanding = DocumentUnderstandingEngine(provider=ai_provider)
        self.export_service = DocumentExportService(settings=self.settings)

    # -------------------------------------------------------------------------
    # Directory Management
    # -------------------------------------------------------------------------
    def register_authorized_directory(self, request: AuthorizedDirectoryCreate) -> AuthorizedDirectoryResponse:
        """Register a new directory in the authorization allowlist."""
        resolved = Path(request.path).resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise DocumentAccessDeniedError(str(request.path), "Target directory does not exist or is not a folder.")

        existing = self.db.query(AuthorizedDirectory).filter(AuthorizedDirectory.path == str(resolved)).first()
        if existing:
            return AuthorizedDirectoryResponse.model_validate(existing)

        dir_record = AuthorizedDirectory(
            id=str(uuid.uuid4()),
            path=str(resolved),
            label=request.label or resolved.name,
        )
        self.db.add(dir_record)
        self.db.commit()
        self.db.refresh(dir_record)
        logger.info(f"Registered authorized document directory: {resolved}")
        return AuthorizedDirectoryResponse.model_validate(dir_record)

    def list_authorized_directories(self) -> List[AuthorizedDirectoryResponse]:
        """List registered directories."""
        dirs = self.db.query(AuthorizedDirectory).all()
        return [AuthorizedDirectoryResponse.model_validate(d) for d in dirs]

    # -------------------------------------------------------------------------
    # Document Discovery & Registration
    # -------------------------------------------------------------------------
    def scan_authorized_directory(self, directory_id: Optional[str] = None) -> List[DocumentMetadataResponse]:
        """Scan authorized directory, discovering supported documents and registering metadata."""
        # Ensure configured directories are synced into DB
        for conf_dir in self.settings.ALLOWED_DOCUMENT_DIRS:
            try:
                res_path = Path(conf_dir).resolve()
                if res_path.exists() and res_path.is_dir():
                    existing = self.db.query(AuthorizedDirectory).filter(AuthorizedDirectory.path == str(res_path)).first()
                    if not existing:
                        new_dir = AuthorizedDirectory(
                            id=str(uuid.uuid4()),
                            path=str(res_path),
                            label=res_path.name,
                        )
                        self.db.add(new_dir)
                        self.db.commit()
            except Exception as e:
                logger.warning(f"Failed syncing config dir {conf_dir}: {e}")

        query = self.db.query(AuthorizedDirectory)
        if directory_id:
            query = query.filter(AuthorizedDirectory.id == directory_id)
        dirs = query.all()

        discovered: List[DocumentMetadataResponse] = []
        max_files = self.settings.DOCUMENT_MAX_FILES_PER_SCAN

        for auth_dir in dirs:
            root = Path(auth_dir.path)
            if not root.exists():
                continue

            file_count = 0
            for file_path in root.rglob("*"):
                if file_count >= max_files:
                    logger.warning(f"Scan limit ({max_files}) reached for {root}")
                    break

                if not file_path.is_file():
                    continue

                ext = file_path.suffix.lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                file_count += 1
                try:
                    rel_path = str(file_path.relative_to(root))
                    stat = file_path.stat()

                    # Avoid re-hashing oversized files during discovery
                    if stat.st_size > self.settings.DOCUMENT_MAX_FILE_BYTES:
                        continue

                    content_hash = self.file_access.calculate_content_hash(file_path)

                    doc = (
                        self.db.query(Document)
                        .filter(Document.directory_id == auth_dir.id)
                        .filter(Document.relative_path == rel_path)
                        .first()
                    )

                    if not doc:
                        doc = Document(
                            id=str(uuid.uuid4()),
                            directory_id=auth_dir.id,
                            filename=file_path.name,
                            relative_path=rel_path,
                            absolute_path=str(file_path.resolve()),
                            file_type=ext.lstrip("."),
                            file_size_bytes=stat.st_size,
                            content_hash=content_hash,
                            status=DocumentProcessingStatus.DISCOVERED,
                        )
                        self.db.add(doc)
                    else:
                        # Detect modified files
                        if doc.content_hash != content_hash:
                            doc.content_hash = content_hash
                            doc.file_size_bytes = stat.st_size
                            doc.status = DocumentProcessingStatus.STALE

                    self.db.commit()
                    self.db.refresh(doc)
                    discovered.append(self._to_metadata_response(doc))
                except Exception as exc:
                    logger.warning(f"Failed scanning file {file_path}: {exc}")

        return discovered

    def list_documents(
        self,
        directory_id: Optional[str] = None,
        status: Optional[DocumentProcessingStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[DocumentMetadataResponse]:
        """List registered documents with optional filters and pagination."""
        query = self.db.query(Document)
        if directory_id:
            query = query.filter(Document.directory_id == directory_id)
        if status:
            query = query.filter(Document.status == status)

        docs = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()
        return [self._to_metadata_response(d) for d in docs]

    def get_document(self, document_id: str) -> Document:
        """Retrieve Document entity by ID or raise DocumentNotFoundError."""
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError(document_id)
        return doc

    def get_document_metadata(self, document_id: str) -> DocumentMetadataResponse:
        """Return safe metadata for a document."""
        doc = self.get_document(document_id)
        return self._to_metadata_response(doc)

    # -------------------------------------------------------------------------
    # Extraction & Indexing Pipeline
    # -------------------------------------------------------------------------
    def process_and_index_document(self, document_id: str) -> DocumentExtractionResponse:
        """Extract text, chunk content, and update the search index for a document."""
        doc = self.get_document(document_id)
        file_path = Path(doc.absolute_path)

        # 1. Path authorization and constraints
        self.file_access.validate_and_resolve_path(str(file_path))
        self.file_access.validate_file_constraints(file_path)

        doc.status = DocumentProcessingStatus.PROCESSING
        self.db.commit()

        # 2. Text Extraction
        try:
            extraction = self.extractor.extract(file_path)
            doc.page_count = extraction.page_count
            doc.extracted_text = extraction.full_text[:5000]  # Store sample in DB
            doc.last_extracted_at = datetime.now(timezone.utc)
            doc.status = DocumentProcessingStatus.EXTRACTED
            self.db.commit()
        except Exception as exc:
            doc.status = DocumentProcessingStatus.ERROR
            doc.error_summary = str(exc)[:500]
            self.db.commit()
            raise

        # 3. Chunking & Indexing
        try:
            chunks = self.chunker.chunk_document(doc.id, extraction)
            chunks_dict = [c.model_dump() for c in chunks]
            self.index_manager.sync_chunks(doc.id, chunks_dict)

            doc.last_indexed_at = datetime.now(timezone.utc)
            doc.status = DocumentProcessingStatus.INDEXED
            self.db.commit()
        except Exception as exc:
            logger.error(f"Indexing error on document {doc.id}: {exc}")
            doc.status = DocumentProcessingStatus.ERROR
            doc.error_summary = f"Indexing failed: {exc}"[:500]
            self.db.commit()
            raise

        return DocumentExtractionResponse(
            document_id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            page_count=doc.page_count,
            total_characters=extraction.total_characters,
            text_sample=extraction.full_text[:500],
            status=doc.status,
            warnings=extraction.warnings,
        )

    # -------------------------------------------------------------------------
    # Search & Understanding
    # -------------------------------------------------------------------------
    def search_documents(
        self,
        query: str,
        directory_id: Optional[str] = None,
        limit: int = 10,
    ) -> DocumentSearchResponse:
        """Execute full-text lexical search across indexed documents."""
        # Find all authorized document IDs
        q = self.db.query(Document.id).filter(Document.status == DocumentProcessingStatus.INDEXED)
        if directory_id:
            q = q.filter(Document.directory_id == directory_id)
        doc_ids = [row[0] for row in q.all()]

        results = self.index_manager.search(query=query, authorized_doc_ids=doc_ids, limit=limit)
        return DocumentSearchResponse(
            query=query,
            total_matches=len(results),
            results=results,
        )

    async def summarize_document(self, document_id: str, detail_level: str = "standard") -> DocumentSummaryResponse:
        """Summarize document using extracted text chunks."""
        doc = self.get_document(document_id)
        if doc.status not in {DocumentProcessingStatus.EXTRACTED, DocumentProcessingStatus.INDEXED}:
            # Extract on the fly if needed
            self.process_and_index_document(document_id)
            doc = self.get_document(document_id)

        chunks = (
            self.db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )
        return await self.understanding.summarize_document(doc=doc, chunks=chunks, detail_level=detail_level)

    async def ask_question(self, document_id: str, question: str) -> DocumentQuestionResponse:
        """Answer a question about a document grounded in retrieved chunks."""
        doc = self.get_document(document_id)
        if doc.status != DocumentProcessingStatus.INDEXED:
            self.process_and_index_document(document_id)

        # Retrieve relevant chunks via search or chronological top chunks
        search_results = self.index_manager.search(query=question, authorized_doc_ids=[document_id], limit=5)
        matched_chunk_ids = [r.chunk_id for r in search_results]

        if matched_chunk_ids:
            relevant_chunks = (
                self.db.query(DocumentChunk)
                .filter(DocumentChunk.id.in_(matched_chunk_ids))
                .all()
            )
        else:
            relevant_chunks = (
                self.db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document_id)
                .limit(5)
                .all()
            )

        return await self.understanding.answer_question(
            doc=doc,
            question=question,
            relevant_chunks=relevant_chunks
        )

    async def compare_documents(self, doc_a_id: str, doc_b_id: str) -> DocumentCompareResponse:
        """Compare two documents for structural and thematic differences."""
        doc_a = self.get_document(doc_a_id)
        doc_b = self.get_document(doc_b_id)

        for d in [doc_a, doc_b]:
            if d.status != DocumentProcessingStatus.INDEXED:
                self.process_and_index_document(d.id)

        chunks_a = self.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_a_id).limit(10).all()
        chunks_b = self.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_b_id).limit(10).all()

        return await self.understanding.compare_documents(
            doc_a=doc_a,
            chunks_a=chunks_a,
            doc_b=doc_b,
            chunks_b=chunks_b
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _to_metadata_response(self, doc: Document) -> DocumentMetadataResponse:
        return DocumentMetadataResponse(
            document_id=doc.id,
            directory_id=doc.directory_id,
            filename=doc.filename,
            relative_path=doc.relative_path,
            file_type=doc.file_type,
            file_size_bytes=doc.file_size_bytes,
            content_hash=doc.content_hash,
            status=doc.status,
            page_count=doc.page_count,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            last_extracted_at=doc.last_extracted_at,
            last_indexed_at=doc.last_indexed_at,
            error_summary=doc.error_summary,
        )
