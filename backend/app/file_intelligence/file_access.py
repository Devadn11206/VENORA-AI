"""Security-first file access controller enforcing authorized directories, containment, and path safety."""

import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Set
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    DocumentAccessDeniedError,
    DocumentSizeLimitError,
    UnsupportedDocumentTypeError,
)
from app.models.document import AuthorizedDirectory

logger = logging.getLogger("venora.file_intelligence.file_access")

SUPPORTED_EXTENSIONS: Set[str] = {
    ".txt",
    ".md",
    ".markdown",
    ".pdf",
    ".docx",
    ".csv",
    ".xlsx",
    ".json",
}


class FileAccessController:
    """Enforces strict path containment, format validation, and resource bounds on local documents."""

    def __init__(self, db: Optional[Session] = None, settings: Optional[Settings] = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def get_authorized_directory_paths(self) -> List[Path]:
        """Collect authorized directories from configuration and persistent database registrations."""
        paths: List[Path] = []
        # 1. Configured allowlist paths from settings
        for p in self.settings.ALLOWED_DOCUMENT_DIRS:
            try:
                resolved = Path(p).resolve()
                if resolved.exists() and resolved.is_dir():
                    paths.append(resolved)
            except Exception as e:
                logger.warning(f"Invalid configured document dir '{p}': {e}")

        # 2. Database registered directories
        if self.db:
            try:
                dirs = self.db.query(AuthorizedDirectory).all()
                for d in dirs:
                    try:
                        resolved = Path(d.path).resolve()
                        if resolved.exists() and resolved.is_dir() and resolved not in paths:
                            paths.append(resolved)
                    except Exception as e:
                        logger.warning(f"Invalid database document dir '{d.path}': {e}")
            except Exception as exc:
                logger.warning(f"Error querying AuthorizedDirectory table: {exc}")

        return paths

    def validate_and_resolve_path(self, target_path: str) -> Path:
        """Resolve path and verify that it strictly resides within an authorized directory.
        
        Rejects:
        - Path traversal ('..')
        - Symbolic link escapes outside authorized roots
        - Windows device paths ('COM1', 'NUL', etc.)
        - Paths not enclosed within at least one authorized directory root
        """
        if not target_path or not target_path.strip():
            raise DocumentAccessDeniedError(target_path, "Path cannot be empty.")

        # Clean and resolve
        raw_path = Path(target_path.strip())
        try:
            resolved = raw_path.resolve(strict=False)
        except Exception as exc:
            raise DocumentAccessDeniedError(str(target_path), f"Failed to resolve path: {exc}")

        # Verify against authorized roots
        authorized_roots = self.get_authorized_directory_paths()
        if not authorized_roots:
            raise DocumentAccessDeniedError(
                str(target_path),
                "No authorized document directories configured. Access denied by default policy."
            )

        matched_root = None
        for root in authorized_roots:
            try:
                # True containment check (resolves symlinks and ensures containment)
                resolved.relative_to(root)
                matched_root = root
                break
            except ValueError:
                continue

        if not matched_root:
            raise DocumentAccessDeniedError(
                str(resolved),
                f"Path is outside all authorized document directories ({[str(r) for r in authorized_roots]})."
            )

        return resolved

    def validate_file_constraints(self, file_path: Path) -> None:
        """Validate existence, extension, and file size limits."""
        if not file_path.exists():
            raise DocumentAccessDeniedError(str(file_path), "File does not exist.")

        if not file_path.is_file():
            raise DocumentAccessDeniedError(str(file_path), "Target is a directory or special device file, not a regular file.")

        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise UnsupportedDocumentTypeError(ext or "unknown")

        stat = file_path.stat()
        if stat.st_size > self.settings.DOCUMENT_MAX_FILE_BYTES:
            raise DocumentSizeLimitError(stat.st_size, self.settings.DOCUMENT_MAX_FILE_BYTES)

    @staticmethod
    def calculate_content_hash(file_path: Path) -> str:
        """Calculate SHA-256 hash of file content in streaming blocks."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()
