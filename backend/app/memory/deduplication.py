"""Deduplication and conflict resolution for persistent memory records.

Handles content hashing, duplicate detection, and intelligent conflict resolution
where explicit updates supersede outdated facts.
"""

import hashlib
import re
from typing import Optional, Tuple
from app.models.memory import MemoryCategory, MemoryRecord, MemoryStatus


def compute_content_hash(content: str, category: MemoryCategory) -> str:
    """Compute deterministic SHA-256 hash for normalized content and category.

    Normalizes whitespace and lowercase to detect exact semantic duplicates.
    """
    normalized = re.sub(r"\s+", " ", content.strip().lower())
    payload = f"{category.value}:{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def detect_memory_conflict(
    existing: MemoryRecord,
    new_content: str,
    new_category: MemoryCategory
) -> Tuple[bool, str]:
    """Detect whether new information conflicts with an existing memory.

    Returns:
        (is_conflict, explanation)
    """
    if existing.category != new_category:
        return False, ""

    # Check for direct subject overlap with differing predicate/value
    # E.g. "Uses SQLite database" vs "Migrated to PostgreSQL database"
    e_words = set(re.findall(r"\w+", existing.content.lower()))
    n_words = set(re.findall(r"\w+", new_content.lower()))

    # Filter common stop words for topic comparison
    stop_words = {"the", "a", "an", "for", "to", "and", "is", "of", "in", "with", "uses"}
    e_filtered = e_words - stop_words
    n_filtered = n_words - stop_words

    intersection = e_filtered.intersection(n_filtered)
    union = e_filtered.union(n_filtered)
    if not union:
        return False, ""

    similarity = len(intersection) / len(union)

    # Check if words indicate an update/migration/replacement
    update_markers = {"migrate", "migrated", "switch", "switched", "now", "update", "updated", "change", "changed", "prefer", "replace"}
    has_update_marker = bool(n_words.intersection(update_markers))

    # If an update marker is present and key topic nouns overlap (e.g. project, database)
    if has_update_marker and len(intersection) >= 1:
        return True, f"Detected state update or topic replacement (overlap={len(intersection)}, similarity={similarity:.2f})"

    # Moderate similarity indicates they talk about the exact same topic, but words changed
    if 0.35 <= similarity < 0.95:
        if has_update_marker:
            return True, f"Detected state update or topic replacement (similarity={similarity:.2f})"

    return False, ""
