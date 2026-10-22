"""Comprehensive test suite for Phase 6 Browser Automation & Web Intelligence."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.core.config import Settings
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
    BrowserActionType,
    BrowserSessionStatus,
    PageHeading,
    PageInspectionResponse,
    PageLink,
    SearchResultItem,
    WebSearchResponse,
)
from app.browser.search import WebSearchEngine
from app.browser.security import URLSecurityValidator
from app.browser.session import ManagedBrowserSession
from app.main import create_app


# -----------------------------------------------------------------------------
# 1. URL Security & Anti-SSRF Tests
# -----------------------------------------------------------------------------
def test_valid_https_url_accepted():
    """Valid public HTTPS URLs are permitted."""
    validator = URLSecurityValidator(settings=Settings())
    assert validator.validate_url("https://www.python.org") == "https://www.python.org"
    assert validator.validate_url("https://fastapi.tiangolo.com/tutorial/") == "https://fastapi.tiangolo.com/tutorial/"


def test_insecure_http_rejected_by_default():
    """Insecure HTTP URLs are rejected when BROWSER_ALLOW_HTTP is false."""
    validator = URLSecurityValidator(settings=Settings(BROWSER_ALLOW_HTTP=False))
    with pytest.raises(URLSecurityError) as exc_info:
        validator.validate_url("http://example.com")
    assert "HTTPS is required" in str(exc_info.value)


def test_disallowed_schemes_rejected():
    """Dangerous URL schemes are blocked."""
    validator = URLSecurityValidator(settings=Settings())
    for bad_scheme in ["file:///C:/Windows/win.ini", "javascript:alert(1)", "data:text/html,<h1>PWN</h1>", "about:blank"]:
        with pytest.raises(URLSecurityError):
            validator.validate_url(bad_scheme)


def test_anti_ssrf_loopback_and_metadata_blocked():
    """Loopback addresses, private IPs, and cloud metadata endpoints are strictly blocked."""
    validator = URLSecurityValidator(settings=Settings())
    blocked_targets = [
        "https://localhost:8000/api/v1/health",
        "https://127.0.0.1:8000/docs",
        "https://169.254.169.254/latest/meta-data/",
        "https://192.168.1.1/admin",
        "https://10.0.0.1/",
    ]
    for url in blocked_targets:
        with pytest.raises(URLSecurityError):
            validator.validate_url(url)


def test_embedded_credentials_rejected():
    """URLs with embedded user:pass are rejected."""
    validator = URLSecurityValidator(settings=Settings())
    with pytest.raises(URLSecurityError):
        validator.validate_url("https://admin:secret@example.com/dashboard")


# -----------------------------------------------------------------------------
# 2. Browser Approval Policy Tests
# -----------------------------------------------------------------------------
def test_sensitive_action_requires_approval():
    """Buttons containing purchase, submit, pay, delete require explicit user approval."""
    # 1. Submit button click
    click_req = BrowserActionRequest(action=BrowserActionType.CLICK, selector="button:text('Submit Payment')")
    assert BrowserApprovalPolicy.requires_approval(click_req) is True

    # 2. Delete account click
    delete_req = BrowserActionRequest(action=BrowserActionType.CLICK, selector="role=button:Delete Account")
    assert BrowserApprovalPolicy.requires_approval(delete_req) is True

    # 3. Password field fill
    pass_req = BrowserActionRequest(action=BrowserActionType.FILL, selector="#password", value="secret123")
    assert BrowserApprovalPolicy.requires_approval(pass_req) is True


def test_ordinary_action_does_not_require_approval():
    """Harmless inspection, scrolling, or search filling does not trigger approval block."""
    scroll_req = BrowserActionRequest(action=BrowserActionType.SCROLL, direction="down", distance=300)
    assert BrowserApprovalPolicy.requires_approval(scroll_req) is False

    search_req = BrowserActionRequest(action=BrowserActionType.FILL, selector="input[name='q']", value="python docs")
    assert BrowserApprovalPolicy.requires_approval(search_req) is False


# -----------------------------------------------------------------------------
# 3. Session & Interaction Tests (Mocked Page & Browser)
# -----------------------------------------------------------------------------
@pytest.fixture
def mock_browser_session():
    """Provides a ManagedBrowserSession backed by mocked Playwright objects."""
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_context.close = AsyncMock()

    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.url = "https://www.python.org"
    mock_page.title = AsyncMock(return_value="Welcome to Python.org")
    mock_page.evaluate = AsyncMock(side_effect=[
        # Headings evaluate
        [{"level": 1, "text": "Welcome to Python.org"}],
        # Links evaluate
        [{"label": "Documentation", "url": "https://docs.python.org"}],
        # Body text evaluate
        "Python is a programming language that lets you work quickly and integrate systems more effectively."
    ])
    mock_page.click = AsyncMock()
    mock_page.fill = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n...")

    session = ManagedBrowserSession(
        session_id="test-session-123",
        browser=mock_browser,
        context=mock_context,
        page=mock_page,
        settings=Settings(),
    )
    return session


@pytest.mark.asyncio
async def test_session_navigate_success(mock_browser_session):
    """Navigation validates URL and updates title/current_url."""
    final_url = await mock_browser_session.navigate("https://www.python.org")
    assert final_url == "https://www.python.org"
    assert mock_browser_session.page_title == "Welcome to Python.org"
    assert mock_browser_session.status == BrowserSessionStatus.IDLE


@pytest.mark.asyncio
async def test_session_inspect_page(mock_browser_session):
    """Page inspection returns structured headings, links, and bounded visible text."""
    inspection = await mock_browser_session.inspect_page()
    assert inspection.title == "Welcome to Python.org"
    assert len(inspection.headings) == 1
    assert inspection.headings[0].text == "Welcome to Python.org"
    assert len(inspection.links) == 1
    assert inspection.links[0].url == "https://docs.python.org"
    assert "Python is a programming language" in inspection.text_content


@pytest.mark.asyncio
async def test_session_execute_click_and_fill(mock_browser_session):
    """Click and fill interact with Playwright locators."""
    mock_locator = MagicMock()
    mock_locator.click = AsyncMock()
    mock_locator.fill = AsyncMock()
    mock_browser_session.page.locator = MagicMock(return_value=mock_locator)

    # Click
    click_res = await mock_browser_session.execute_action(
        BrowserActionRequest(action=BrowserActionType.CLICK, selector="#nav-docs")
    )
    assert click_res.success is True
    mock_locator.click.assert_awaited_once()

    # Fill
    fill_res = await mock_browser_session.execute_action(
        BrowserActionRequest(action=BrowserActionType.FILL, selector="#search", value="pytest")
    )
    assert fill_res.success is True
    mock_locator.fill.assert_awaited_once_with("pytest", timeout=30000)


# -----------------------------------------------------------------------------
# 4. Web Search & Multi-Page Research Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_web_search_engine_query():
    """Web search engine queries provider and filters results."""
    engine = WebSearchEngine(settings=Settings())
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <h2 class="result__title"><a href="https://fastapi.tiangolo.com">FastAPI</a></h2>
        <a class="result__url" href="https://fastapi.tiangolo.com">fastapi.tiangolo.com</a>
        <a class="result__snippet">FastAPI framework, high performance, easy to learn.</a>
        """
        mock_get.return_value = mock_resp

        res = await engine.search("FastAPI documentation", limit=1)
        assert res.total_results >= 1
        assert res.results[0].title == "FastAPI"
        assert res.results[0].url == "https://fastapi.tiangolo.com"


