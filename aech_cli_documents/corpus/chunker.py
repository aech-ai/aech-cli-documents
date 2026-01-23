"""Structure-aware chunking - chunk at section boundaries."""

import uuid
from typing import Optional

from .models import Chunk, Section
from .structure import DocumentTree, TreeNode, count_tokens_approx


MAX_CHUNK_TOKENS = 1500
MIN_CHUNK_TOKENS = 50
OVERLAP_TOKENS = 200


def build_enriched_content(
    content: str,
    section_title: Optional[str] = None,
    section_path: Optional[str] = None,
    section_summary: Optional[str] = None,
    semantic_type: Optional[str] = None,
    key_terms: Optional[list[str]] = None,
    hypothetical_questions: Optional[list[str]] = None,
) -> str:
    """
    Build enriched content for embedding.
    Combines section metadata with content to improve retrieval.
    """
    parts = []

    if section_path and section_title:
        parts.append(f"Section: {section_path} - {section_title}")

    if semantic_type:
        parts.append(f"Type: {semantic_type}")

    if section_summary:
        parts.append(f"Summary: {section_summary}")

    if key_terms:
        parts.append(f"Key Terms: {', '.join(key_terms)}")

    if hypothetical_questions:
        questions_str = "\n".join(f"Q: {q}" for q in hypothetical_questions)
        parts.append(f"Questions this section answers:\n{questions_str}")

    parts.append(f"\nContent:\n{content}")

    return "\n".join(parts)


def split_at_paragraphs(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split text at paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = count_tokens_approx(para)

        # If this paragraph alone exceeds max, we need to split it further
        if para_tokens > max_tokens:
            # First, flush current chunk if any
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_tokens = 0

            # Split long paragraph by sentences
            sentences = para.replace(". ", ".\n").split("\n")
            for sentence in sentences:
                sent_tokens = count_tokens_approx(sentence)
                if current_tokens + sent_tokens > max_tokens and current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    # Keep last item for overlap
                    overlap_text = current_chunk[-1] if current_chunk else ""
                    current_chunk = [overlap_text] if count_tokens_approx(overlap_text) < overlap_tokens else []
                    current_tokens = count_tokens_approx("\n\n".join(current_chunk))
                current_chunk.append(sentence)
                current_tokens += sent_tokens
            continue

        # Normal case: add paragraph if it fits
        if current_tokens + para_tokens > max_tokens and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            # Keep last paragraph for overlap
            overlap_text = current_chunk[-1] if current_chunk else ""
            if count_tokens_approx(overlap_text) < overlap_tokens:
                current_chunk = [overlap_text]
                current_tokens = count_tokens_approx(overlap_text)
            else:
                current_chunk = []
                current_tokens = 0

        current_chunk.append(para)
        current_tokens += para_tokens

    # Don't forget the last chunk
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def chunk_node(
    node: TreeNode,
    document_id: str,
    section: Optional[Section] = None,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    """
    Create chunks from a tree node.

    If the section content fits in one chunk, keep it intact.
    Otherwise, split at paragraph boundaries.
    """
    content = node.content
    if not content or not content.strip():
        return []

    token_count = count_tokens_approx(content)

    # Build enriched content using section enrichment if available
    enriched_kwargs = {
        "section_title": node.title,
        "section_path": node.path,
    }
    if section:
        enriched_kwargs.update({
            "section_summary": section.summary,
            "semantic_type": section.semantic_type,
            "key_terms": section.key_terms,
            "hypothetical_questions": section.hypothetical_questions,
        })

    chunks = []

    if token_count <= max_tokens:
        # Section fits in one chunk - keep intact
        enriched = build_enriched_content(content, **enriched_kwargs)
        chunks.append(Chunk(
            id=f"{document_id}_{node.id}_0",
            document_id=document_id,
            section_id=node.id,
            chunk_index=len(chunks),
            section_path=node.path,
            content=content,
            enriched_content=enriched,
            section_title=node.title,
            section_summary=section.summary if section else None,
            semantic_type=section.semantic_type if section else None,
            char_offset_start=0,
            char_offset_end=len(content),
        ))
    else:
        # Split at paragraph boundaries
        text_chunks = split_at_paragraphs(content, max_tokens, overlap_tokens)

        char_offset = 0
        for i, chunk_text in enumerate(text_chunks):
            if count_tokens_approx(chunk_text) < MIN_CHUNK_TOKENS:
                continue  # Skip tiny chunks

            enriched = build_enriched_content(chunk_text, **enriched_kwargs)

            chunks.append(Chunk(
                id=f"{document_id}_{node.id}_{i}",
                document_id=document_id,
                section_id=node.id,
                chunk_index=len(chunks),
                section_path=node.path,
                content=chunk_text,
                enriched_content=enriched,
                section_title=node.title,
                section_summary=section.summary if section else None,
                semantic_type=section.semantic_type if section else None,
                char_offset_start=char_offset,
                char_offset_end=char_offset + len(chunk_text),
            ))

            char_offset += len(chunk_text)

    return chunks


def chunk_document(
    tree: DocumentTree,
    document_id: str,
    sections: Optional[dict[str, Section]] = None,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    """
    Chunk an entire document using its structure tree.

    Args:
        tree: DocumentTree from extract_structure
        document_id: Document ID for chunk IDs
        sections: Optional dict mapping node IDs to Section models (with enrichment)
        max_tokens: Maximum tokens per chunk
        overlap_tokens: Overlap between chunks when splitting

    Returns:
        List of Chunk objects
    """
    sections = sections or {}
    all_chunks = []
    chunk_index = 0

    def walk(node: TreeNode):
        nonlocal chunk_index

        # Get enriched section if available
        section = sections.get(node.id)

        # Create chunks for this node's content
        node_chunks = chunk_node(
            node,
            document_id,
            section=section,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )

        # Update chunk indices to be document-global
        for chunk in node_chunks:
            chunk.chunk_index = chunk_index
            chunk_index += 1

        all_chunks.extend(node_chunks)

        # Recurse to children
        for child in node.children:
            walk(child)

    # Start from root (which may have preamble content)
    walk(tree.root)

    return all_chunks


def chunk_unstructured(
    text: str,
    document_id: str,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    """
    Chunk unstructured text (no markdown headers).
    Used for documents without clear section structure.
    """
    text_chunks = split_at_paragraphs(text, max_tokens, overlap_tokens)
    chunks = []

    char_offset = 0
    for i, chunk_text in enumerate(text_chunks):
        if count_tokens_approx(chunk_text) < MIN_CHUNK_TOKENS:
            continue

        chunks.append(Chunk(
            id=f"{document_id}_chunk_{i}",
            document_id=document_id,
            section_id=None,
            chunk_index=i,
            section_path=None,
            content=chunk_text,
            enriched_content=chunk_text,  # No enrichment for unstructured
            section_title=None,
            section_summary=None,
            semantic_type=None,
            char_offset_start=char_offset,
            char_offset_end=char_offset + len(chunk_text),
        ))

        char_offset += len(chunk_text)

    return chunks
