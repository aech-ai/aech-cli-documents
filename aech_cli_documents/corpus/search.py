"""Hybrid search - FTS + vector + RRF fusion with optional query expansion."""

import sqlite3
from typing import Optional

from .database import Corpus
from .embeddings import encode_text, batch_cosine_similarity
from .expansion import expand_query, QueryExpansion
from .models import SearchResult


# RRF constant - higher values give more weight to later ranks
RRF_K = 60

# Minimum vector similarity score
MIN_VECTOR_SCORE = 0.25


def fts_search(
    corpus: Corpus,
    query: str,
    limit: int = 50,
) -> list[tuple[str, float, int]]:
    """
    Full-text search using FTS5.

    Returns:
        List of (chunk_id, bm25_score, rank)
    """
    with corpus.connection() as conn:
        # FTS5 search with BM25 ranking
        rows = conn.execute("""
            SELECT
                id,
                bm25(chunks_fts) as score
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
            ORDER BY score
            LIMIT ?
        """, (query, limit)).fetchall()

        # Convert to list with ranks (BM25 scores are negative, more negative = better)
        results = []
        for rank, row in enumerate(rows, 1):
            results.append((row['id'], abs(row['score']), rank))

        return results


def vector_search(
    corpus: Corpus,
    query: str,
    limit: int = 50,
    min_score: float = MIN_VECTOR_SCORE,
) -> list[tuple[str, float, int]]:
    """
    Vector similarity search using embeddings.

    Returns:
        List of (chunk_id, cosine_similarity, rank)
    """
    corpus.ensure_configured_embedding_model()

    # Encode query
    query_embedding = encode_text(query)

    # Get all chunk embeddings
    chunk_embeddings = corpus.get_all_chunks_with_embeddings()

    if not chunk_embeddings:
        return []

    # Compute similarities
    chunk_ids = [ce[0] for ce in chunk_embeddings]
    embeddings = [ce[1] for ce in chunk_embeddings]

    similarities = batch_cosine_similarity(query_embedding, embeddings)

    # Filter and sort
    results = [
        (chunk_id, sim)
        for chunk_id, sim in zip(chunk_ids, similarities)
        if sim >= min_score
    ]
    results.sort(key=lambda x: x[1], reverse=True)
    results = results[:limit]

    # Add ranks
    return [(chunk_id, score, rank + 1) for rank, (chunk_id, score) in enumerate(results)]


def rrf_score(rank: int, k: int = RRF_K) -> float:
    """Reciprocal Rank Fusion score."""
    return 1.0 / (k + rank)


def hybrid_search(
    corpus: Corpus,
    query: str,
    limit: int = 20,
    fts_weight: float = 1.0,
    vector_weight: float = 1.0,
    semantic_types: Optional[list[str]] = None,
) -> list[SearchResult]:
    """
    Hybrid search combining FTS and vector search with RRF.

    Args:
        corpus: Corpus to search
        query: Search query
        limit: Maximum results
        fts_weight: Weight for FTS scores
        vector_weight: Weight for vector scores
        semantic_types: Optional filter by semantic type

    Returns:
        List of SearchResult objects
    """
    # Run both searches
    fts_results = fts_search(corpus, query, limit=limit * 2)
    vector_results = vector_search(corpus, query, limit=limit * 2)

    # Build score maps
    fts_scores = {chunk_id: (score, rank) for chunk_id, score, rank in fts_results}
    vector_scores = {chunk_id: (score, rank) for chunk_id, score, rank in vector_results}

    # Combine all chunk IDs
    all_chunk_ids = set(fts_scores.keys()) | set(vector_scores.keys())

    # Calculate RRF scores
    combined_scores = []
    for chunk_id in all_chunk_ids:
        fts_score, fts_rank = fts_scores.get(chunk_id, (0, len(fts_results) + 100))
        vec_score, vec_rank = vector_scores.get(chunk_id, (0, len(vector_results) + 100))

        # RRF combination
        rrf_total = (
            fts_weight * rrf_score(fts_rank) +
            vector_weight * rrf_score(vec_rank)
        )

        combined_scores.append({
            "chunk_id": chunk_id,
            "combined_score": rrf_total,
            "fts_score": fts_score if chunk_id in fts_scores else None,
            "vector_score": vec_score if chunk_id in vector_scores else None,
            "fts_rank": fts_rank if chunk_id in fts_scores else None,
            "vector_rank": vec_rank if chunk_id in vector_scores else None,
        })

    # Sort by combined score
    combined_scores.sort(key=lambda x: x["combined_score"], reverse=True)

    # Fetch chunk details and build results
    results = []
    with corpus.connection() as conn:
        for item in combined_scores[:limit * 2]:  # Fetch extra for filtering
            row = conn.execute("""
                SELECT c.*, d.name as document_name
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.id = ?
            """, (item["chunk_id"],)).fetchone()

            if not row:
                continue

            # Apply semantic type filter
            if semantic_types and row['semantic_type'] not in semantic_types:
                continue

            # Create preview
            content = row['content'] or ""
            preview = content[:300] + "..." if len(content) > 300 else content

            results.append(SearchResult(
                chunk_id=row['id'],
                document_id=row['document_id'],
                document_name=row['document_name'],
                section_path=row['section_path'],
                section_title=row['section_title'],
                content=content,
                content_preview=preview,
                score=item["combined_score"],
                fts_score=item["fts_score"],
                vector_score=item["vector_score"],
                fts_rank=item["fts_rank"],
                vector_rank=item["vector_rank"],
                semantic_type=row['semantic_type'],
                section_summary=row['section_summary'],
            ))

            if len(results) >= limit:
                break

    return results


