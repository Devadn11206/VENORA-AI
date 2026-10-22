"""Comprehensive automated test suite for Phase 5 File Intelligence and Document Understanding."""

import io
import json
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.errors import (
    DocumentAccessDeniedError,
    DocumentNotFoundError,
    DocumentSizeLimitError,
    UnsupportedDocumentTypeError,
)
from app.database.base import Base
from app.database.init_db import init_db
from app.database.session import get_db
from app.desktop.permissions import DesktopPermissionService
from app.file_intelligence.chunker import DocumentChunker
from app.file_intelligence.export_service import DocumentExportService
from app.file_intelligence.file_access import FileAccessController
from app.file_intelligence.index_manager import DocumentIndexManager
from app.file_intelligence.service import DocumentIntelligenceService
from app.file_intelligence.text_extraction import DocumentExtractor
from app.file_intelligence.understanding import DocumentUnderstandingEngine
from app.main import create_app
from app.models.document import AuthorizedDirectory, Document, DocumentChunk, DocumentProcessingStatus


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace directory structure with synthetic test documents."""
    auth_dir = tmp_path / "authorized_docs"
    auth_dir.mkdir(parents=True, exist_ok=True)

    unauth_dir = tmp_path / "unauthorized_docs"
    unauth_dir.mkdir(parents=True, exist_ok=True)

    # 1. Plain text file
    txt_file = auth_dir / "sample.txt"
    txt_file.write_text("VENORA AI is a personal AI desktop assistant.\nIt uses local reasoning and tool orchestration.", encoding="utf-8")

    # 2. Markdown file with headings
    md_file = auth_dir / "notes.md"
    md_file.write_text("# Project Deadlines\nPhase 5 completion is scheduled for October.\n# Team Deliverables\nDeliverables include document intelligence and retrieval.", encoding="utf-8")

    # 3. CSV file
    csv_file = auth_dir / "data.csv"
    csv_file.write_text("id,name,role\n1,Alice,Engineer\n2,Bob,Architect\n", encoding="utf-8")

    # 4. JSON file
    json_file = auth_dir / "config.json"
    json_file.write_text(json.dumps({"project": "VENORA", "version": "0.5.0", "modules": ["desktop", "orchestration", "documents"]}), encoding="utf-8")

    # 5. Unauthorized file
    secret_file = unauth_dir / "passwords.txt"
    secret_file.write_text("SECRET_KEY=123456", encoding="utf-8")

    return {
        "auth_dir": auth_dir,
        "unauth_dir": unauth_dir,
        "txt_file": txt_file,
        "md_file": md_file,
        "csv_file": csv_file,
        "json_file": json_file,
        "secret_file": secret_file,
    }


@pytest.fixture
def doc_db_session(tmp_path):
    """In-memory SQLite database isolated for document tests with schema and FTS5 initialized."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/test_docs.db",
        connect_args={"check_same_thread": False}
    )
    init_db(target_engine=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def doc_settings(temp_workspace):
    """Settings instance pointing explicitly to the authorized test directory."""
    return Settings(
        ALLOWED_DOCUMENT_DIRS=[str(temp_workspace["auth_dir"])],
        DOCUMENT_EXPORT_DIR=str(temp_workspace["auth_dir"] / "exports"),
        DOCUMENT_MAX_FILE_BYTES=1024 * 1024,  # 1 MB
        DOCUMENT_MAX_CHUNK_CHARS=500,
        DOCUMENT_CHUNK_OVERLAP_CHARS=50,
    )


# -----------------------------------------------------------------------------
# 1. File Access & Security Tests
# -----------------------------------------------------------------------------
def test_file_access_authorized_directory(temp_workspace, doc_db_session, doc_settings):
    """Authorized directory access succeeds."""
    fac = FileAccessController(db=doc_db_session, settings=doc_settings)
    resolved = fac.validate_and_resolve_path(str(temp_workspace["txt_file"]))
    assert resolved.exists()
    assert resolved.name == "sample.txt"


def test_file_access_unauthorized_directory_rejected(temp_workspace, doc_db_session, doc_settings):
    """Accessing an unauthorized path raises DocumentAccessDeniedError."""
    fac = FileAccessController(db=doc_db_session, settings=doc_settings)
    with pytest.raises(DocumentAccessDeniedError):
        fac.validate_and_resolve_path(str(temp_workspace["secret_file"]))


def test_file_access_path_traversal_rejected(temp_workspace, doc_db_session, doc_settings):
    """Attempting path traversal ('..') to escape authorized directory is blocked."""
    fac = FileAccessController(db=doc_db_session, settings=doc_settings)
    traversal_path = str(temp_workspace["auth_dir"] / ".." / "unauthorized_docs" / "passwords.txt")
    with pytest.raises(DocumentAccessDeniedError):
        fac.validate_and_resolve_path(traversal_path)


def test_file_access_unsupported_file_type(temp_workspace, doc_db_session, doc_settings):
    """Unsupported file extension raises UnsupportedDocumentTypeError."""
    exe_file = temp_workspace["auth_dir"] / "malicious.exe"
    exe_file.write_bytes(b"\x00\x01\x02")
    fac = FileAccessController(db=doc_db_session, settings=doc_settings)
    with pytest.raises(UnsupportedDocumentTypeError):
        fac.validate_file_constraints(exe_file)


def test_file_access_oversized_file_rejected(temp_workspace, doc_db_session, doc_settings):
    """Oversized file triggers DocumentSizeLimitError."""
    big_file = temp_workspace["auth_dir"] / "huge.txt"
    big_file.write_bytes(b"A" * (1024 * 1024 + 500))  # Exceeds 1 MB
    fac = FileAccessController(db=doc_db_session, settings=doc_settings)
    with pytest.raises(DocumentSizeLimitError):
        fac.validate_file_constraints(big_file)


# -----------------------------------------------------------------------------
# 2. Text Extraction Tests
# -----------------------------------------------------------------------------
def test_text_extraction_plain_text(temp_workspace, doc_settings):
    """Plain text files are extracted cleanly with line counts."""
    extractor = DocumentExtractor(settings=doc_settings)
    res = extractor.extract(temp_workspace["txt_file"])
    assert res.file_type == "txt"
    assert "VENORA AI" in res.full_text
    assert res.page_count == 1


def test_text_extraction_markdown_sections(temp_workspace, doc_settings):
    """Markdown headings are parsed into structural sections."""
    extractor = DocumentExtractor(settings=doc_settings)
    res = extractor.extract(temp_workspace["md_file"])
    assert res.file_type == "md"
    titles = [s.section_title for s in res.sections]
    assert "Project Deadlines" in titles
    assert "Team Deliverables" in titles


def test_text_extraction_csv_tabular(temp_workspace, doc_settings):
    """CSV records are parsed and bounded."""
    extractor = DocumentExtractor(settings=doc_settings)
    res = extractor.extract(temp_workspace["csv_file"])
    assert res.file_type == "csv"
    assert "Alice | Engineer" in res.full_text


def test_text_extraction_json_structure(temp_workspace, doc_settings):
    """JSON files are verified and extracted."""
    extractor = DocumentExtractor(settings=doc_settings)
    res = extractor.extract(temp_workspace["json_file"])
    assert res.file_type == "json"
    assert "orchestration" in res.full_text


# -----------------------------------------------------------------------------
# 3. Chunking & Indexing Tests
# -----------------------------------------------------------------------------
def test_document_chunking_bounds(temp_workspace, doc_settings):
    """Extracted text is partitioned into bounded chunks."""
    extractor = DocumentExtractor(settings=doc_settings)
    res = extractor.extract(temp_workspace["md_file"])
    chunker = DocumentChunker(settings=doc_settings)
    chunks = chunker.chunk_document("doc-1", res)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.document_id == "doc-1"
        assert len(c.content) <= doc_settings.DOCUMENT_MAX_CHUNK_CHARS


def test_document_indexing_and_search(temp_workspace, doc_db_session, doc_settings):
    """Documents are indexed and retrieved via lexical full-text search."""
    service = DocumentIntelligenceService(db=doc_db_session, settings=doc_settings)
    docs = service.scan_authorized_directory()
    assert len(docs) >= 4

    # Find the markdown document
    md_doc = next(d for d in docs if d.filename == "notes.md")
    service.process_and_index_document(md_doc.document_id)

    # Search for "Deadlines"
    search_res = service.search_documents("Deadlines")
    assert search_res.total_matches > 0
    assert "Deadlines" in search_res.results[0].snippet or "Deadlines" in search_res.results[0].section_title


def test_reindex_detects_changed_content(temp_workspace, doc_db_session, doc_settings):
    """Modifying a document updates content hash and status to STALE on scan."""
    service = DocumentIntelligenceService(db=doc_db_session, settings=doc_settings)
    docs = service.scan_authorized_directory()
    txt_meta = next(d for d in docs if d.filename == "sample.txt")

    # Modify file content
    temp_workspace["txt_file"].write_text("Updated new content for VENORA test.", encoding="utf-8")
    rescanned = service.scan_authorized_directory()
    updated_meta = next(d for d in rescanned if d.filename == "sample.txt")

    assert updated_meta.content_hash != txt_meta.content_hash
    assert updated_meta.status == DocumentProcessingStatus.STALE


# -----------------------------------------------------------------------------
# 4. Document Understanding Tests (Summarization & Q&A)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_summarize_document_offline_fallback(temp_workspace, doc_db_session, doc_settings):
    """Summarization works gracefully with deterministic offline fallback when no LLM is configured."""
    service = DocumentIntelligenceService(db=doc_db_session, settings=doc_settings)
    service.scan_authorized_directory()
    txt_doc = service.db.query(Document).filter(Document.filename == "sample.txt").first()

    summary = await service.summarize_document(txt_doc.id)
    assert summary.document_id == txt_doc.id
    assert summary.summary is not None
    assert len(summary.summary) > 10


@pytest.mark.asyncio
async def test_ask_question_returns_citations(temp_workspace, doc_db_session, doc_settings):
    """Q&A provides grounded citations pointing to real document excerpts."""
    service = DocumentIntelligenceService(db=doc_db_session, settings=doc_settings)
    service.scan_authorized_directory()
    md_doc = service.db.query(Document).filter(Document.filename == "notes.md").first()

    qa_resp = await service.ask_question(md_doc.id, "When is completion scheduled?")
    assert qa_resp.document_id == md_doc.id
    assert len(qa_resp.citations) > 0
    assert qa_resp.citations[0].filename == "notes.md"


@pytest.mark.asyncio
async def test_compare_documents(temp_workspace, doc_db_session, doc_settings):
    """Comparing two documents outputs similarities and differences."""
    service = DocumentIntelligenceService(db=doc_db_session, settings=doc_settings)
    service.scan_authorized_directory()
    docs = service.db.query(Document).all()

    comp = await service.compare_documents(docs[0].id, docs[1].id)
    assert len(comp.similarities) > 0 or len(comp.differences) > 0


# -----------------------------------------------------------------------------
# 5. Document Export Tests
# -----------------------------------------------------------------------------
def test_export_document_analysis(temp_workspace, doc_settings):
    """Analysis reports can be exported to authorized output directory."""
    exporter = DocumentExportService(settings=doc_settings)
    resp = exporter.export_content("Summary content: VENORA Phase 5 passed.", "analysis_report", "txt")
    assert resp.exported_filename == "analysis_report.txt"
    assert resp.file_size_bytes > 0

    export_path = Path(doc_settings.DOCUMENT_EXPORT_DIR) / "analysis_report.txt"
    assert export_path.exists()
    assert "VENORA Phase 5" in export_path.read_text(encoding="utf-8")


# -----------------------------------------------------------------------------
# 6. REST API Endpoints Tests
# -----------------------------------------------------------------------------
@pytest.fixture
def doc_api_client(temp_workspace, doc_db_session, doc_settings):
    """FastAPI TestClient with overridden DB and settings for document endpoints."""
    app = create_app()

    def override_get_db():
        try:
            yield doc_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Register test directory into DB
    service = DocumentIntelligenceService(db=doc_db_session, settings=doc_settings)
    from app.file_intelligence.schemas import AuthorizedDirectoryCreate
    service.register_authorized_directory(AuthorizedDirectoryCreate(path=str(temp_workspace["auth_dir"]), label="Test Docs"))

    client = TestClient(app)
    return client


def test_api_list_directories(doc_api_client):
    """GET /api/v1/documents/directories returns registered paths."""
    resp = doc_api_client.get("/api/v1/documents/directories")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "Test Docs" in [d["label"] for d in data]


def test_api_scan_and_list_documents(doc_api_client):
    """POST /api/v1/documents/scan and GET /api/v1/documents."""
    scan_resp = doc_api_client.post("/api/v1/documents/scan")
    assert scan_resp.status_code == 200
    docs = scan_resp.json()
    assert len(docs) >= 4

    list_resp = doc_api_client.get("/api/v1/documents")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 4


def test_api_get_document_metadata_and_extract(doc_api_client):
    """POST /api/v1/documents/{id}/extract and GET /api/v1/documents/{id}."""
    scan_resp = doc_api_client.post("/api/v1/documents/scan")
    doc_id = scan_resp.json()[0]["document_id"]

    extract_resp = doc_api_client.post(f"/api/v1/documents/{doc_id}/extract")
    assert extract_resp.status_code == 200
    extract_data = extract_resp.json()
    assert extract_data["document_id"] == doc_id
    assert extract_data["status"] == "indexed"

    meta_resp = doc_api_client.get(f"/api/v1/documents/{doc_id}")
    assert meta_resp.status_code == 200
    assert meta_resp.json()["document_id"] == doc_id


def test_api_search_documents(doc_api_client):
    """POST /api/v1/documents/search."""
    # Scan and index all
    scan_resp = doc_api_client.post("/api/v1/documents/scan")
    for d in scan_resp.json():
        doc_api_client.post(f"/api/v1/documents/{d['document_id']}/extract")

    search_resp = doc_api_client.post(
        "/api/v1/documents/search",
        json={"query": "assistant", "limit": 5}
    )
    assert search_resp.status_code == 200
    data = search_resp.json()
    assert data["total_matches"] > 0


def test_api_ask_question(doc_api_client):
    """POST /api/v1/documents/{id}/ask."""
    scan_resp = doc_api_client.post("/api/v1/documents/scan")
    doc_id = scan_resp.json()[0]["document_id"]

    ask_resp = doc_api_client.post(
        f"/api/v1/documents/{doc_id}/ask",
        json={"question": "What is this document about?"}
    )
    assert ask_resp.status_code == 200
    data = ask_resp.json()
    assert "answer" in data
    assert "citations" in data


def test_api_export_analysis(doc_api_client):
    """POST /api/v1/documents/export."""
    export_resp = doc_api_client.post(
        "/api/v1/documents/export",
        json={"content": "Analysis text", "filename": "test_export", "format": "txt"}
    )
    assert export_resp.status_code == 201
    assert export_resp.json()["exported_filename"] == "test_export.txt"