@pytest.mark.asyncio
async def test_web_research_engine_synthesis(mock_browser_session):
    """Multi-page research visits candidate pages and produces grounded summary."""
    mock_manager = MagicMock()
    mock_manager.create_session = AsyncMock(return_value=mock_browser_session)
    mock_manager.close_session = AsyncMock()

    mock_search = MagicMock()
    mock_search.search = AsyncMock(return_value=WebSearchResponse(
        query="FastAPI",
        total_results=1,
        results=[SearchResultItem(title="FastAPI", url="https://fastapi.tiangolo.com", snippet="FastAPI docs")]
    ))

    research = WebResearchEngine(browser_manager=mock_manager, search_engine=mock_search)
    res = await research.execute_research(query="FastAPI", max_pages=1)
    assert res.pages_visited == 1
    assert len(res.sources) == 1
    assert res.sources[0].url == "https://fastapi.tiangolo.com"
    assert "FastAPI" in res.summary


# -----------------------------------------------------------------------------
# 5. REST API Integration Tests
# -----------------------------------------------------------------------------
@pytest.fixture
def browser_api_client(mock_browser_session):
    """FastAPI TestClient with overridden BrowserManager."""
    app = create_app()

    mock_mgr = MagicMock()
    mock_mgr.settings = Settings()
    mock_mgr.sessions = {"sess-test-1": mock_browser_session}
    mock_mgr.create_session = AsyncMock(return_value=mock_browser_session)
    mock_mgr.get_session = MagicMock(return_value=mock_browser_session)
    mock_mgr.list_sessions = MagicMock(return_value=[mock_browser_session.to_response()])
    mock_mgr.close_session = AsyncMock()

    from app.api.routes.browser import get_browser_manager
    app.dependency_overrides[get_browser_manager] = lambda: mock_mgr

    client = TestClient(app)
    return client


def test_api_browser_status(browser_api_client):
    """GET /api/v1/browser/status."""
    resp = browser_api_client.get("/api/v1/browser/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["max_sessions"] == 3


def test_api_create_and_list_sessions(browser_api_client):
    """POST /api/v1/browser/sessions and GET /api/v1/browser/sessions."""
    create_resp = browser_api_client.post("/api/v1/browser/sessions", json={"headless": True})
    assert create_resp.status_code == 201
    assert "session_id" in create_resp.json()

    list_resp = browser_api_client.get("/api/v1/browser/sessions")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1


def test_api_navigate_and_inspect_page(browser_api_client):
    """POST /api/v1/browser/sessions/{id}/navigate and GET /api/v1/browser/sessions/{id}/page."""
    nav_resp = browser_api_client.post(
        "/api/v1/browser/sessions/sess-test-1/navigate",
        json={"url": "https://www.python.org"}
    )
    assert nav_resp.status_code == 200
    assert nav_resp.json()["url"] == "https://www.python.org"

    inspect_resp = browser_api_client.get("/api/v1/browser/sessions/sess-test-1/page")
    assert inspect_resp.status_code == 200
    assert "headings" in inspect_resp.json()


def test_api_sensitive_action_blocked_by_approval_policy(browser_api_client):
    """POST /api/v1/browser/sessions/{id}/actions blocks sensitive button clicks without approval."""
    act_resp = browser_api_client.post(
        "/api/v1/browser/sessions/sess-test-1/actions",
        json={"action": "click", "selector": "button:text('Submit Payment')"}
    )
    assert act_resp.status_code == 403
    assert "requires explicit user approval" in act_resp.json()["detail"]


def test_api_close_session(browser_api_client):
    """DELETE /api/v1/browser/sessions/{id}."""
    resp = browser_api_client.delete("/api/v1/browser/sessions/sess-test-1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"
