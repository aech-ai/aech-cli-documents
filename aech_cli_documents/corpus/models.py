"""Pydantic models for documents, sections, and chunks."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Document(BaseModel):
    """A document in the corpus."""

    id: str
    name: str
    source_type: str  # 'file', 'email', 'url', 'teams', etc.
    source_path: Optional[str] = None
    content_type: Optional[str] = None

    # Raw content
    raw_markdown: Optional[str] = None

    # Document-level metadata
    title: Optional[str] = None
    author: Optional[str] = None
    created_date: Optional[datetime] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    # Processing status
    enriched_at: Optional[datetime] = None
    section_count: int = 0
    chunk_count: int = 0
    token_count: int = 0

    # Timestamps
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Section(BaseModel):
    """A section within a document (hierarchical structure)."""

    id: str
    document_id: str
    parent_id: Optional[str] = None

    # Structure
    level: int  # 1-6 from markdown headers
    path: str  # "3.2.1" style hierarchical path
    position: int  # order within parent

    # Content
    title: str
    content: Optional[str] = None  # full section content (without children)

    # Enrichment fields (LLM-generated at index time)
    summary: Optional[str] = None
    key_terms: list[str] = Field(default_factory=list)
    hypothetical_questions: list[str] = Field(default_factory=list)
    semantic_type: Optional[str] = None  # definitions, obligations, rights, procedures, etc.
    entities: list[dict] = Field(default_factory=list)  # [{name, type}, ...]
    importance_score: Optional[float] = None  # 0-1

    # Metadata
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    token_count: int = 0


class Chunk(BaseModel):
    """A searchable chunk of content."""

    id: str
    document_id: str
    section_id: Optional[str] = None

    # Position
    chunk_index: int
    section_path: Optional[str] = None

    # Content
    content: str
    enriched_content: Optional[str] = None  # what gets embedded

    # Embedding (stored as bytes in DB, converted here)
    embedding: Optional[list[float]] = None

    # Metadata from section (denormalized)
    section_title: Optional[str] = None
    section_summary: Optional[str] = None
    semantic_type: Optional[str] = None

    # Location in source
    char_offset_start: Optional[int] = None
    char_offset_end: Optional[int] = None


class SearchResult(BaseModel):
    """A search result with relevance information."""

    chunk_id: str
    document_id: str
    document_name: str
    section_path: Optional[str] = None
    section_title: Optional[str] = None

    # Content
    content: str
    content_preview: str  # truncated for display

    # Scores
    score: float
    fts_score: Optional[float] = None
    vector_score: Optional[float] = None
    fts_rank: Optional[int] = None
    vector_rank: Optional[int] = None

    # Context
    semantic_type: Optional[str] = None
    section_summary: Optional[str] = None

    # For tree navigation
    parent_summary: Optional[str] = None
    sibling_titles: list[str] = Field(default_factory=list)


class SectionEnrichment(BaseModel):
    """LLM-generated enrichment for a section."""

    summary: str
    key_terms: list[str]
    hypothetical_questions: list[str]
    semantic_type: str
    entities: list[dict]
    importance_score: float


class CorpusInfo(BaseModel):
    """Statistics about a corpus."""

    name: str
    path: str
    document_count: int
    section_count: int
    chunk_count: int
    size_bytes: int
    created_at: datetime
    updated_at: datetime
    embedding_model: str
