"""LLM-powered section enrichment - summaries, HyDE questions, classification.

Model configuration via environment variables:
- ANTHROPIC_API_KEY: API key for Anthropic
- ENRICHMENT_MODEL: Model to use for enrichment tasks (required)
"""

import json
import os
from typing import Optional, Callable

import anthropic

from .models import Section, SectionEnrichment
from .structure import TreeNode


def get_enrichment_model() -> str:
    """Get enrichment model from environment. Raises if not set."""
    model = os.environ.get("ENRICHMENT_MODEL")
    if not model:
        raise ValueError(
            "ENRICHMENT_MODEL environment variable not set. "
            "Set it in your .env file (e.g., ENRICHMENT_MODEL=claude-sonnet-4-20250514)"
        )
    return model


SECTION_ENRICHMENT_PROMPT = """Analyze this document section and provide structured enrichment.

Section Path: {section_path}
Section Title: {section_title}

Content:
{section_content}

Respond with ONLY a JSON object (no markdown code blocks, no explanation):
{{
  "summary": "1-2 sentence summary of what this section covers",
  "key_terms": ["term1", "term2", "term3"],
  "hypothetical_questions": [
    "Question 1 that this section answers?",
    "Question 2 that this section answers?",
    "Question 3 that this section answers?"
  ],
  "semantic_type": "one of: definitions|obligations|rights|procedures|background|technical|financial|legal|boilerplate|other",
  "entities": [
    {{"name": "Entity Name", "type": "person|company|product|location|date|other"}}
  ],
  "importance_score": 0.8
}}

Guidelines:
- summary: Focus on what information this section provides
- key_terms: 3-7 important concepts, terms, or phrases
- hypothetical_questions: 2-5 questions someone might ask that this section answers
- semantic_type: Classify the nature of this content
- entities: Extract named entities mentioned (people, companies, products, etc.)
- importance_score: 0.0-1.0, how important is this content vs boilerplate/filler"""


BATCH_ENRICHMENT_PROMPT = """Analyze these document sections and provide structured enrichment for each.

{sections_text}

For EACH section, respond with a JSON object on its own line. The format for each section should be:
{{"section_id": "...", "summary": "...", "key_terms": [...], "hypothetical_questions": [...], "semantic_type": "...", "entities": [...], "importance_score": 0.8}}

Output one JSON object per line, no other text."""


def parse_enrichment_json(text: str) -> dict:
    """Parse enrichment JSON from LLM response."""
    # Try to extract JSON from the response
    text = text.strip()

    # Remove markdown code block if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    # Return default if parsing fails
    return {
        "summary": "",
        "key_terms": [],
        "hypothetical_questions": [],
        "semantic_type": "other",
        "entities": [],
        "importance_score": 0.5,
    }


def enrich_section(
    node: TreeNode,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> SectionEnrichment:
    """
    Enrich a single section with LLM-generated metadata.

    Args:
        node: TreeNode to enrich
        model: Model to use (uses ENRICHMENT_MODEL env var if not provided)
        api_key: API key (uses ANTHROPIC_API_KEY env var if not provided)

    Returns:
        SectionEnrichment with generated metadata
    """
    model = model or get_enrichment_model()
    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    # Truncate content if too long
    content = node.content
    if len(content) > 15000:
        content = content[:15000] + "\n\n[Content truncated...]"

    prompt = SECTION_ENRICHMENT_PROMPT.format(
        section_path=node.path,
        section_title=node.title,
        section_content=content,
    )

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    result = parse_enrichment_json(response.content[0].text)

    return SectionEnrichment(
        summary=result.get("summary", ""),
        key_terms=result.get("key_terms", []),
        hypothetical_questions=result.get("hypothetical_questions", []),
        semantic_type=result.get("semantic_type", "other"),
        entities=result.get("entities", []),
        importance_score=result.get("importance_score", 0.5),
    )


def enrich_document(
    nodes: list[TreeNode],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    skip_small_sections: bool = True,
    min_content_length: int = 50,
) -> dict[str, SectionEnrichment]:
    """
    Enrich all sections in a document.

    Args:
        nodes: List of TreeNodes to enrich
        model: Model to use (uses ENRICHMENT_MODEL env var if not provided)
        api_key: API key (uses ANTHROPIC_API_KEY env var if not provided)
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
            enrichment = enrich_section(node, model=model, api_key=api_key)
            enrichments[node.id] = enrichment
        except Exception as e:
            # Log error but continue
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


def apply_enrichment_to_section(section: Section, enrichment: SectionEnrichment) -> Section:
    """Apply enrichment data to a Section model."""
    section.summary = enrichment.summary
    section.key_terms = enrichment.key_terms
    section.hypothetical_questions = enrichment.hypothetical_questions
    section.semantic_type = enrichment.semantic_type
    section.entities = enrichment.entities
    section.importance_score = enrichment.importance_score
    return section
