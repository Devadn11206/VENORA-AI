"""URL validation, anti-SSRF protection, and network safety enforcement."""

import ipaddress
import logging
from typing import List, Optional, Set
from urllib.parse import urlparse

from app.core.config import Settings, get_settings
from app.core.errors import URLSecurityError

logger = logging.getLogger("venora.browser.security")

DISALLOWED_SCHEMES: Set[str] = {
    "file",
    "javascript",
    "data",
    "vbscript",
    "about",
    "chrome",
    "edge",
    "blob",
}


class URLSecurityValidator:
    """Enforces HTTPS protocols, blocks local IP/loopback/metadata destinations, and prevents SSRF."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.allow_http = self.settings.BROWSER_ALLOW_HTTP
        self.blocked_hosts = set(h.lower() for h in self.settings.BROWSER_BLOCKED_HOSTS)

    def validate_url(self, target_url: str) -> str:
        """Validate destination URL against protocol and network security rules.
        
        Rules:
        - Must be a valid well-formed URL
        - Scheme must be 'https' (or 'http' if explicitly enabled in config)
        - Scheme file://, javascript:, data:, and browser-internal schemes are strictly rejected
        - Embedded credentials (e.g. user:pass@host) are rejected
        - Loopback (127.0.0.1, localhost), private networks (10.x, 192.168.x, 172.16.x),
          link-local addresses (169.254.x), and cloud metadata endpoints are blocked.
        """
        if not target_url or not target_url.strip():
            raise URLSecurityError(target_url, "URL cannot be empty.")

        clean_url = target_url.strip()
        try:
            parsed = urlparse(clean_url)
        except Exception as exc:
            raise URLSecurityError(clean_url, f"Malformed URL: {exc}")

        scheme = (parsed.scheme or "").lower()
        if not scheme:
            raise URLSecurityError(clean_url, "URL missing protocol scheme (e.g., https://).")

        # 1. Scheme enforcement
        if scheme in DISALLOWED_SCHEMES:
            raise URLSecurityError(clean_url, f"Protocol scheme '{scheme}://' is strictly prohibited.")

        if scheme == "http" and not self.allow_http:
            raise URLSecurityError(clean_url, "Insecure HTTP scheme is not allowed by policy. HTTPS is required.")

        if scheme not in {"http", "https"}:
            raise URLSecurityError(clean_url, f"Unsupported scheme '{scheme}'. Only HTTP/HTTPS supported.")

        # 2. Rejection of embedded credentials
        if parsed.username or parsed.password:
            raise URLSecurityError(clean_url, "URLs containing embedded authentication credentials are prohibited.")

        # 3. Hostname and IP validation (Anti-SSRF)
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise URLSecurityError(clean_url, "URL missing valid hostname.")

        if hostname in self.blocked_hosts:
            raise URLSecurityError(clean_url, f"Access to '{hostname}' is blocked by anti-SSRF security policy.")

        # Check if hostname is an IP address
        try:
            ip_obj = ipaddress.ip_address(hostname)
            if ip_obj.is_loopback:
                raise URLSecurityError(clean_url, "Loopback IP addresses (127.0.0.0/8, ::1) are blocked.")
            if ip_obj.is_private:
                raise URLSecurityError(clean_url, "Private network IP addresses are blocked.")
            if ip_obj.is_link_local:
                raise URLSecurityError(clean_url, "Link-local addresses (169.254.0.0/16) are blocked.")
            if ip_obj.is_reserved:
                raise URLSecurityError(clean_url, "Reserved IP addresses are blocked.")
        except ValueError:
            # Hostname is a domain name, not a literal IP
            pass

        return clean_url
