"""Browser session encapsulating Playwright browser, context, and page instances."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import Settings, get_settings
from app.core.errors import (
    BrowserActionError,
    ElementNotFoundError,
    URLSecurityError,
)
from app.browser.schemas import (
    BrowserActionRequest,
    BrowserActionResponse,
    BrowserActionType,
    BrowserSessionResponse,
    BrowserSessionStatus,
    PageHeading,
    PageInspectionResponse,
    PageLink,
)
from app.browser.security import URLSecurityValidator

logger = logging.getLogger("venora.browser.session")


class ManagedBrowserSession:
    """Manages an isolated Playwright BrowserContext and Page."""

    def __init__(
        self,
        session_id: str,
        browser: Any,
        context: Any,
        page: Any,
        settings: Optional[Settings] = None,
        security_validator: Optional[URLSecurityValidator] = None,
    ) -> None:
        self.session_id = session_id
        self.browser = browser
        self.context = context
        self.page = page
        self.settings = settings or get_settings()
        self.security_validator = security_validator or URLSecurityValidator(settings=self.settings)
        self.status = BrowserSessionStatus.ACTIVE
        self.created_at = datetime.now(timezone.utc)
        self.last_activity_at = datetime.now(timezone.utc)
        self.current_url: Optional[str] = None
        self.page_title: Optional[str] = None

    def touch(self) -> None:
        """Update activity timestamp."""
        self.last_activity_at = datetime.now(timezone.utc)

    async def navigate(self, target_url: str) -> str:
        """Validate URL and navigate the page."""
        validated_url = self.security_validator.validate_url(target_url)
        self.status = BrowserSessionStatus.NAVIGATING
        self.touch()

        try:
            timeout_ms = int(self.settings.BROWSER_PAGE_TIMEOUT_SECONDS * 1000)
            response = await self.page.goto(validated_url, timeout=timeout_ms, wait_until="domcontentloaded")
            
            # Post-navigation redirect check
            final_url = self.page.url
            self.security_validator.validate_url(final_url)

            self.current_url = final_url
            self.page_title = await self.page.title()
            self.status = BrowserSessionStatus.IDLE
            self.touch()
            logger.info(f"Session {self.session_id} navigated to {final_url} ('{self.page_title}')")
            return final_url
        except URLSecurityError:
            self.status = BrowserSessionStatus.ERROR
            raise
        except Exception as exc:
            self.status = BrowserSessionStatus.ERROR
            logger.error(f"Navigation failed for session {self.session_id} to '{target_url}': {exc}")
            raise BrowserActionError(f"Navigation to '{target_url}' failed: {exc}")

    async def inspect_page(self) -> PageInspectionResponse:
        """Extract title, current URL, headings, links, and visible text."""
        self.touch()
        url = self.page.url
        title = await self.page.title()

        # Extract headings via evaluate
        headings_raw = await self.page.evaluate(
            """() => {
                const results = [];
                document.querySelectorAll('h1, h2, h3').forEach(el => {
                    const text = el.innerText ? el.innerText.trim() : '';
                    if (text) {
                        const level = parseInt(el.tagName.replace('H', ''), 10);
                        results.push({ level, text });
                    }
                });
                return results.slice(0, 30);
            }"""
        )
        headings = [PageHeading(level=h["level"], text=h["text"]) for h in headings_raw]

        # Extract links
        links_raw = await self.page.evaluate(
            """() => {
                const results = [];
                document.querySelectorAll('a[href]').forEach(el => {
                    const label = el.innerText ? el.innerText.trim() : '';
                    const href = el.href;
                    if (label && href && href.startsWith('http')) {
                        results.push({ label: label.substring(0, 100), url: href });
                    }
                });
                return results.slice(0, 50);
            }"""
        )
        links = [PageLink(label=l["label"], url=l["url"]) for l in links_raw]

        # Extract visible text content (strip script/style tags)
        visible_text = await self.page.evaluate(
            """() => {
                const clone = document.body.cloneNode(true);
                const scripts = clone.querySelectorAll('script, style, noscript, svg');
                scripts.forEach(s => s.remove());
                return clone.innerText || '';
            }"""
        )

        max_chars = self.settings.BROWSER_MAX_EXTRACTED_CHARS
        clean_text = (visible_text or "").strip()
        is_truncated = len(clean_text) > max_chars
        bounded_text = clean_text[:max_chars]

        self.current_url = url
        self.page_title = title

        return PageInspectionResponse(
            session_id=self.session_id,
            url=url,
            title=title,
            headings=headings,
            links=links,
            text_content=bounded_text,
            char_count=len(bounded_text),
            is_truncated=is_truncated,
        )

    async def execute_action(self, action_req: BrowserActionRequest) -> BrowserActionResponse:
        """Execute a controlled interactive operation (click, fill, select, scroll)."""
        self.touch()
        act = action_req.action
        timeout_ms = int(self.settings.BROWSER_PAGE_TIMEOUT_SECONDS * 1000)

        try:
            if act == BrowserActionType.CLICK:
                if not action_req.selector:
                    raise BrowserActionError("Selector required for click action.")
                locator = self._resolve_locator(action_req.selector)
                await locator.click(timeout=timeout_ms)

            elif act == BrowserActionType.FILL:
                if not action_req.selector:
                    raise BrowserActionError("Selector required for fill action.")
                locator = self._resolve_locator(action_req.selector)
                await locator.fill(action_req.value or "", timeout=timeout_ms)

            elif act == BrowserActionType.SELECT:
                if not action_req.selector:
                    raise BrowserActionError("Selector required for select action.")
                locator = self._resolve_locator(action_req.selector)
                await locator.select_option(action_req.value or "", timeout=timeout_ms)

            elif act == BrowserActionType.CHECK:
                if not action_req.selector:
                    raise BrowserActionError("Selector required for check action.")
                locator = self._resolve_locator(action_req.selector)
                await locator.check(timeout=timeout_ms)

            elif act == BrowserActionType.SCROLL:
                distance = action_req.distance or 500
                if action_req.direction == "up":
                    distance = -distance
                await self.page.evaluate(f"window.scrollBy(0, {distance});")

            elif act == BrowserActionType.BACK:
                await self.page.go_back(timeout=timeout_ms)

            elif act == BrowserActionType.FORWARD:
                await self.page.go_forward(timeout=timeout_ms)

            elif act == BrowserActionType.SCREENSHOT:
                # Capture in memory or file
                screenshot_bytes = await self.page.screenshot()
                # Return success indicator

            # Re-verify page destination after action (in case click triggered a navigation)
            curr_url = self.page.url
            self.security_validator.validate_url(curr_url)
            self.current_url = curr_url
            self.page_title = await self.page.title()
            self.touch()

            return BrowserActionResponse(
                session_id=self.session_id,
                action=act,
                success=True,
                resulting_url=curr_url,
                resulting_title=self.page_title,
                message=f"Action '{act.value}' executed successfully.",
            )
        except URLSecurityError:
            raise
        except Exception as exc:
            logger.warning(f"Browser action '{act}' failed in session {self.session_id}: {exc}")
            raise BrowserActionError(f"Action '{act}' failed: {exc}")

    def _resolve_locator(self, selector: str):
        """Find element locator using text, role, or CSS selector safely."""
        clean_sel = selector.strip()
        # Role or text shortcuts
        if clean_sel.startswith("text="):
            return self.page.get_by_text(clean_sel[5:])
        elif clean_sel.startswith("label="):
            return self.page.get_by_label(clean_sel[6:])
        elif clean_sel.startswith("role="):
            parts = clean_sel[5:].split(":")
            role = parts[0]
            name = parts[1] if len(parts) > 1 else None
            return self.page.get_by_role(role, name=name) if name else self.page.get_by_role(role)
        else:
            return self.page.locator(clean_sel)

    async def close(self) -> None:
        """Close page and context cleanly."""
        self.status = BrowserSessionStatus.CLOSED
        try:
            await self.context.close()
        except Exception as exc:
            logger.debug(f"Error closing context for session {self.session_id}: {exc}")

    def to_response(self) -> BrowserSessionResponse:
        """Serialize metadata."""
        return BrowserSessionResponse(
            session_id=self.session_id,
            status=self.status,
            current_url=self.current_url,
            page_title=self.page_title,
            created_at=self.created_at,
            last_activity_at=self.last_activity_at,
        )
