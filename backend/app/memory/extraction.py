"""Memory extraction engine for identifying useful long-term memories from conversation turns."""

import json
import re
from typing import List, Optional
from app.core.logging import get_logger
from app.ai.provider import BaseAIProvider
from app.models.memory import MemoryCategory
from app.memory.schemas import CandidateMemory
from app.memory.privacy import sanitize_and_redact_secrets, contains_sensitive_secrets

logger = get_logger("memory.extraction")

_EXTRACTION_PROMPT = """You are the Memory Extraction Module of VENORA AI.
Analyze the conversation dialogue below and extract durable, useful long-term memories worth remembering in future sessions.

Memory Categories:
- USER_PREFERENCE: User's explicitly stated habits, response styles, preferred frameworks/languages.
- USER_FACT: Concrete, relatively stable personal or environment facts explicitly stated by user.
- PROJECT_CONTEXT: Architecture decisions, goals, constraints, technology stacks.
- TASK_CONTEXT: Reusable details or parameters from a completed workflow.
- PROCEDURAL_MEMORY: Explicit user-taught rules, steps, or workflows.
- CONVERSATION_SUMMARY: Concise high-level summary of the key decision or outcome.

Guidelines:
1. ONLY extract meaningful, durable information. Do not retain small talk or trivial chit-chat.
2. DO NOT extract passwords, API keys, credentials, or private authentication tokens.
3. Distinguish explicit statements (high confidence 0.9-1.0) from inferred context (confidence 0.6-0.8).
4. Output must be a strictly valid JSON array of objects with fields:
   - "content": concise, standalone factual statement
   - "category": one of USER_PREFERENCE, USER_FACT, PROJECT_CONTEXT, TASK_CONTEXT, PROCEDURAL_MEMORY, CONVERSATION_SUMMARY
   - "confidence": float between 0.0 and 1.0
   - "importance": float between 0.0 and 1.0
   - "reason_for_retention": short explanation

If nothing is worth remembering, return an empty array: []

Conversation:
{conversation_text}

JSON Output:"""


class MemoryExtractor:
    """Extracts candidate memory records from raw conversation turns."""

    def __init__(self, ai_provider: Optional[BaseAIProvider] = None) -> None:
        self.ai_provider = ai_provider

    def extract_from_conversation(
        self,
        messages: List[dict],
        min_confidence: float = 0.75,
        max_candidates: int = 10
    ) -> List[CandidateMemory]:
        """Extract candidate memories from message list."""
        if not messages:
            return []

        # If no AI provider is configured, run heuristic extraction
        if not self.ai_provider:
            return self._heuristic_extraction(messages, min_confidence, max_candidates)

        # Build formatted dialogue text
        dialogue = []
        for msg in messages:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            if content and isinstance(content, str):
                dialogue.append(f"{role}: {content}")

        convo_str = "\n".join(dialogue)
        prompt = _EXTRACTION_PROMPT.format(conversation_text=convo_str)

        try:
            response = self.ai_provider.chat_complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            raw_text = response.content.strip() if hasattr(response, "content") else str(response).strip()
            
            # Clean markdown codeblocks if returned
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()

            parsed = json.loads(raw_text)
            if not isinstance(parsed, list):
                logger.warning("Memory extraction did not return a JSON list; falling back to heuristics.")
                return self._heuristic_extraction(messages, min_confidence, max_candidates)

            candidates: List[CandidateMemory] = []
            for item in parsed[:max_candidates]:
                try:
                    content = item.get("content", "").strip()
                    if not content or len(content) < 3:
                        continue

                    # Filter secrets immediately
                    if contains_sensitive_secrets(content):
                        logger.warning("Candidate memory discarded due to sensitive secret detection.")
                        continue

                    sanitized = sanitize_and_redact_secrets(content)
                    cat_str = item.get("category", "USER_FACT")
                    category = MemoryCategory[cat_str] if cat_str in MemoryCategory.__members__ else MemoryCategory.USER_FACT
                    confidence = float(item.get("confidence", 0.8))
                    importance = float(item.get("importance", 0.5))

                    if confidence >= min_confidence:
                        candidates.append(
                            CandidateMemory(
                                content=sanitized,
                                category=category,
                                confidence=confidence,
                                importance=importance,
                                reason_for_retention=item.get("reason_for_retention", "")
                            )
                        )
                except Exception as parse_err:
                    logger.debug(f"Skipping malformed candidate memory: {parse_err}")

            return candidates

        except Exception as exc:
            logger.warning(f"AI memory extraction encountered error ({exc}); using heuristic fallback.")
            return self._heuristic_extraction(messages, min_confidence, max_candidates)

    def _heuristic_extraction(
        self,
        messages: List[dict],
        min_confidence: float = 0.75,
        max_candidates: int = 10
    ) -> List[CandidateMemory]:
        """Heuristic rule-based fallback extraction when AI provider is unavailable."""
        candidates: List[CandidateMemory] = []

        preference_patterns = [
            (re.compile(r"i prefer\s+(.+)", re.IGNORECASE), MemoryCategory.USER_PREFERENCE),
            (re.compile(r"my preference is\s+(.+)", re.IGNORECASE), MemoryCategory.USER_PREFERENCE),
            (re.compile(r"always use\s+(.+)", re.IGNORECASE), MemoryCategory.USER_PREFERENCE),
            (re.compile(r"our project uses\s+(.+)", re.IGNORECASE), MemoryCategory.PROJECT_CONTEXT),
            (re.compile(r"we decided to\s+(.+)", re.IGNORECASE), MemoryCategory.PROJECT_CONTEXT),
            (re.compile(r"remember that\s+(.+)", re.IGNORECASE), MemoryCategory.USER_FACT),
            (re.compile(r"my name is\s+(.+)", re.IGNORECASE), MemoryCategory.USER_FACT),
        ]

        for msg in messages:
            if msg.get("role") != "user":
                continue
            text = msg.get("content", "")
            if not isinstance(text, str):
                continue

            for pattern, cat in preference_patterns:
                match = pattern.search(text)
                if match:
                    extracted = text.strip()
                    if contains_sensitive_secrets(extracted):
                        continue
                    sanitized = sanitize_and_redact_secrets(extracted)
                    candidates.append(
                        CandidateMemory(
                            content=sanitized,
                            category=cat,
                            confidence=0.9,
                            importance=0.7,
                            reason_for_retention="Explicit user statement matched heuristic pattern."
                        )
                    )
                    if len(candidates) >= max_candidates:
                        return candidates

        return candidates
