"""BrowserManager managing concurrent Playwright Chromium instances and sessions."""

import asyncio
import logging
from typing import Dict, List, Optional
import uuid

from app.core.config import Settings, get_settings
from app.core.errors import BrowserSessionError, BrowserSessionNotFoundError
from app.browser.schemas import BrowserSessionResponse, BrowserSessionStatus
from app.browser.security import URLSecurityValidator
from app.browser.session import ManagedBrowserSession

logger = logging.getLogger("venora.browser.manager")


class BrowserManager:
    """Singleton/central manager for application-managed browser lifecycle and contexts."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.security_validator = URLSecurityValidator(settings=self.settings)
        self.sessions: Dict[str, ManagedBrowserSession] = {}
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        """Lazily initialize the Playwright Chromium instance."""
        if self._browser is None:
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=self.settings.BROWSER_HEADLESS,
                    args=[
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                    ],
                )
                logger.info("Playwright Chromium browser process started.")
            except Exception as exc:
                logger.error(f"Failed to launch Playwright browser: {exc}")
                raise BrowserSessionError(f"Could not launch browser: {exc}")

    async def create_session(self, headless: Optional[bool] = None) -> ManagedBrowserSession:
        """Create an isolated browser context and page."""
        async with self._lock:
            # Enforce max concurrent sessions limit
            if len(self.sessions) >= self.settings.BROWSER_MAX_SESSIONS:
                # Clean stale sessions first
                await self.cleanup_stale_sessions()
                if len(self.sessions) >= self.settings.BROWSER_MAX_SESSIONS:
                    raise BrowserSessionError(
                        f"Active browser sessions limit ({self.settings.BROWSER_MAX_SESSIONS}) reached."
                    )

            await self._ensure_browser()

            session_id = str(uuid.uuid4())
            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 VENORA-Assistant/1.0",
                accept_downloads=False,
            )
            page = await context.new_page()

            managed = ManagedBrowserSession(
                session_id=session_id,
                browser=self._browser,
                context=context,
                page=page,
                settings=self.settings,
                security_validator=self.security_validator,
            )
            self.sessions[session_id] = managed
            logger.info(f"Created browser session: {session_id}")
            return managed

    def get_session(self, session_id: str) -> ManagedBrowserSession:
        """Retrieve active session by ID or raise BrowserSessionNotFoundError."""
        if session_id not in self.sessions:
            raise BrowserSessionNotFoundError(session_id)
        session = self.sessions[session_id]
        if session.status == BrowserSessionStatus.CLOSED:
            raise BrowserSessionNotFoundError(session_id)
        return session

    def list_sessions(self) -> List[BrowserSessionResponse]:
        """List active session metadata."""
        return [s.to_response() for s in self.sessions.values() if s.status != BrowserSessionStatus.CLOSED]

    async def close_session(self, session_id: str) -> None:
        """Close an active session and release its context."""
        if session_id in self.sessions:
            session = self.sessions.pop(session_id)
            await session.close()
            logger.info(f"Closed browser session {session_id}")

    async def cleanup_stale_sessions(self) -> int:
        """Close sessions that exceeded inactivity timeout."""
        now = asyncio.get_event_loop().time()
        timeout = self.settings.BROWSER_SESSION_TIMEOUT_SECONDS
        stale_ids = []

        for sid, sess in list(self.sessions.items()):
            elapsed = (datetime.now().astimezone() - sess.last_activity_at.astimezone()).total_seconds()
            if elapsed > timeout or sess.status == BrowserSessionStatus.CLOSED:
                stale_ids.append(sid)

        for sid in stale_ids:
            await self.close_session(sid)

        return len(stale_ids)

    async def shutdown(self) -> None:
        """Cleanly close all sessions and stop the browser process."""
        for sid in list(self.sessions.keys()):
            await self.close_session(sid)

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        logger.info("Browser manager shut down successfully.")
