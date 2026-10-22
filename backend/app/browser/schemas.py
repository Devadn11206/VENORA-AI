"""Pydantic v2 schemas for Browser Automation & Web Intelligence."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class BrowserActionType(str, Enum):
    """Supported interactive browser action types."""
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    SCROLL = "scroll"
    SCREENSHOT = "screenshot"
    BACK = "back"
    FORWARD = "forward"


class BrowserSessionStatus(str, Enum):
    """Lifecycle status of a browser session."""
    ACTIVE = "active"
    IDLE = "idle"
    NAVIGATING = "navigating"
    CLOSED = "closed"
    ERROR = "error"


class CreateBrowserSessionRequest(BaseModel):
    """Request schema to create a browser session."""
    headless: Optional[bool] = Field(None, description="Run headless or visible (default: config BROWSER_HEADLESS)")


class BrowserSessionResponse(BaseModel):
    """Metadata response for an active browser session."""
    session_id: str
    status: BrowserSessionStatus
    current_url: Optional[str] = None
    page_title: Optional[str] = None
    created_at: datetime
    last_activity_at: datetime


class NavigateRequest(BaseModel):
    """Request to navigate the browser to a target URL."""
    url: str = Field(..., description="Target web address (HTTPS required)")


class PageHeading(BaseModel):
    """Heading structure extracted from a web page."""
    level: int
    text: str


class PageLink(BaseModel):
    """Link extracted from a web page."""
    label: str
    url: str


class PageInspectionResponse(BaseModel):
    """Bounded, structured content extracted from the current page."""
    session_id: str
    url: str
    title: str
    headings: List[PageHeading] = Field(default_factory=list)
    links: List[PageLink] = Field(default_factory=list)
    text_content: str
    char_count: int
    is_truncated: bool = False


class BrowserActionRequest(BaseModel):
    """Discriminated action schema for safe browser interactions."""
    action: BrowserActionType
    selector: Optional[str] = Field(None, description="Role, accessible label, or CSS selector")
    value: Optional[str] = Field(None, description="Text value to enter or option to select")
    direction: Optional[str] = Field(default="down", description="Scroll direction: 'up' or 'down'")
    distance: Optional[int] = Field(default=500, description="Scroll distance in pixels")


class BrowserActionResponse(BaseModel):
    """Result of an executed browser interaction."""
    session_id: str
    action: BrowserActionType
    success: bool
    resulting_url: str
    resulting_title: Optional[str] = None
    message: Optional[str] = None


class SearchResultItem(BaseModel):
    """Normalized search result item."""
    title: str
    url: str
    snippet: str
    source_provider: str = "duckduckgo"


class WebSearchRequest(BaseModel):
    """Web search query request."""
    query: str = Field(..., min_length=2, max_length=500, description="Search terms")
    limit: int = Field(default=5, ge=1, le=10, description="Number of results")


class WebSearchResponse(BaseModel):
    """Web search response."""
    query: str
    total_results: int
    results: List[SearchResultItem]


class WebResearchRequest(BaseModel):
    """Multi-page web research request."""
    query: str = Field(..., min_length=3, max_length=500, description="Research topic or question")
    max_pages: int = Field(default=3, ge=1, le=5, description="Maximum pages to inspect")


class ResearchSource(BaseModel):
    """A visited source in a multi-page research task."""
    title: str
    url: str
    excerpt: str


class WebResearchResponse(BaseModel):
    """Synthesized research output."""
    query: str
    summary: str
    sources: List[ResearchSource]
    pages_visited: int