def expanded_hybrid_search(
    corpus: Corpus,
    query: str,
    limit: int = 20,
    fts_weight: float = 1.0,
    vector_weight: float = 1.0,
    semantic_types: Optional[list[str]] = None,
) -> list[SearchResult]:
    """
    Hybrid search with query expansion for improved recall.

    Expands the query into multiple variants (lex, vec, hyde) using an LLM,
    then searches with all variants and combines results with RRF.

    Args:
        corpus: Corpus to search
        query: Search query
        limit: Maximum results
        fts_weight: Weight for FTS scores
        vector_weight: Weight for vector scores
        semantic_types: Optional filter by semantic type

    Returns:
        List of SearchResult objects
    """
    # Expand query using LLM (cached)
    expanded = expand_query(
        query,
        get_cache_fn=corpus.get_cache,
        set_cache_fn=corpus.set_cache,
    )

    # Build query lists - original query always included with 2x weight
    queries_fts = [query, query] + expanded.lex  # Original 2x + expansions
    queries_vec = [query, query] + expanded.vec + [expanded.hyde]  # Original 2x + expansions + hyde

    # Collect FTS results from all variants
    fts_scores: dict[str, tuple[float, int]] = {}
    for q in queries_fts:
        try:
            for chunk_id, score, rank in fts_search(corpus, q, limit=limit):
                if chunk_id not in fts_scores or score > fts_scores[chunk_id][0]:
                    fts_scores[chunk_id] = (score, rank)
        except Exception:
            # FTS can fail on certain query patterns, skip this variant
            continue

    # Collect vector results from all variants
    vector_scores: dict[str, tuple[float, int]] = {}
    for q in queries_vec:
        if not q:
            continue
        for chunk_id, score, rank in vector_search(corpus, q, limit=limit):
            if chunk_id not in vector_scores or score > vector_scores[chunk_id][0]:
                vector_scores[chunk_id] = (score, rank)

    # Combine all chunk IDs
    all_chunk_ids = set(fts_scores.keys()) | set(vector_scores.keys())

    # Calculate RRF scores
    combined_scores = []
    for chunk_id in all_chunk_ids:
        fts_score, fts_rank = fts_scores.get(chunk_id, (0, len(fts_scores) + 100))
        vec_score, vec_rank = vector_scores.get(chunk_id, (0, len(vector_scores) + 100))

        # RRF combination
        rrf_total = (
            fts_weight * rrf_score(fts_rank) +
            vector_weight * rrf_score(vec_rank)
        )

        combined_scores.append({
            "chunk_id": chunk_id,
            "combined_score": rrf_total,
            "fts_score": fts_score if chunk_id in fts_scores else None,
            "vector_score": vec_score if chunk_id in vector_scores else None,
            "fts_rank": fts_rank if chunk_id in fts_scores else None,
            "vector_rank": vec_rank if chunk_id in vector_scores else None,
        })

    # Sort by combined score
    combined_scores.sort(key=lambda x: x["combined_score"], reverse=True)

    # Fetch chunk details and build results
    results = []
    with corpus.connection() as conn:
        for item in combined_scores[:limit * 2]:  # Fetch extra for filtering
            row = conn.execute("""
                SELECT c.*, d.name as document_name
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.id = ?
            """, (item["chunk_id"],)).fetchone()

            if not row:
                continue

            # Apply semantic type filter
            if semantic_types and row['semantic_type'] not in semantic_types:
                continue

            # Create preview
            content = row['content'] or ""
            preview = content[:300] + "..." if len(content) > 300 else content

            results.append(SearchResult(
                chunk_id=row['id'],
                document_id=row['document_id'],
                document_name=row['document_name'],
                section_path=row['section_path'],
                section_title=row['section_title'],
                content=content,
                content_preview=preview,
                score=item["combined_score"],
                fts_score=item["fts_score"],
                vector_score=item["vector_score"],
                fts_rank=item["fts_rank"],
                vector_rank=item["vector_rank"],
                semantic_type=row['semantic_type'],
                section_summary=row['section_summary'],
            ))

            if len(results) >= limit:
                break

    return results


def search_documents(
    corpus: Corpus,
    query: str,
    limit: int = 20,
) -> list[dict]:
    """
    Search at document level using FTS.

    Returns:
        List of document dicts with scores
    """
    with corpus.connection() as conn:
        rows = conn.execute("""
            SELECT
                d.*,
                bm25(documents_fts) as score
            FROM documents_fts
            JOIN documents d ON documents_fts.id = d.id
            WHERE documents_fts MATCH ?
            ORDER BY score
            LIMIT ?
        """, (query, limit)).fetchall()

        return [dict(row) for row in rows]


def expand_context(
    corpus: Corpus,
    results: list[SearchResult],
) -> list[SearchResult]:
    """
    Expand search results with parent/sibling context from tree structure.
    """
    for result in results:
        if not result.section_path:
            continue

        # Find parent section
        parent_path = ".".join(result.section_path.split(".")[:-1])
        if parent_path:
            with corpus.connection() as conn:
                parent = conn.execute("""
                    SELECT summary FROM sections
                    WHERE document_id = ? AND path = ?
                """, (result.document_id, parent_path)).fetchone()

                if parent and parent['summary']:
                    result.parent_summary = parent['summary']

                # Find siblings
                siblings = conn.execute("""
                    SELECT title FROM sections
                    WHERE document_id = ? AND path LIKE ? AND path != ?
                """, (
                    result.document_id,
                    parent_path + ".%",
                    result.section_path
                )).fetchall()

                result.sibling_titles = [s['title'] for s in siblings]

    return results
