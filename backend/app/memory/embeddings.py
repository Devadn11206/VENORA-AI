"""Embedding provider abstraction and vector similarity computations for semantic retrieval."""

from abc import ABC, abstractmethod
import math
from typing import List, Optional, Dict
import hashlib
import json

from app.core.logging import get_logger
from app.core.errors import EmbeddingError

logger = get_logger("memory.embeddings")


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    val = dot_product / (norm_a * norm_b)
    # Clamp to [0.0, 1.0] for similarity measure
    return max(0.0, min(1.0, (val + 1.0) / 2.0))


class BaseEmbeddingProvider(ABC):
    """Abstract base class for memory vector embedding providers."""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generate a vector embedding for a single text chunk."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate vector embeddings for a list of texts."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name/identifier of the embedding model."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of vectors produced by this model."""
        pass


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic hash-based embedding provider for unit tests and offline testing.

    Generates normalized pseudo-embeddings derived from character n-grams and text hash,
    allowing semantic tests to verify vector ranking without downloading models or calling external APIs.
    """

    def __init__(self, dimension: int = 64, model_name: str = "mock-deterministic-v1") -> None:
        self._dim = dimension
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_text(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self._dim

        # Create a deterministic vector using token hashes + character frequencies
        vec = [0.0] * self._dim
        tokens = text.lower().split()
        for token in tokens:
            thash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = thash % self._dim
            vec[idx] += 1.0

        # Normalize vector
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]


def get_embedding_provider(
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None
) -> Optional[BaseEmbeddingProvider]:
    """Factory to get the configured embedding provider, or None if disabled/unconfigured."""
    if not provider_type:
        return None
    
    p = provider_type.strip().lower()
    if p in ("mock", "test"):
        return MockEmbeddingProvider(model_name=model_name or "mock-deterministic-v1")
    
    logger.warning(f"Unknown or unsupported embedding provider: '{provider_type}'. Falling back to lexical retrieval.")
    return None
