"""Tools module export and default registry factory."""

from typing import Optional
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.desktop.service import DesktopService
from app.ai.tools.base import BaseTool
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.desktop_tools import (
    CaptureScreenshotTool,
    DesktopCapabilitiesTool,
    InspectProcessesTool,
    LaunchApplicationTool,
    ListApplicationsTool,
)


from app.ai.tools.document_tools import (
    AskDocumentQuestionTool,
    CompareDocumentsTool,
    ExtractDocumentTextTool,
    ListAuthorizedDocumentsTool,
    SearchDocumentsTool,
    SummarizeDocumentTool,
)
from app.file_intelligence.service import DocumentIntelligenceService


def create_default_tool_registry(
    desktop_service: Optional[DesktopService] = None,
    settings: Optional[Settings] = None,
    db: Optional[Session] = None,
) -> ToolRegistry:
    """Instantiate and populate the standard VENORA AI tool registry with approved desktop and document capabilities."""
    cfg = settings or get_settings()
    svc = desktop_service or DesktopService(db=db, settings=cfg)
    registry = ToolRegistry(permission_service=svc.permissions)

    # Register approved Phase 2 desktop tools
    registry.register(ListApplicationsTool(svc))
    registry.register(LaunchApplicationTool(svc))
    registry.register(InspectProcessesTool(svc))
    registry.register(CaptureScreenshotTool(svc))
    registry.register(DesktopCapabilitiesTool(svc))

    # Register approved Phase 5 document intelligence tools
    if db is not None:
        doc_svc = DocumentIntelligenceService(db=db, settings=cfg)
        registry.register(ListAuthorizedDocumentsTool(doc_svc))
        registry.register(ExtractDocumentTextTool(doc_svc))
        registry.register(SearchDocumentsTool(doc_svc))
        registry.register(SummarizeDocumentTool(doc_svc))
        registry.register(AskDocumentQuestionTool(doc_svc))
        registry.register(CompareDocumentsTool(doc_svc))

    return registry
