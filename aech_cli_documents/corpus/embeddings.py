"""Embedding generation using bge-m3 model."""

import os
from functools import lru_cache
from typing import Optional, Callable

import numpy as np


# Lazy loading to avoid slow import on CLI startup
_model = None


def get_model(model_name: str = "BAAI/bge-m3"):
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
    return _model


def encode_text(
    text: str,
    model_name: str = "BAAI/bge-m3",
) -> list[float]:
    """
    Encode a single text to embedding vector.

    Args:
        text: Text to encode
        model_name: Model to use

    Returns:
        List of floats (embedding vector)
    """
    model = get_model(model_name)
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def encode_batch(
    texts: list[str],
    model_name: str = "BAAI/bge-m3",
    batch_size: int = 8,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[list[float]]:
    """
    Encode multiple texts to embedding vectors.

    Args:
        texts: List of texts to encode
        model_name: Model to use
        batch_size: Batch size for encoding
        progress_callback: Optional callback(current, total, message)

    Returns:
        List of embedding vectors
    """
    if not texts:
        return []

    model = get_model(model_name)

    if progress_callback:
        progress_callback(0, len(texts), "Generating embeddings...")

    # Process in batches
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = model.encode(batch, normalize_embeddings=True)
        all_embeddings.extend(embeddings.tolist())

        if progress_callback:
            progress_callback(
                min(i + batch_size, len(texts)),
                len(texts),
                f"Encoded {min(i + batch_size, len(texts))}/{len(texts)} texts"
            )

    return all_embeddings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    Note: If vectors are already normalized (bge-m3 does this), dot product = cosine similarity.
    """
    a_np = np.array(a)
    b_np = np.array(b)
    return float(np.dot(a_np, b_np))


def batch_cosine_similarity(
    query_embedding: list[float],
    embeddings: list[list[float]],
) -> list[float]:
    """
    Compute cosine similarity between a query and multiple embeddings.
    Optimized for batch computation.
    """
    query_np = np.array(query_embedding)
    embeddings_np = np.array(embeddings)

    # Dot product (normalized vectors)
    similarities = np.dot(embeddings_np, query_np)
    return similarities.tolist()


def get_embedding_dimension(model_name: str = "BAAI/bge-m3") -> int:
    """Get the dimension of embeddings from this model."""
    model = get_model(model_name)
    return model.get_sentence_embedding_dimension()
