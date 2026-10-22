"""Document chunking engine with structural boundary preservation and configurable overlap."""

import uuid
from typing import List, Optional
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.file_intelligence.text_extraction import ExtractedPageOrSection, ExtractionResult


class TextChunk(BaseModel):
    """Normalized chunk of text ready for indexing or QA retrieval."""
    chunk_id: str
    document_id: str
    chunk_index: int
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    content: str
    char_count: int


class DocumentChunker:
    """Splits extracted document sections into bounded, overlapping chunks."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.max_chunk_chars = self.settings.DOCUMENT_MAX_CHUNK_CHARS
        self.overlap_chars = self.settings.DOCUMENT_CHUNK_OVERLAP_CHARS

    def chunk_document(self, document_id: str, extraction: ExtractionResult) -> List[TextChunk]:
        """Convert an extraction result into an ordered sequence of TextChunk instances."""
        chunks: List[TextChunk] = []
        chunk_idx = 0

        for section in extraction.sections:
            text = section.text.strip()
            if not text:
                continue

            if len(text) <= self.max_chunk_chars:
                chunks.append(TextChunk(
                    chunk_id=str(uuid.uuid4()),
                    document_id=document_id,
                    chunk_index=chunk_idx,
                    page_number=section.page_number,
                    section_title=section.section_title,
                    content=text,
                    char_count=len(text)
                ))
                chunk_idx += 1
            else:
                # Split along paragraphs or sentences
                paragraphs = text.split("\n\n")
                current_block: List[str] = []
                current_len = 0

                for p in paragraphs:
                    p_clean = p.strip()
                    if not p_clean:
                        continue

                    if current_len + len(p_clean) > self.max_chunk_chars and current_block:
                        joined = "\n\n".join(current_block)
                        chunks.append(TextChunk(
                            chunk_id=str(uuid.uuid4()),
                            document_id=document_id,
                            chunk_index=chunk_idx,
                            page_number=section.page_number,
                            section_title=section.section_title,
                            content=joined,
                            char_count=len(joined)
                        ))
                        chunk_idx += 1

                        # Carry over overlap
                        if self.overlap_chars > 0 and len(joined) > self.overlap_chars:
                            overlap_text = joined[-self.overlap_chars:]
                            current_block = [overlap_text, p_clean]
                            current_len = len(overlap_text) + len(p_clean)
                        else:
                            current_block = [p_clean]
                            current_len = len(p_clean)
                    else:
                        current_block.append(p_clean)
                        current_len += len(p_clean)

                if current_block:
                    joined = "\n\n".join(current_block)
                    chunks.append(TextChunk(
                        chunk_id=str(uuid.uuid4()),
                        document_id=document_id,
                        chunk_index=chunk_idx,
                        page_number=section.page_number,
                        section_title=section.section_title,
                        content=joined,
                        char_count=len(joined)
                    ))
                    chunk_idx += 1

        return chunks
