"""Phase 6 Browser Automation & Web Intelligence Package."""

from app.browser.approval import BrowserApprovalPolicy
from app.browser.manager import BrowserManager
from app.browser.research import WebResearchEngine
from app.browser.schemas import (
    BrowserActionRequest,
    BrowserActionResponse,
    BrowserActionType,
    BrowserSessionResponse,
    BrowserSessionStatus,
    CreateBrowserSessionRequest,
    NavigateRequest,
    PageInspectionResponse,
    WebResearchRequest,
    WebResearchResponse,
    WebSearchRequest,
    WebSearchResponse,
)
from app.browser.search import WebSearchEngine
from app.browser.security import URLSecurityValidator
from app.browser.session import ManagedBrowserSession

__all__ = [
    "BrowserApprovalPolicy",
    "BrowserManager",
    "ManagedBrowserSession",
    "URLSecurityValidator",
    "WebSearchEngine",
    "WebResearchEngine",
    "BrowserActionRequest",
    "BrowserActionResponse",
    "BrowserActionType",
    "BrowserSessionResponse",
    "BrowserSessionStatus",
    "CreateBrowserSessionRequest",
    "NavigateRequest",
    "PageInspectionResponse",
    "WebResearchRequest",
    "WebResearchResponse",
    "WebSearchRequest",
    "WebSearchResponse",
]
