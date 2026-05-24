"""
Gemini Embedding Wrapper for Asirive Copartner
===============================================
Thin adapter that wraps GeminiClient.get_embeddings() into a callable
suitable for injecting into MemoryManager's ChromaDB collections.

Also includes a session-level cache to avoid re-embedding identical strings.
"""

import logging
from typing import Callable

logger = logging.getLogger("Copartner.Embeddings")


class GeminiEmbedder:
    """
    Wraps the Gemini Embedding API for use with ChromaDB.

    Usage:
        from core.gemini_client import GeminiClient
        from memory.embeddings import GeminiEmbedder

        client = GeminiClient()
        embedder = GeminiEmbedder(client)
        vecs = embedder.embed(["hello world", "another text"])
    """

    def __init__(self, gemini_client):
        self._client = gemini_client
        self._cache: dict[str, list[float]] = {}
        logger.info("GeminiEmbedder initialized")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of strings. Results are cached per session to save tokens.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).
        """
        results: list[list[float] | None] = [None] * len(texts)
        uncached_idx: list[int] = []
        uncached_texts: list[str] = []

        # Check cache first
        for i, text in enumerate(texts):
            if text in self._cache:
                results[i] = self._cache[text]
            else:
                uncached_idx.append(i)
                uncached_texts.append(text)

        # Embed only uncached texts
        if uncached_texts:
            try:
                new_vecs = self._client.get_embeddings(uncached_texts)
                for i, (idx, text) in enumerate(zip(uncached_idx, uncached_texts)):
                    self._cache[text] = new_vecs[i]
                    results[idx] = new_vecs[i]
                logger.debug(f"Embedded {len(uncached_texts)} new texts ({len(self._cache)} cached)")
            except Exception as e:
                logger.error(f"Embedding failed: {e}")
                # Return zero vectors as fallback so memory ops don't crash
                for idx in uncached_idx:
                    results[idx] = [0.0] * 768

        return results  # type: ignore

    def clear_cache(self):
        """Clear the session embedding cache."""
        self._cache.clear()
        logger.debug("Embedding cache cleared")

    @property
    def cache_size(self) -> int:
        return len(self._cache)


def make_chromadb_embedding_fn(embedder: GeminiEmbedder) -> Callable:
    """
    Returns a ChromaDB-compatible embedding function object.
    ChromaDB expects an object with a __call__(input: list[str]) -> list[list[float]] method.
    """
    class _ChromaEmbedFn:
        def name(self) -> str:
            return "gemini-embedder"

        def __call__(self, input: list[str]) -> list[list[float]]:
            return embedder.embed(input)

    return _ChromaEmbedFn()
