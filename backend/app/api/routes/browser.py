"""API routes for Phase 6 Browser Automation & Web Intelligence."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import get_settings
from app.core.errors import (
    BrowserActionError,
    BrowserSessionError,
    BrowserSessionNotFoundError,
    URLSecurityError,
)
from app.browser.approval import BrowserApprovalPolicy
from app.browser.manager import BrowserManager
from app.browser.research import WebResearchEngine
from app.browser.schemas import (
    BrowserActionRequest,
    BrowserActionResponse,
    BrowserSessionResponse,
    CreateBrowserSessionRequest,
    NavigateRequest,
    PageInspectionResponse,
    WebResearchRequest,
    WebResearchResponse,
    WebSearchRequest,
    WebSearchResponse,
)
from app.browser.search import WebSearchEngine

router = APIRouter(prefix="/browser", tags=["browser"])

# Singleton manager instance for API runtime
_browser_manager: Optional[BrowserManager] = None


def get_browser_manager() -> BrowserManager:
    """Dependency provider returning singleton BrowserManager."""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager(settings=get_settings())
    return _browser_manager


@router.get("/status", summary="Get browser subsystem status")
def get_browser_status(manager: BrowserManager = Depends(get_browser_manager)):
    """Return operational indicators for the browser automation engine."""
    return {
        "status": "ready" if manager.settings.BROWSER_ENABLED else "disabled",
        "headless": manager.settings.BROWSER_HEADLESS,
        "active_sessions": len(manager.sessions),
        "max_sessions": manager.settings.BROWSER_MAX_SESSIONS,
        "allow_http": manager.settings.BROWSER_ALLOW_HTTP,
    }


@router.post(
    "/sessions",
    response_model=BrowserSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an isolated browser session",
)
async def create_session(
    request: CreateBrowserSessionRequest = CreateBrowserSessionRequest(),
    manager: BrowserManager = Depends(get_browser_manager),
):
    """Launch an isolated Playwright browser context."""
    try:
        session = await manager.create_session(headless=request.headless)
        return session.to_response()
    except BrowserSessionError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))


@router.get(
    "/sessions",
    response_model=List[BrowserSessionResponse],
    summary="List active browser sessions",
)
def list_sessions(manager: BrowserManager = Depends(get_browser_manager)):
    """List metadata for active sessions."""
    return manager.list_sessions()


@router.get(
    "/sessions/{session_id}",
    response_model=BrowserSessionResponse,
    summary="Get browser session details",
)
def get_session(session_id: str, manager: BrowserManager = Depends(get_browser_manager)):
    """Get metadata for a specific session."""
    try:
        session = manager.get_session(session_id)
        return session.to_response()
    except BrowserSessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")


@router.post(
    "/sessions/{session_id}/navigate",
    summary="Navigate browser session to URL",
)
async def navigate_session(
    session_id: str,
    request: NavigateRequest,
    manager: BrowserManager = Depends(get_browser_manager),
):
    """Navigate session to a validated URL (SSRF & HTTPS enforced)."""
    try:
        session = manager.get_session(session_id)
        final_url = await session.navigate(request.url)
        return {"session_id": session_id, "url": final_url, "title": session.page_title}
    except BrowserSessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    except URLSecurityError as sec_err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(sec_err))
    except BrowserActionError as act_err:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(act_err))


@router.get(
    "/sessions/{session_id}/page",
    response_model=PageInspectionResponse,
    summary="Inspect current web page",
)
async def inspect_page(
    session_id: str,
    manager: BrowserManager = Depends(get_browser_manager),
):
    """Extract visible page text, headings, and links."""
    try:
        session = manager.get_session(session_id)
        return await session.inspect_page()
    except BrowserSessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")


@router.post(
    "/sessions/{session_id}/actions",
    response_model=BrowserActionResponse,
    summary="Perform a controlled browser action",
)
async def perform_action(
    session_id: str,
    request: BrowserActionRequest,
    manager: BrowserManager = Depends(get_browser_manager),
):
    """Execute click, fill, select, check, or scroll on a page element."""
    try:
        session = manager.get_session(session_id)

        # Check approval requirement for consequential actions
        if BrowserApprovalPolicy.requires_approval(request, session.current_url):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action '{request.action.value}' on target requires explicit user approval before execution."
            )

        return await session.execute_action(request)
    except BrowserSessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    except BrowserActionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/sessions/{session_id}",
    summary="Close browser session",
)
async def close_session(
    session_id: str,
    manager: BrowserManager = Depends(get_browser_manager),
):
    """Terminate session and release Playwright context."""
    await manager.close_session(session_id)
    return {"session_id": session_id, "status": "closed"}


# -----------------------------------------------------------------------------
# Search & Multi-Page Research Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/search",
    response_model=WebSearchResponse,
    summary="Search the web",
)
async def web_search(request: WebSearchRequest):
    """Execute web search query via DuckDuckGo."""
    engine = WebSearchEngine(settings=get_settings())
    return await engine.search(query=request.query, limit=request.limit)


@router.post(
    "/research",
    response_model=WebResearchResponse,
    summary="Conduct multi-page web research",
)
async def web_research(
    request: WebResearchRequest,
    manager: BrowserManager = Depends(get_browser_manager),
):
    """Conduct multi-page web research with grounded citations and synthesis."""
    research_engine = WebResearchEngine(browser_manager=manager, settings=manager.settings)
    return await research_engine.execute_research(query=request.query, max_pages=request.max_pages)
