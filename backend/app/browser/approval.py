"""Sensitive action classifier identifying consequential browser interactions requiring explicit user confirmation."""

import re
from typing import Optional, Set

from app.browser.schemas import BrowserActionRequest, BrowserActionType

# Regular expressions detecting sensitive submission or payment buttons
SENSITIVE_TEXT_PATTERNS = [
    r"\b(buy|purchase|pay|checkout|order now|subscribe)\b",
    r"\b(submit|send|post|publish|share|tweet)\b",
    r"\b(delete|remove|erase|destroy|cancel account)\b",
    r"\b(accept terms|agree to terms|sign in|log in|authorize)\b",
    r"\b(upload|transfer|confirm order)\b",
]


class BrowserApprovalPolicy:
    """Classifies browser interactions to determine if explicit user approval is required before execution."""

    @classmethod
    def requires_approval(cls, action_req: BrowserActionRequest, current_url: Optional[str] = None) -> bool:
        """Evaluate if proposed action is externally consequential or mutates external state."""
        # 1. Filling password or credit card fields
        if action_req.action == BrowserActionType.FILL:
            val = (action_req.value or "").lower()
            sel = (action_req.selector or "").lower()
            if any(term in sel for term in ["password", "passwd", "pin", "cvv", "credit", "card", "ssn"]):
                return True

        # 2. Clicks on sensitive buttons
        if action_req.action == BrowserActionType.CLICK:
            sel = (action_req.selector or "").lower()
            for pattern in SENSITIVE_TEXT_PATTERNS:
                if re.search(pattern, sel, re.IGNORECASE):
                    return True

        return False
