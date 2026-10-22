"""Document text extraction engine supporting TXT, Markdown, PDF, DOCX, CSV, XLSX, and JSON."""

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.errors import DocumentExtractionError, UnsupportedDocumentTypeError

logger = logging.getLogger("venora.file_intelligence.text_extraction")


class ExtractedPageOrSection(BaseModel):
    """Structured unit of extracted text."""
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    text: str


class ExtractionResult(BaseModel):
    """Complete result from document text extraction."""
    filename: str
    file_type: str
    total_characters: int
    page_count: int
    sections: List[ExtractedPageOrSection]
    full_text: str
    warnings: List[str] = []


class DocumentExtractor:
    """Parses supported file formats and extracts normalized structural text."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text from the given file based on its file extension."""
        ext = file_path.suffix.lower()

        if ext in {".txt", ".md", ".markdown"}:
            return self._extract_text_file(file_path, ext)
        elif ext == ".pdf":
            return self._extract_pdf(file_path)
        elif ext == ".docx":
            return self._extract_docx(file_path)
        elif ext == ".csv":
            return self._extract_csv(file_path)
        elif ext == ".xlsx":
            return self._extract_xlsx(file_path)
        elif ext == ".json":
            return self._extract_json(file_path)
        else:
            raise UnsupportedDocumentTypeError(ext)

    def _extract_text_file(self, file_path: Path, ext: str) -> ExtractionResult:
        """Extract plain text or markdown file with encoding fallback."""
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
        content = None
        used_enc = None

        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    content = f.read()
                    used_enc = enc
                    break
            except (UnicodeDecodeError, Exception):
                continue

        if content is None:
            raise DocumentExtractionError(file_path.name, "Unable to decode text content with standard encodings.")

        # Markdown headings detection for sectioning
        sections: List[ExtractedPageOrSection] = []
        lines = content.splitlines()
        current_section = "Introduction"
        current_lines: List[str] = []

        for line in lines:
            if line.startswith("#"):
                if current_lines:
                    sections.append(ExtractedPageOrSection(
                        section_title=current_section,
                        text="\n".join(current_lines).strip()
                    ))
                    current_lines = []
                current_section = line.lstrip("#").strip() or "Section"
            current_lines.append(line)

        if current_lines:
            sections.append(ExtractedPageOrSection(
                section_title=current_section,
                text="\n".join(current_lines).strip()
            ))

        if not sections:
            sections = [ExtractedPageOrSection(page_number=1, text=content)]

        return ExtractionResult(
            filename=file_path.name,
            file_type=ext.lstrip("."),
            total_characters=len(content),
            page_count=1,
            sections=sections,
            full_text=content,
        )

    def _extract_pdf(self, file_path: Path) -> ExtractionResult:
        """Extract text from PDF page by page using pypdf."""
        try:
            import pypdf
        except ImportError:
            raise DocumentExtractionError(file_path.name, "pypdf library is not installed.")

        sections: List[ExtractedPageOrSection] = []
        full_text_parts: List[str] = []
        warnings: List[str] = []

        try:
            reader = pypdf.PdfReader(str(file_path))
            total_pages = len(reader.pages)
            max_pages = min(total_pages, self.settings.DOCUMENT_MAX_PDF_PAGES)

            if total_pages > self.settings.DOCUMENT_MAX_PDF_PAGES:
                warnings.append(
                    f"PDF has {total_pages} pages; processing was truncated to the limit of {max_pages} pages."
                )

            for page_num in range(1, max_pages + 1):
                page = reader.pages[page_num - 1]
                extracted = page.extract_text() or ""
                clean_text = extracted.strip()
                if clean_text:
                    sections.append(ExtractedPageOrSection(
                        page_number=page_num,
                        section_title=f"Page {page_num}",
                        text=clean_text
                    ))
                    full_text_parts.append(clean_text)

            combined_text = "\n\n".join(full_text_parts)
            return ExtractionResult(
                filename=file_path.name,
                file_type="pdf",
                total_characters=len(combined_text),
                page_count=max_pages,
                sections=sections,
                full_text=combined_text,
                warnings=warnings,
            )
        except Exception as exc:
            raise DocumentExtractionError(file_path.name, f"PDF extraction failed: {exc}")

    def _extract_docx(self, file_path: Path) -> ExtractionResult:
        """Extract paragraphs and tables from DOCX using python-docx."""
        try:
            import docx
        except ImportError:
            raise DocumentExtractionError(file_path.name, "python-docx library is not installed.")

        sections: List[ExtractedPageOrSection] = []
        full_text_parts: List[str] = []

        try:
            doc = docx.Document(str(file_path))
            current_heading = "Document Content"
            current_paras: List[str] = []

            for p in doc.paragraphs:
                text = p.text.strip()
                if not text:
                    continue
                if p.style.name.startswith("Heading"):
                    if current_paras:
                        sections.append(ExtractedPageOrSection(
                            section_title=current_heading,
                            text="\n".join(current_paras)
                        ))
                        current_paras = []
                    current_heading = text
                else:
                    current_paras.append(text)
                    full_text_parts.append(text)

            if current_paras:
                sections.append(ExtractedPageOrSection(
                    section_title=current_heading,
                    text="\n".join(current_paras)
                ))

            # Tables extraction
            for table_idx, table in enumerate(doc.tables, 1):
                table_lines = []
                for row in table.rows:
                    row_data = [cell.text.strip() for cell in row.cells]
                    table_lines.append(" | ".join(row_data))
                if table_lines:
                    table_text = "\n".join(table_lines)
                    sections.append(ExtractedPageOrSection(
                        section_title=f"Table {table_idx}",
                        text=table_text
                    ))
                    full_text_parts.append(table_text)

            combined_text = "\n\n".join(full_text_parts)
            return ExtractionResult(
                filename=file_path.name,
                file_type="docx",
                total_characters=len(combined_text),
                page_count=1,
                sections=sections or [ExtractedPageOrSection(section_title="Content", text=combined_text)],
                full_text=combined_text,
            )
        except Exception as exc:
            raise DocumentExtractionError(file_path.name, f"DOCX extraction failed: {exc}")

    def _extract_csv(self, file_path: Path) -> ExtractionResult:
        """Extract CSV with bounded rows and columns."""
        rows_data: List[str] = []
        warnings: List[str] = []
        max_rows = self.settings.DOCUMENT_MAX_CSV_ROWS

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                for idx, row in enumerate(reader):
                    if idx >= max_rows:
                        warnings.append(f"CSV exceeded maximum limit of {max_rows} rows; truncated.")
                        break
                    rows_data.append(" | ".join(row))

            combined_text = "\n".join(rows_data)
            return ExtractionResult(
                filename=file_path.name,
                file_type="csv",
                total_characters=len(combined_text),
                page_count=1,
                sections=[ExtractedPageOrSection(section_title="Data Rows", text=combined_text)],
                full_text=combined_text,
                warnings=warnings,
            )
        except Exception as exc:
            raise DocumentExtractionError(file_path.name, f"CSV parsing failed: {exc}")

    def _extract_xlsx(self, file_path: Path) -> ExtractionResult:
        """Extract Excel sheets using openpyxl with row bounds."""
        try:
            import openpyxl
        except ImportError:
            raise DocumentExtractionError(file_path.name, "openpyxl library is not installed.")

        sections: List[ExtractedPageOrSection] = []
        full_text_parts: List[str] = []
        warnings: List[str] = []
        max_rows = self.settings.DOCUMENT_MAX_CSV_ROWS

        try:
            wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                sheet_lines: List[str] = []
                row_count = 0
                for row in sheet.iter_rows(values_only=True):
                    row_count += 1
                    if row_count > max_rows:
                        warnings.append(f"Sheet '{sheet_name}' exceeded {max_rows} rows; truncated.")
                        break
                    row_str = " | ".join(str(cell) if cell is not None else "" for cell in row)
                    if any(cell is not None for cell in row):
                        sheet_lines.append(row_str)

                sheet_text = "\n".join(sheet_lines)
                if sheet_text:
                    sections.append(ExtractedPageOrSection(
                        section_title=f"Sheet: {sheet_name}",
                        text=sheet_text
                    ))
                    full_text_parts.append(sheet_text)

            wb.close()
            combined_text = "\n\n".join(full_text_parts)
            return ExtractionResult(
                filename=file_path.name,
                file_type="xlsx",
                total_characters=len(combined_text),
                page_count=len(sections) or 1,
                sections=sections or [ExtractedPageOrSection(section_title="Content", text=combined_text)],
                full_text=combined_text,
                warnings=warnings,
            )
        except Exception as exc:
            raise DocumentExtractionError(file_path.name, f"XLSX extraction failed: {exc}")

    def _extract_json(self, file_path: Path) -> ExtractionResult:
        """Extract JSON document with structural validation."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Check depth
            def get_depth(d, level=1):
                if not isinstance(d, (dict, list)) or not d:
                    return level
                if isinstance(d, dict):
                    return max(get_depth(v, level + 1) for v in d.values())
                return max(get_depth(v, level + 1) for v in d)

            depth = get_depth(data)
            warnings = []
            if depth > self.settings.DOCUMENT_MAX_JSON_DEPTH:
                warnings.append(f"JSON nesting depth ({depth}) exceeds limit ({self.settings.DOCUMENT_MAX_JSON_DEPTH}).")

            formatted_text = json.dumps(data, indent=2)
            return ExtractionResult(
                filename=file_path.name,
                file_type="json",
                total_characters=len(formatted_text),
                page_count=1,
                sections=[ExtractedPageOrSection(section_title="JSON Data", text=formatted_text)],
                full_text=formatted_text,
                warnings=warnings,
            )
        except json.JSONDecodeError as jde:
            raise DocumentExtractionError(file_path.name, f"Malformed JSON: {jde}")
        except Exception as exc:
            raise DocumentExtractionError(file_path.name, f"JSON extraction failed: {exc}")
