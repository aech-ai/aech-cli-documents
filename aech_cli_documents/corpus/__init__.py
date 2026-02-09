"""
Universal Document Corpus - Agent Aech's document intelligence capability.

This module provides:
- Document ingestion with VLM-based conversion
- Structure extraction from markdown
- LLM-powered enrichment (summaries, HyDE questions, classification)
- Hybrid search (FTS + vector + RRF)
- SQLite-based corpus storage
"""

from .database import Corpus, create_corpus
from .models import Document, Section, Chunk, SearchResult
from .search import hybrid_search, expanded_hybrid_search, vector_search, fts_search
from .expansion import expand_query, QueryExpansion
from .structure import extract_structure, DocumentTree
from .chunker import chunk_document
from .embeddings import encode_text, encode_batch
from .enrichment import enrich_section, enrich_document
from .vlm import convert_to_markdown_vlm

__all__ = [
    # Database
    "Corpus",
    "create_corpus",
    # Models
    "Document",
    "Section",
    "Chunk",
    "SearchResult",
    # Search
    "hybrid_search",
    "expanded_hybrid_search",
    "vector_search",
    "fts_search",
    # Query Expansion
    "expand_query",
    "QueryExpansion",
    # Structure
    "extract_structure",
    "DocumentTree",
    # Chunking
    "chunk_document",
    # Embeddings
    "encode_text",
    "encode_batch",
    # Enrichment
    "enrich_section",
    "enrich_document",
    # VLM
    "convert_to_markdown_vlm",
]
