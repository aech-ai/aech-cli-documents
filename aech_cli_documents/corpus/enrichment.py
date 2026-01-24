"""LLM-powered section enrichment - summaries, HyDE questions, classification.

Uses pydantic-ai with model configuration from environment variables.
"""

import os
from typing import Optional, Callable

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from .models import Section, SectionEnrichment
from .model_utils import parse_model_string, get_model_settings
from .structure import TreeNode


class EnrichmentOutput(BaseModel):
    """Structured output for section enrichment."""

    summary: str = Field(description="1-2 sentence summary of what this section covers")
    key_terms: list[str] = Field(default_factory=list, description="3-7 important concepts, terms, or phrases")
    hypothetical_questions: list[str] = Field(
        default_factory=list,
        description="2-5 questions someone might ask that this section answers (HyDE)",
    )
    semantic_type: str = Field(
        default="other",
        description="Content type: definitions|obligations|rights|procedures|background|technical|financial|legal|boilerplate|other",
    )
    entities: list[dict] = Field(
        default_factory=list,
        description="Named entities: [{name, type}] where type is person|company|product|location|date|other",
    )
    importance_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How important is this content vs boilerplate (0.0-1.0)",
    )


ENRICHMENT_SYSTEM_PROMPT = """You are an expert at analyzing document sections for search optimization.

Your goal is to enrich each section with metadata that improves retrieval:
- summary: Focus on what information this section provides
- key_terms: Important concepts, terms, phrases for search matching
- hypothetical_questions: Questions someone might ask that this section answers
- semantic_type: Classify the nature of this content
- entities: Extract named entities (people, companies, products, etc.)
- importance_score: 0.0-1.0, how important vs boilerplate/filler

Semantic types:
- definitions: Term definitions, glossaries
- obligations: Requirements, duties, must-do items
- rights: Permissions, entitlements
- procedures: Step-by-step processes
- background: Context, history, explanations
- technical: Technical specifications, code
- financial: Numbers, budgets, pricing
- legal: Legal clauses, terms
- boilerplate: Standard text, disclaimers
- other: Doesn't fit above categories"""


def _build_enrichment_agent() -> Agent:
    """Build the pydantic-ai agent for section enrichment."""
    model_string = os.getenv("ENRICHMENT_MODEL", os.getenv("AECH_LLM_MODEL", "openai:gpt-4o-mini"))
    model_name, _ = parse_model_string(model_string)
    model_settings = get_model_settings(model_string)

    return Agent(
        model_name,
        output_type=EnrichmentOutput,
        instructions=ENRICHMENT_SYSTEM_PROMPT,
        model_settings=model_settings,
    )


# Lazy-loaded agent
_enrichment_agent: Agent | None = None


def _get_agent() -> Agent:
    """Get or create the enrichment agent."""
    global _enrichment_agent
    if _enrichment_agent is None:
        _enrichment_agent = _build_enrichment_agent()
    return _enrichment_agent


async def enrich_section_async(node: TreeNode) -> SectionEnrichment:
    """
    Enrich a single section with LLM-generated metadata (async).

    Args:
        node: TreeNode to enrich

    Returns:
        SectionEnrichment with generated metadata
    """
    # Truncate content if too long
    content = node.content
    if len(content) > 15000:
        content = content[:15000] + "\n\n[Content truncated...]"

    prompt = f"""Analyze this document section:

Section Path: {node.path}
Section Title: {node.title}

Content:
{content}"""

    agent = _get_agent()
    result = await agent.run(prompt)
    output = result.output

    return SectionEnrichment(
        summary=output.summary,
        key_terms=output.key_terms,
        hypothetical_questions=output.hypothetical_questions,
        semantic_type=output.semantic_type,
        entities=output.entities,
        importance_score=output.importance_score,
    )


def enrich_section(node: TreeNode, **kwargs) -> SectionEnrichment:
    """
    Enrich a single section with LLM-generated metadata (sync wrapper).

    Args:
        node: TreeNode to enrich
        **kwargs: Ignored (for backward compatibility)

    Returns:
        SectionEnrichment with generated metadata
    """
    import asyncio

    return asyncio.get_event_loop().run_until_complete(enrich_section_async(node))


async def enrich_document_async(
    nodes: list[TreeNode],
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    skip_small_sections: bool = True,
    min_content_length: int = 50,
) -> dict[str, SectionEnrichment]:
    """
    Enrich all sections in a document (async).

    Args:
        nodes: List of TreeNodes to enrich
        progress_callback: Optional callback(current, total, message)
        skip_small_sections: Skip sections with little content
        min_content_length: Minimum content length to enrich

    Returns:
        Dict mapping node IDs to SectionEnrichment
    """
    # Filter nodes with content worth enriching
    enrichable_nodes = []
    for node in nodes:
        if node.level == 0:  # Skip root
            continue
        if not node.content or len(node.content.strip()) < min_content_length:
            if skip_small_sections:
                continue
        enrichable_nodes.append(node)

    if not enrichable_nodes:
        return {}

    if progress_callback:
        progress_callback(0, len(enrichable_nodes), "Enriching sections...")

    enrichments = {}
    for i, node in enumerate(enrichable_nodes):
        if progress_callback:
            progress_callback(i, len(enrichable_nodes), f"Enriching: {node.title[:30]}...")

        try:
            enrichment = await enrich_section_async(node)
            enrichments[node.id] = enrichment
        except Exception as e:
            print(f"Warning: Failed to enrich section '{node.title}': {e}")
            enrichments[node.id] = SectionEnrichment(
                summary="",
                key_terms=[],
                hypothetical_questions=[],
                semantic_type="other",
                entities=[],
                importance_score=0.5,
            )

    if progress_callback:
        progress_callback(len(enrichable_nodes), len(enrichable_nodes), "Enrichment complete")

    return enrichments


def enrich_document(
    nodes: list[TreeNode],
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    skip_small_sections: bool = True,
    min_content_length: int = 50,
    **kwargs,
) -> dict[str, SectionEnrichment]:
    """
    Enrich all sections in a document (sync wrapper).

    Args:
        nodes: List of TreeNodes to enrich
        progress_callback: Optional callback(current, total, message)
        skip_small_sections: Skip sections with little content
        min_content_length: Minimum content length to enrich
        **kwargs: Ignored (for backward compatibility)

    Returns:
        Dict mapping node IDs to SectionEnrichment
    """
    import asyncio

    return asyncio.get_event_loop().run_until_complete(
        enrich_document_async(nodes, progress_callback, skip_small_sections, min_content_length)
    )


def apply_enrichment_to_section(section: Section, enrichment: SectionEnrichment) -> Section:
    """Apply enrichment data to a Section model."""
    section.summary = enrichment.summary
    section.key_terms = enrichment.key_terms
    section.hypothetical_questions = enrichment.hypothetical_questions
    section.semantic_type = enrichment.semantic_type
    section.entities = enrichment.entities
    section.importance_score = enrichment.importance_score
    return section
