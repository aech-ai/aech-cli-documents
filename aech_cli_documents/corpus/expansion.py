"""Query expansion using pydantic-ai with aggressive caching.

Model configured via EXPANSION_MODEL env var (falls back to AECH_LLM_MODEL).
"""

import hashlib
import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from .model_utils import parse_model_string, get_model_settings


class QueryExpansion(BaseModel):
    """Expanded query variants for hybrid search."""

    lex: list[str] = Field(description="2-3 short keyword phrases for BM25 exact matching")
    vec: list[str] = Field(description="2-3 natural language questions for vector search")
    hyde: str = Field(description="Hypothetical passage (2-3 sentences) that answers the query")


EXPANSION_SYSTEM_PROMPT = """You expand search queries into variants for hybrid search.

Given a query, generate:
- lex: 2-3 short keyword phrases for exact matching (e.g., "payment terms", "net 30")
- vec: 2-3 natural language questions for semantic search (e.g., "What are the payment terms?")
- hyde: A hypothetical passage (2-3 sentences) that would answer the query

Be concise. Output only what's needed for search."""


def _build_expansion_agent() -> Agent:
    """Build the pydantic-ai agent for query expansion."""
    model_string = os.getenv("EXPANSION_MODEL", os.getenv("AECH_LLM_MODEL", "openai:gpt-4o-mini"))
    model_name, _ = parse_model_string(model_string)
    model_settings = get_model_settings(model_string)

    return Agent(
        model_name,
        output_type=QueryExpansion,
        instructions=EXPANSION_SYSTEM_PROMPT,
        model_settings=model_settings,
    )


# Lazy-loaded agent
_expansion_agent: Agent | None = None


def _get_agent() -> Agent:
    """Get or create the expansion agent."""
    global _expansion_agent
    if _expansion_agent is None:
        _expansion_agent = _build_expansion_agent()
    return _expansion_agent


def get_expansion_cache_key(query: str) -> str:
    """Generate cache key for query expansion."""
    return hashlib.md5(query.strip().lower().encode()).hexdigest()


async def expand_query_async(query: str, get_cache_fn=None, set_cache_fn=None) -> QueryExpansion:
    """
    Expand query into lex/vec/hyde variants.

    Args:
        query: Search query to expand
        get_cache_fn: Optional function(cache_type, cache_key) -> cached_value
        set_cache_fn: Optional function(cache_type, cache_key, value)

    Returns:
        QueryExpansion with lex, vec, hyde variants
    """
    cache_key = get_expansion_cache_key(query)

    # Check cache first
    if get_cache_fn:
        cached = get_cache_fn("expansion", cache_key)
        if cached:
            return QueryExpansion.model_validate_json(cached)

    # Call LLM
    agent = _get_agent()
    result = await agent.run(query)

    # Cache result
    if set_cache_fn:
        set_cache_fn("expansion", cache_key, result.output.model_dump_json())

    return result.output


def expand_query(query: str, get_cache_fn=None, set_cache_fn=None) -> QueryExpansion:
    """
    Expand query into lex/vec/hyde variants (sync wrapper).

    Args:
        query: Search query to expand
        get_cache_fn: Optional function(cache_type, cache_key) -> cached_value
        set_cache_fn: Optional function(cache_type, cache_key, value)

    Returns:
        QueryExpansion with lex, vec, hyde variants
    """
    import asyncio

    return asyncio.get_event_loop().run_until_complete(
        expand_query_async(query, get_cache_fn, set_cache_fn)
    )
