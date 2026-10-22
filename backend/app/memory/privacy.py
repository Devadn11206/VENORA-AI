"""Privacy and security filtering utilities for the memory subsystem.

Defines regex heuristics to scrub credentials, secret keys, passwords, and sensitive tokens
before memories are stored in the persistent database.
"""

import re
from typing import Tuple

# Common patterns for API keys, tokens, passwords, and secrets
_SECRET_PATTERNS = [
    re.compile(r"(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token|bearer)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{16,})['\"]?", re.IGNORECASE),
    re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]{6,})['\"]?", re.IGNORECASE),
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),  # OpenAI / OpenRouter style
    re.compile(r"ghp_[a-zA-Z0-9]{36,}", re.IGNORECASE),   # GitHub personal access tokens
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"),
]


def contains_sensitive_secrets(text: str) -> bool:
    """Check if the text contains high-risk secrets (API keys, private keys, passwords)."""
    if not text:
        return False
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


def sanitize_and_redact_secrets(text: str) -> str:
    """Scrub sensitive secrets from text, replacing them with [REDACTED_SECRET]."""
    if not text:
        return ""
    sanitized = text
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized
