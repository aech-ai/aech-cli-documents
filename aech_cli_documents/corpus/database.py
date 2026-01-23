"""SQLite corpus database with FTS5 and embedding storage."""

import json
import sqlite3
import struct
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .models import Document, Section, Chunk, CorpusInfo


SCHEMA = """
-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_path TEXT,
    content_type TEXT,
    raw_markdown TEXT,
    title TEXT,
    author TEXT,
    created_date DATETIME,
    tags TEXT,
    metadata_json TEXT,
    enriched_at DATETIME,
    section_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_enriched ON documents(enriched_at);

-- Sections table (hierarchical structure)
CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    parent_id TEXT,
    level INTEGER NOT NULL,
    path TEXT NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT,
    key_terms TEXT,
    hypothetical_questions TEXT,
    semantic_type TEXT,
    entities TEXT,
    importance_score REAL,
    start_line INTEGER,
    end_line INTEGER,
    token_count INTEGER DEFAULT 0,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES sections(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sections_document ON sections(document_id);
CREATE INDEX IF NOT EXISTS idx_sections_parent ON sections(parent_id);
CREATE INDEX IF NOT EXISTS idx_sections_path ON sections(path);
CREATE INDEX IF NOT EXISTS idx_sections_type ON sections(semantic_type);

-- Chunks table (searchable units)
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    section_id TEXT,
    chunk_index INTEGER NOT NULL,
    section_path TEXT,
    content TEXT NOT NULL,
    enriched_content TEXT,
    embedding BLOB,
    section_title TEXT,
    section_summary TEXT,
    semantic_type TEXT,
    char_offset_start INTEGER,
    char_offset_end INTEGER,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section_id);
CREATE INDEX IF NOT EXISTS idx_chunks_type ON chunks(semantic_type);

-- Full-text search for chunks
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    id UNINDEXED,
    content,
    enriched_content,
    section_title,
    tokenize = 'porter'
);

-- Full-text search for documents
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    id UNINDEXED,
    name,
    title,
    raw_markdown,
    tokenize = 'porter'
);

-- Corpus metadata
CREATE TABLE IF NOT EXISTS corpus_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Triggers for FTS sync
CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(id, content, enriched_content, section_title)
    VALUES (NEW.id, NEW.content, NEW.enriched_content, NEW.section_title);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_update AFTER UPDATE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE id = OLD.id;
    INSERT INTO chunks_fts(id, content, enriched_content, section_title)
    VALUES (NEW.id, NEW.content, NEW.enriched_content, NEW.section_title);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS documents_fts_insert AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(id, name, title, raw_markdown)
    VALUES (NEW.id, NEW.name, NEW.title, NEW.raw_markdown);
END;

CREATE TRIGGER IF NOT EXISTS documents_fts_update AFTER UPDATE ON documents BEGIN
    DELETE FROM documents_fts WHERE id = OLD.id;
    INSERT INTO documents_fts(id, name, title, raw_markdown)
    VALUES (NEW.id, NEW.name, NEW.title, NEW.raw_markdown);
END;

CREATE TRIGGER IF NOT EXISTS documents_fts_delete AFTER DELETE ON documents BEGIN
    DELETE FROM documents_fts WHERE id = OLD.id;
END;
"""


def embedding_to_bytes(embedding: list[float]) -> bytes:
    """Convert float list to binary blob."""
    return struct.pack(f'{len(embedding)}f', *embedding)


def bytes_to_embedding(blob: bytes) -> list[float]:
    """Convert binary blob to float list."""
    count = len(blob) // 4
    return list(struct.unpack(f'{count}f', blob))


class Corpus:
    """A document corpus backed by SQLite."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection with WAL mode."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield self._conn
        except Exception:
            self._conn.rollback()
            raise

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # Document operations

    def add_document(self, doc: Document) -> str:
        """Add a document to the corpus."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO documents (
                    id, name, source_type, source_path, content_type,
                    raw_markdown, title, author, created_date, tags,
                    metadata_json, enriched_at, section_count, chunk_count,
                    token_count, ingested_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc.id, doc.name, doc.source_type, doc.source_path, doc.content_type,
                doc.raw_markdown, doc.title, doc.author,
                doc.created_date.isoformat() if doc.created_date else None,
                json.dumps(doc.tags), json.dumps(doc.metadata),
                doc.enriched_at.isoformat() if doc.enriched_at else None,
                doc.section_count, doc.chunk_count, doc.token_count,
                doc.ingested_at.isoformat(), doc.updated_at.isoformat()
            ))
            conn.commit()
        return doc.id

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a document by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            if row:
                return self._row_to_document(row)
        return None

    def list_documents(
        self,
        source_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[Document]:
        """List documents with optional filtering."""
        with self.connection() as conn:
            if source_type:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE source_type = ? ORDER BY ingested_at DESC LIMIT ? OFFSET ?",
                    (source_type, limit, offset)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM documents ORDER BY ingested_at DESC LIMIT ? OFFSET ?",
                    (limit, offset)
                ).fetchall()
            return [self._row_to_document(row) for row in rows]

    def update_document(self, doc: Document) -> None:
        """Update a document."""
        with self.connection() as conn:
            conn.execute("""
                UPDATE documents SET
                    name = ?, source_type = ?, source_path = ?, content_type = ?,
                    raw_markdown = ?, title = ?, author = ?, created_date = ?,
                    tags = ?, metadata_json = ?, enriched_at = ?,
                    section_count = ?, chunk_count = ?, token_count = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                doc.name, doc.source_type, doc.source_path, doc.content_type,
                doc.raw_markdown, doc.title, doc.author,
                doc.created_date.isoformat() if doc.created_date else None,
                json.dumps(doc.tags), json.dumps(doc.metadata),
                doc.enriched_at.isoformat() if doc.enriched_at else None,
                doc.section_count, doc.chunk_count, doc.token_count,
                datetime.utcnow().isoformat(), doc.id
            ))
            conn.commit()

    def delete_document(self, doc_id: str) -> None:
        """Delete a document and all its sections/chunks."""
        with self.connection() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()

    # Section operations

    def add_section(self, section: Section) -> str:
        """Add a section to the corpus."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO sections (
                    id, document_id, parent_id, level, path, position,
                    title, content, summary, key_terms, hypothetical_questions,
                    semantic_type, entities, importance_score,
                    start_line, end_line, token_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                section.id, section.document_id, section.parent_id,
                section.level, section.path, section.position,
                section.title, section.content, section.summary,
                json.dumps(section.key_terms), json.dumps(section.hypothetical_questions),
                section.semantic_type, json.dumps(section.entities),
                section.importance_score, section.start_line, section.end_line,
                section.token_count
            ))
            conn.commit()
        return section.id

    def get_sections_for_document(self, doc_id: str) -> list[Section]:
        """Get all sections for a document."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sections WHERE document_id = ? ORDER BY path",
                (doc_id,)
            ).fetchall()
            return [self._row_to_section(row) for row in rows]

    def get_section(self, section_id: str) -> Optional[Section]:
        """Get a section by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM sections WHERE id = ?", (section_id,)
            ).fetchone()
            if row:
                return self._row_to_section(row)
        return None

    def update_section(self, section: Section) -> None:
        """Update a section (typically for enrichment)."""
        with self.connection() as conn:
            conn.execute("""
                UPDATE sections SET
                    summary = ?, key_terms = ?, hypothetical_questions = ?,
                    semantic_type = ?, entities = ?, importance_score = ?
                WHERE id = ?
            """, (
                section.summary, json.dumps(section.key_terms),
                json.dumps(section.hypothetical_questions), section.semantic_type,
                json.dumps(section.entities), section.importance_score, section.id
            ))
            conn.commit()

    # Chunk operations

    def add_chunk(self, chunk: Chunk) -> str:
        """Add a chunk to the corpus."""
        embedding_blob = embedding_to_bytes(chunk.embedding) if chunk.embedding else None
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO chunks (
                    id, document_id, section_id, chunk_index, section_path,
                    content, enriched_content, embedding, section_title,
                    section_summary, semantic_type, char_offset_start, char_offset_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk.id, chunk.document_id, chunk.section_id, chunk.chunk_index,
                chunk.section_path, chunk.content, chunk.enriched_content,
                embedding_blob, chunk.section_title, chunk.section_summary,
                chunk.semantic_type, chunk.char_offset_start, chunk.char_offset_end
            ))
            conn.commit()
        return chunk.id

    def add_chunks_batch(self, chunks: list[Chunk]) -> None:
        """Add multiple chunks in a single transaction."""
        with self.connection() as conn:
            for chunk in chunks:
                embedding_blob = embedding_to_bytes(chunk.embedding) if chunk.embedding else None
                conn.execute("""
                    INSERT INTO chunks (
                        id, document_id, section_id, chunk_index, section_path,
                        content, enriched_content, embedding, section_title,
                        section_summary, semantic_type, char_offset_start, char_offset_end
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chunk.id, chunk.document_id, chunk.section_id, chunk.chunk_index,
                    chunk.section_path, chunk.content, chunk.enriched_content,
                    embedding_blob, chunk.section_title, chunk.section_summary,
                    chunk.semantic_type, chunk.char_offset_start, chunk.char_offset_end
                ))
            conn.commit()

    def get_chunks_for_document(self, doc_id: str) -> list[Chunk]:
        """Get all chunks for a document."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index",
                (doc_id,)
            ).fetchall()
            return [self._row_to_chunk(row) for row in rows]

    def get_all_chunks_with_embeddings(self) -> list[tuple[str, list[float]]]:
        """Get all chunk IDs and embeddings for vector search."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL"
            ).fetchall()
            return [(row['id'], bytes_to_embedding(row['embedding'])) for row in rows]

    def update_chunk_embedding(self, chunk_id: str, embedding: list[float]) -> None:
        """Update a chunk's embedding."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE chunks SET embedding = ? WHERE id = ?",
                (embedding_to_bytes(embedding), chunk_id)
            )
            conn.commit()

    # Corpus metadata

    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a metadata value."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT value FROM corpus_meta WHERE key = ?", (key,)
            ).fetchone()
            return row['value'] if row else default

    def set_meta(self, key: str, value: str) -> None:
        """Set a metadata value."""
        with self.connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO corpus_meta (key, value) VALUES (?, ?)",
                (key, value)
            )
            conn.commit()

    def get_info(self) -> CorpusInfo:
        """Get corpus statistics."""
        with self.connection() as conn:
            doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            section_count = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0

        return CorpusInfo(
            name=self.get_meta('name', self.db_path.stem),
            path=str(self.db_path),
            document_count=doc_count,
            section_count=section_count,
            chunk_count=chunk_count,
            size_bytes=size_bytes,
            created_at=datetime.fromisoformat(
                self.get_meta('created_at', datetime.utcnow().isoformat())
            ),
            updated_at=datetime.fromisoformat(
                self.get_meta('updated_at', datetime.utcnow().isoformat())
            ),
            embedding_model=self.get_meta('embedding_model', 'BAAI/bge-m3')
        )

    # Row converters

    def _row_to_document(self, row: sqlite3.Row) -> Document:
        return Document(
            id=row['id'],
            name=row['name'],
            source_type=row['source_type'],
            source_path=row['source_path'],
            content_type=row['content_type'],
            raw_markdown=row['raw_markdown'],
            title=row['title'],
            author=row['author'],
            created_date=datetime.fromisoformat(row['created_date']) if row['created_date'] else None,
            tags=json.loads(row['tags']) if row['tags'] else [],
            metadata=json.loads(row['metadata_json']) if row['metadata_json'] else {},
            enriched_at=datetime.fromisoformat(row['enriched_at']) if row['enriched_at'] else None,
            section_count=row['section_count'],
            chunk_count=row['chunk_count'],
            token_count=row['token_count'],
            ingested_at=datetime.fromisoformat(row['ingested_at']),
            updated_at=datetime.fromisoformat(row['updated_at'])
        )

    def _row_to_section(self, row: sqlite3.Row) -> Section:
        return Section(
            id=row['id'],
            document_id=row['document_id'],
            parent_id=row['parent_id'],
            level=row['level'],
            path=row['path'],
            position=row['position'],
            title=row['title'],
            content=row['content'],
            summary=row['summary'],
            key_terms=json.loads(row['key_terms']) if row['key_terms'] else [],
            hypothetical_questions=json.loads(row['hypothetical_questions']) if row['hypothetical_questions'] else [],
            semantic_type=row['semantic_type'],
            entities=json.loads(row['entities']) if row['entities'] else [],
            importance_score=row['importance_score'],
            start_line=row['start_line'],
            end_line=row['end_line'],
            token_count=row['token_count']
        )

    def _row_to_chunk(self, row: sqlite3.Row) -> Chunk:
        return Chunk(
            id=row['id'],
            document_id=row['document_id'],
            section_id=row['section_id'],
            chunk_index=row['chunk_index'],
            section_path=row['section_path'],
            content=row['content'],
            enriched_content=row['enriched_content'],
            embedding=bytes_to_embedding(row['embedding']) if row['embedding'] else None,
            section_title=row['section_title'],
            section_summary=row['section_summary'],
            semantic_type=row['semantic_type'],
            char_offset_start=row['char_offset_start'],
            char_offset_end=row['char_offset_end']
        )


def create_corpus(db_path: str | Path, name: Optional[str] = None) -> Corpus:
    """Create a new corpus database."""
    db_path = Path(db_path)

    # Create parent directories if needed
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create and initialize database
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.close()

    # Set initial metadata
    corpus = Corpus(db_path)
    corpus.set_meta('name', name or db_path.stem)
    corpus.set_meta('created_at', datetime.utcnow().isoformat())
    corpus.set_meta('updated_at', datetime.utcnow().isoformat())
    corpus.set_meta('embedding_model', 'BAAI/bge-m3')

    return corpus
