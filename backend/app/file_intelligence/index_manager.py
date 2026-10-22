"""Local document indexing and lexical full-text search engine using SQLite FTS5 with standard SQL fallback."""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk, DocumentProcessingStatus
from app.file_intelligence.schemas import SearchResultItem

logger = logging.getLogger("venora.file_intelligence.index")


class DocumentIndexManager:
    """Manages document chunk persistence and search via SQLite FTS5 / SQL queries."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def sync_chunks(self, document_id: str, chunks_data: List[Dict[str, Any]]) -> None:
        """Store chunk records in database and synchronize SQLite FTS5 table."""
        # 1. Clear previous chunks for this document
        self.db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        
        # 2. Clear previous FTS5 entries
        try:
            self.db.execute(
                text("DELETE FROM document_chunks_fts WHERE document_id = :doc_id"),
                {"doc_id": document_id}
            )
        except Exception:
            pass  # FTS5 might not be active

        # 3. Insert new chunk entities
        new_chunks = []
        for c in chunks_data:
            chunk = DocumentChunk(
                id=c["chunk_id"],
                document_id=document_id,
                chunk_index=c["chunk_index"],
                page_number=c.get("page_number"),
                section_title=c.get("section_title"),
                content=c["content"],
                char_count=c["char_count"],
            )
            new_chunks.append(chunk)

        self.db.add_all(new_chunks)
        self.db.flush()

        # 4. Insert into FTS5
        try:
            for c in chunks_data:
                self.db.execute(
                    text(
                        """
                        INSERT INTO document_chunks_fts(chunk_id, document_id, content, section_title)
                        VALUES (:chunk_id, :document_id, :content, :section_title)
                        """
                    ),
                    {
                        "chunk_id": c["chunk_id"],
                        "document_id": document_id,
                        "content": c["content"],
                        "section_title": c.get("section_title") or "",
                    }
                )
        except Exception as fts_err:
            logger.debug(f"FTS5 insertion skipped: {fts_err}")

        self.db.commit()

    def search(
        self,
        query: str,
        authorized_doc_ids: List[str],
        limit: int = 10,
    ) -> List[SearchResultItem]:
        """Search chunks belonging to authorized document IDs.
        
        Attempts SQLite FTS5 BM25 match first; falls back to SQL LIKE if unavailable.
        """
        if not authorized_doc_ids or not query.strip():
            return []

        results: List[SearchResultItem] = []
        clean_query = query.strip()

        # Try FTS5 search
        fts_success = False
        try:
            # Prepare match query
            safe_query = " ".join(f'"{word}"' for word in clean_query.split() if word)
            sql = text(
                """
                SELECT 
                    f.chunk_id,
                    f.document_id,
                    f.section_title,
                    snippet(document_chunks_fts, 2, '<b>', '</b>', '...', 32) as snippet,
                    c.page_number,
                    d.filename,
                    d.relative_path,
                    bm25(document_chunks_fts) as rank
                FROM document_chunks_fts f
                JOIN documents d ON d.id = f.document_id
                JOIN document_chunks c ON c.id = f.chunk_id
                WHERE document_chunks_fts MATCH :query
                  AND f.document_id IN :doc_ids
                ORDER BY rank
                LIMIT :limit
                """
            )
            rows = self.db.execute(
                sql,
                {"query": safe_query, "doc_ids": tuple(authorized_doc_ids), "limit": limit}
            ).fetchall()

            for r in rows:
                results.append(SearchResultItem(
                    chunk_id=r[0],
                    document_id=r[1],
                    section_title=r[2],
                    snippet=r[3],
                    page_number=r[4],
                    filename=r[5],
                    relative_path=r[6],
                    score=float(r[7]) if r[7] is not None else None,
                ))
            fts_success = True
        except Exception as fts_exc:
            logger.debug(f"FTS5 search bypassed ({fts_exc}), executing LIKE fallback.")

        if not fts_success:
            # Fallback to standard LIKE search
            like_query = f"%{clean_query}%"
            chunks = (
                self.db.query(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .filter(DocumentChunk.document_id.in_(authorized_doc_ids))
                .filter(DocumentChunk.content.ilike(like_query))
                .limit(limit)
                .all()
            )

            for chunk, doc in chunks:
                # Simple excerpt
                idx = chunk.content.lower().find(clean_query.lower())
                start = max(0, idx - 50)
                end = min(len(chunk.content), idx + len(clean_query) + 50)
                snippet = f"...{chunk.content[start:end]}..." if idx >= 0 else chunk.content[:100]

                results.append(SearchResultItem(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    filename=doc.filename,
                    relative_path=doc.relative_path,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    snippet=snippet,
                    score=1.0,
                ))

        return results
