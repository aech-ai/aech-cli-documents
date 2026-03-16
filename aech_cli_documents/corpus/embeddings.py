"""Embedding generation via an OpenAI-compatible endpoint such as LM Studio."""

import logging
import os
from typing import Callable, Optional

import numpy as np


logger = logging.getLogger(__name__)

DEFAULT_MODEL = "text-embedding-bge-m3@fp16"
DEFAULT_API_KEY = "lm-studio"
DEFAULT_BATCH_SIZE = 8
DEFAULT_TIMEOUT_SECONDS = 60.0

_client = None
_client_config = None
_embedding_dim = None


def get_configured_embedding_model() -> str:
    """Return the configured embedding model name."""
    model_name = os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL).strip()
    if not model_name:
        raise RuntimeError("EMBEDDING_MODEL must be set")
    return model_name


def _get_base_url() -> str:
    base_url = os.getenv("EMBEDDING_BASE_URL", "").strip()
    if not base_url:
        raise RuntimeError(
            "EMBEDDING_BASE_URL must be set to an OpenAI-compatible embeddings endpoint"
        )
    return base_url


def _get_api_key() -> str:
    return os.getenv("EMBEDDING_API_KEY", "").strip() or DEFAULT_API_KEY


def _get_batch_size(default: int = DEFAULT_BATCH_SIZE) -> int:
    raw_value = os.getenv("EMBEDDING_BATCH_SIZE", str(default)).strip()
    return max(1, int(raw_value))


def _get_timeout_seconds() -> float:
    raw_value = os.getenv("EMBEDDING_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)).strip()
    return float(raw_value)


def _get_openai_client():
    """Lazy-load the OpenAI-compatible client."""
    global _client, _client_config
    config = (_get_base_url(), _get_api_key(), _get_timeout_seconds())
    if _client is None or _client_config != config:
        from openai import OpenAI

        logger.info(
            "Connecting to OpenAI-compatible embedding backend at %s with model %s",
            config[0],
            get_configured_embedding_model(),
        )
        _client = OpenAI(
            base_url=config[0],
            api_key=config[1],
            timeout=config[2],
        )
        _client_config = config
    return _client


def _encode_openai_batch(texts: list[str]) -> list[list[float]]:
    """Encode a batch of texts through an OpenAI-compatible endpoint."""
    global _embedding_dim

    client = _get_openai_client()
    response = client.embeddings.create(
        model=get_configured_embedding_model(),
        input=texts,
    )
    ordered = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    if ordered and _embedding_dim is None:
        _embedding_dim = len(ordered[0])
        logger.info("Detected embedding dimension: %s", _embedding_dim)

    return ordered


def encode_text(
    text: str,
    model_name: Optional[str] = None,
) -> list[float]:
    """
    Encode a single text to an embedding vector.
    """
    configured_model = get_configured_embedding_model()
    if model_name and model_name != configured_model:
        raise RuntimeError(
            f"Requested embedding model {model_name!r} does not match configured model {configured_model!r}"
        )
    return _encode_openai_batch([text])[0]


def encode_batch(
    texts: list[str],
    model_name: Optional[str] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[list[float]]:
    """
    Encode multiple texts to embedding vectors.
    """
    configured_model = get_configured_embedding_model()
    if model_name and model_name != configured_model:
        raise RuntimeError(
            f"Requested embedding model {model_name!r} does not match configured model {configured_model!r}"
        )
    if not texts:
        return []

    effective_batch_size = _get_batch_size(batch_size)

    if progress_callback:
        progress_callback(0, len(texts), "Generating embeddings...")

    all_embeddings: list[list[float]] = []
    for index in range(0, len(texts), effective_batch_size):
        batch = texts[index:index + effective_batch_size]
        all_embeddings.extend(_encode_openai_batch(batch))
        if progress_callback:
            progress_callback(
                min(index + effective_batch_size, len(texts)),
                len(texts),
                f"Encoded {min(index + effective_batch_size, len(texts))}/{len(texts)} texts",
            )

    return all_embeddings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    """
    a_np = np.array(a, dtype=float)
    b_np = np.array(b, dtype=float)
    norm_a = float(np.linalg.norm(a_np))
    norm_b = float(np.linalg.norm(b_np))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a_np, b_np) / (norm_a * norm_b))


def batch_cosine_similarity(
    query_embedding: list[float],
    embeddings: list[list[float]],
) -> list[float]:
    """
    Compute cosine similarity between a query and multiple embeddings.
    Optimized for batch computation.
    """
    if not embeddings:
        return []

    query_np = np.array(query_embedding, dtype=float)
    embeddings_np = np.array(embeddings, dtype=float)

    query_norm = float(np.linalg.norm(query_np))
    embedding_norms = np.linalg.norm(embeddings_np, axis=1)
    if query_norm == 0.0:
        return [0.0] * len(embeddings)

    dot_products = np.dot(embeddings_np, query_np)
    similarities = np.divide(
        dot_products,
        embedding_norms * query_norm,
        out=np.zeros_like(dot_products, dtype=float),
        where=embedding_norms != 0,
    )
    return similarities.tolist()


def get_embedding_dimension(model_name: Optional[str] = None) -> int:
    """Get the configured embedding dimension."""
    configured_model = get_configured_embedding_model()
    if model_name and model_name != configured_model:
        raise RuntimeError(
            f"Requested embedding model {model_name!r} does not match configured model {configured_model!r}"
        )

    global _embedding_dim
    if _embedding_dim is None:
        _encode_openai_batch(["dimension probe"])
    return _embedding_dim or 0
