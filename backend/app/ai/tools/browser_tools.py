"""Controlled Phase 6 Browser & Web Intelligence tools registered on ToolRegistry."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.ai.schemas import ToolResult
from app.ai.tools.base import BaseTool
from app.desktop.schemas import VerificationStatus
from app.browser.manager import BrowserManager
from app.browser.research import WebResearchEngine
from app.browser.schemas import (
    BrowserActionRequest,
    BrowserActionType,
    NavigateRequest,
)
from app.browser.search import WebSearchEngine


# -----------------------------------------------------------------------------
# Arguments Schemas
# -----------------------------------------------------------------------------
class CreateBrowserSessionArgs(BaseModel):
    headless: Optional[bool] = Field(None, description="Run headless or visible")


class NavigateArgs(BaseModel):
    session_id: str = Field(..., description="Active browser session ID")
    url: str = Field(..., description="Target HTTPS web address")


class InspectPageArgs(BaseModel):
    session_id: str = Field(..., description="Active browser session ID")


class BrowserActionArgs(BaseModel):
    session_id: str = Field(..., description="Active browser session ID")
    action: BrowserActionType = Field(..., description="Action to perform: click, fill, select, scroll, screenshot, back, forward")
    selector: Optional[str] = Field(None, description="CSS selector, accessible role (e.g. role=button:Submit), or text (e.g. text=Login)")
    value: Optional[str] = Field(None, description="Text value to enter or option to choose")
    direction: Optional[str] = Field(default="down", description="Scroll direction: 'up' or 'down'")
    distance: Optional[int] = Field(default=500, description="Scroll distance in pixels")


class CloseBrowserSessionArgs(BaseModel):
    session_id: str = Field(..., description="Browser session ID to terminate")


class WebSearchArgs(BaseModel):
    query: str = Field(..., min_length=2, max_length=500, description="Search terms")
    limit: int = Field(default=5, ge=1, le=10, description="Max results")


class WebResearchArgs(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, description="Topic or research question")
    max_pages: int = Field(default=3, ge=1, le=5, description="Max web pages to inspect")


# -----------------------------------------------------------------------------
# Tool Implementations
# -----------------------------------------------------------------------------
class BrowserCreateSessionTool(BaseTool):
    """Tool to create an isolated browser session."""
    name = "browser_create_session"
    description = "Create an isolated, application-managed browser session."
    args_schema = CreateBrowserSessionArgs
    required_permission = "browser.session.create"
    is_read_only = False

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            sess = await self.manager.create_session(headless=arguments.get("headless"))
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=sess.to_response().model_dump(mode="json"),
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="SESSION_CREATE_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class BrowserNavigateTool(BaseTool):
    """Tool to navigate an active session to a validated URL."""
    name = "browser_navigate"
    description = "Navigate an active browser session to a validated HTTPS URL."
    args_schema = NavigateArgs
    required_permission = "browser.navigate"
    is_read_only = False

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            sess = self.manager.get_session(arguments["session_id"])
            final_url = await sess.navigate(arguments["url"])
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={"session_id": sess.session_id, "url": final_url, "title": sess.page_title},
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="NAVIGATE_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class BrowserInspectPageTool(BaseTool):
    """Tool to inspect current page content, title, headings, and links."""
    name = "browser_inspect_page"
    description = "Inspect the active page in a browser session, returning headings, links, and visible text."
    args_schema = InspectPageArgs
    required_permission = "browser.page.inspect"
    is_read_only = True

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            sess = self.manager.get_session(arguments["session_id"])
            data = await sess.inspect_page()
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=data.model_dump(mode="json"),
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="INSPECT_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class BrowserActionTool(BaseTool):
    """Tool to perform controlled interactions on an active page."""
    name = "browser_action"
    description = "Execute an interaction (click, fill, select, check, scroll, back, forward) on a page."
    args_schema = BrowserActionArgs
    required_permission = "browser.interact.click"
    is_read_only = False

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            sess = self.manager.get_session(arguments["session_id"])
            req = BrowserActionRequest(
                action=arguments["action"],
                selector=arguments.get("selector"),
                value=arguments.get("value"),
                direction=arguments.get("direction", "down"),
                distance=arguments.get("distance", 500),
            )
            res = await sess.execute_action(req)
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=res.model_dump(mode="json"),
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="ACTION_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class BrowserCloseSessionTool(BaseTool):
    """Tool to close an active browser session."""
    name = "browser_close_session"
    description = "Close an application-managed browser session."
    args_schema = CloseBrowserSessionArgs
    required_permission = "browser.session.close"
    is_read_only = False

    def __init__(self, manager: BrowserManager) -> None:
        self.manager = manager

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            await self.manager.close_session(arguments["session_id"])
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result={"session_id": arguments["session_id"], "status": "closed"},
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="CLOSE_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class WebSearchTool(BaseTool):
    """Tool to query DuckDuckGo web search."""
    name = "web_search"
    description = "Search the web for up-to-date information."
    args_schema = WebSearchArgs
    required_permission = "browser.search"
    is_read_only = True

    def __init__(self, search_engine: WebSearchEngine) -> None:
        self.search_engine = search_engine

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            resp = await self.search_engine.search(
                query=arguments["query"],
                limit=arguments.get("limit", 5),
            )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=resp.model_dump(mode="json"),
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="SEARCH_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )


class WebResearchTool(BaseTool):
    """Tool to execute multi-page research and grounded synthesis."""
    name = "web_research"
    description = "Conduct multi-page web research across credible sources and produce a grounded summary."
    args_schema = WebResearchArgs
    required_permission = "browser.research"
    is_read_only = True

    def __init__(self, research_engine: WebResearchEngine) -> None:
        self.research_engine = research_engine

    async def execute(self, call_id: str, arguments: Dict[str, Any]) -> ToolResult:
        try:
            res = await self.research_engine.execute_research(
                query=arguments["query"],
                max_pages=arguments.get("max_pages", 3),
            )
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="success",
                result=res.model_dump(mode="json"),
                verification_status=VerificationStatus.VERIFIED,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                status="error",
                error_code="RESEARCH_ERROR",
                safe_error_message=str(exc),
                verification_status=VerificationStatus.FAILED,
            )
