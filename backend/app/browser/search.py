"""Web search engine abstraction with DuckDuckGo HTML / API search provider."""

import logging
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

from app.core.config import Settings, get_settings
from app.core.errors import SearchProviderError
from app.browser.schemas import SearchResultItem, WebSearchResponse
from app.browser.security import URLSecurityValidator

logger = logging.getLogger("venora.browser.search")


class WebSearchEngine:
    """Performs normalized web searches using public DuckDuckGo HTML endpoint without scraping private credentials."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.security_validator = URLSecurityValidator(settings=self.settings)

    async def search(self, query: str, limit: int = 5) -> WebSearchResponse:
        """Execute a web search query and return normalized, validated results."""
        clean_query = query.strip()
        if not clean_query:
            return WebSearchResponse(query=query, total_results=0, results=[])

        # Use DuckDuckGo HTML endpoint
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(clean_query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 VENORA/1.0"
        }

        results: List[SearchResultItem] = []
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"Search provider returned status {resp.status_code}")
                    return WebSearchResponse(query=clean_query, total_results=0, results=[])

                # Parse results via BeautifulSoup if available, else simple regex parsing
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.find_all("a", class_="result__url")
                    snippets = soup.find_all("a", class_="result__snippet")
                    titles = soup.find_all("h2", class_="result__title")

                    for i in range(min(len(titles), limit)):
                        raw_title = titles[i].get_text().strip()
                        raw_link = links[i]["href"] if i < len(links) and "href" in links[i].attrs else None
                        raw_snippet = snippets[i].get_text().strip() if i < len(snippets) else ""

                        if not raw_link:
                            continue

                        # Extract target destination from DDG redirect url
                        dest_url = raw_link
                        if "uddg=" in dest_url:
                            import urllib.parse
                            parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(dest_url).query)
                            if "uddg" in parsed_qs:
                                dest_url = parsed_qs["uddg"][0]

                        # Security check on candidate search URL
                        try:
                            valid_url = self.security_validator.validate_url(dest_url)
                            results.append(SearchResultItem(
                                title=raw_title,
                                url=valid_url,
                                snippet=raw_snippet,
                                source_provider="duckduckgo",
                            ))
                        except Exception:
                            continue

                except ImportError:
                    logger.warning("BeautifulSoup not installed; returning empty search results.")

        except Exception as exc:
            logger.error(f"Search query '{clean_query}' failed: {exc}")
            raise SearchProviderError(f"Web search failed: {exc}")

        return WebSearchResponse(
            query=clean_query,
            total_results=len(results),
            results=results[:limit],
        )
