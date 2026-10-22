"""Controlled document export service with path containment checks."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Optional
from app.core.config import Settings, get_settings
from app.core.errors import DocumentAccessDeniedError
from app.file_intelligence.schemas import DocumentExportResponse

logger = logging.getLogger("venora.file_intelligence.export")


class DocumentExportService:
    """Safely writes analysis and summary reports into an explicitly authorized export directory."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def export_content(self, content: str, filename: str, format_type: str = "txt") -> DocumentExportResponse:
        """Write content to safe export directory.
        
        Guards:
        - Path traversal ('..') is stripped.
        - Filename is sanitized.
        - Export directory is verified and contained.
        - Execution flags are never set on generated files.
        """
        export_dir = self.settings.resolved_export_dir
        export_dir.mkdir(parents=True, exist_ok=True)

        clean_name = Path(filename).name
        if not clean_name.endswith(f".{format_type}"):
            clean_name = f"{clean_name}.{format_type}"

        destination = (export_dir / clean_name).resolve()

        # Enforce containment
        try:
            destination.relative_to(export_dir)
        except ValueError:
            raise DocumentAccessDeniedError(str(destination), "Export filename cannot escape the export directory.")

        with open(destination, "w", encoding="utf-8") as f:
            f.write(content)

        file_size = destination.stat().st_size
        logger.info(f"Exported {file_size} bytes to '{destination.name}'")

        return DocumentExportResponse(
            exported_filename=clean_name,
            relative_path=str(destination.name),
            file_size_bytes=file_size,
            created_at=datetime.now(timezone.utc),
        )
