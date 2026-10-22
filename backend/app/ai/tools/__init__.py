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
    include_browser: bool = False,
) -> ToolRegistry:
    """Instantiate and populate the standard VENORA AI tool registry with approved desktop, document, and browser capabilities."""
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

    # Register approved Phase 6 browser tools when requested
    if include_browser:
        from app.browser.manager import BrowserManager
        from app.browser.search import WebSearchEngine
        from app.browser.research import WebResearchEngine
        from app.ai.tools.browser_tools import (
            BrowserActionTool,
            BrowserCloseSessionTool,
            BrowserCreateSessionTool,
            BrowserInspectPageTool,
            BrowserNavigateTool,
            WebResearchTool,
            WebSearchTool,
        )
        b_manager = BrowserManager(settings=cfg)
        s_engine = WebSearchEngine(settings=cfg)
        r_engine = WebResearchEngine(browser_manager=b_manager, search_engine=s_engine, settings=cfg)
        registry.register(BrowserCreateSessionTool(b_manager))
        registry.register(BrowserNavigateTool(b_manager))
        registry.register(BrowserInspectPageTool(b_manager))
        registry.register(BrowserActionTool(b_manager))
        registry.register(WebSearchTool(s_engine))
        registry.register(WebResearchTool(r_engine))

    # Register approved Phase 7 memory tools when db session is available
    if db is not None:
        from app.memory.service import MemoryService
        from app.ai.tools.memory_tools import (
            MemorySearchTool,
            MemoryGetTool,
            MemorySaveTool,
            MemoryUpdateTool,
            MemoryArchiveTool,
            MemoryDeleteTool,
            MemoryListTool,
        )
        mem_svc = MemoryService(db=db, settings=cfg)
        registry.register(MemorySearchTool(mem_svc))
        registry.register(MemoryGetTool(mem_svc))
        registry.register(MemorySaveTool(mem_svc))
        registry.register(MemoryUpdateTool(mem_svc))
        registry.register(MemoryArchiveTool(mem_svc))
        registry.register(MemoryDeleteTool(mem_svc))
        registry.register(MemoryListTool(mem_svc))

    return registry
