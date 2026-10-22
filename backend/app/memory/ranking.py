"""Hybrid memory ranking and scoring engine.

Combines:
1. Semantic vector similarity (cosine) if embeddings are active.
2. Lexical match score (token overlap / FTS5 match).
3. Memory confidence score.
4. Memory importance weight.
5. Recency / age decay.
"""

from datetime import datetime, timezone
import math
import re
from typing import Optional
from app.models.memory import MemoryRecord


def compute_lexical_score(query: str, content: str) -> float:
    """Compute normalized token overlap lexical score between query and memory content."""
    q_tokens = set(re.findall(r"\w+", query.lower()))
    if not q_tokens:
        return 0.0

    c_tokens = set(re.findall(r"\w+", content.lower()))
    if not c_tokens:
        return 0.0

    overlap = q_tokens.intersection(c_tokens)
    # Score proportional to how much of the query matches the content
    ratio = len(overlap) / len(q_tokens)

    # Bonus if query phrase appears verbatim
    if query.strip().lower() in content.lower():
        ratio = min(1.0, ratio + 0.3)

    return max(0.0, min(1.0, ratio))


def compute_recency_score(created_at: datetime, half_life_days: float = 90.0) -> float:
    """Compute exponential decay score based on memory age.

    Recency score is normalized between 0.0 and 1.0. A 90-day half-life ensures
    older memories are slightly downranked compared to brand-new ones, without
    erasing foundational project decisions.
    """
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    decay = math.exp(-0.693 * age_days / half_life_days)
    return max(0.1, min(1.0, decay))


def score_memory(
    memory: MemoryRecord,
    query: str,
    semantic_similarity: Optional[float] = None
) -> float:
    """Compute overall hybrid relevance score [0.0, 1.0] for a memory record against a query.

    Weights:
    - If semantic similarity is available:
        - 45% Semantic similarity
        - 25% Lexical overlap
        - 15% Importance
        - 10% Confidence
        - 5% Recency
    - If lexical only:
        - 65% Lexical overlap
        - 20% Importance
        - 10% Confidence
        - 5% Recency
    """
    lexical = compute_lexical_score(query, memory.content)
    recency = compute_recency_score(memory.created_at)
    confidence = float(memory.confidence or 1.0)
    importance = float(memory.importance or 0.5)

    if semantic_similarity is not None:
        final_score = (
            0.45 * semantic_similarity
            + 0.25 * lexical
            + 0.15 * importance
            + 0.10 * confidence
            + 0.05 * recency
        )
    else:
        final_score = (
            0.65 * lexical
            + 0.20 * importance
            + 0.10 * confidence
            + 0.05 * recency
        )

    return round(max(0.0, min(1.0, final_score)), 4)
