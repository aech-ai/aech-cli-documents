# RLM Integration Brainstorm

/Users/steven/.claude/plans/peaceful-bubbling-kahn.md

**Date**: 2026-01-28
**Context**: Exploring how to integrate Recursive Language Models (RLM) into aech-cli-documents

## Source Material

- Paper: https://arxiv.org/html/2512.24601v1
- Reference implementation: `/Users/steven/work/github/0dev/pydantic-ai-rlm`

## Core Insight from the Paper

**The problem**: LLMs can't handle inputs beyond their context windows. Even within limits, "context rot" degrades performance.

**The RLM solution**: Treat the prompt as environmental data, not direct input. The LLM writes Python code to programmatically explore the data, using sub-LLM calls for targeted semantic analysis.

```python
# LLM writes code like this:
sections = re.split(r'\n##\s+', context)
for s in sections:
    if 'payment' in s.lower():
        analysis = llm_query(f"Extract payment terms:\n{s}")
```

**Key quote from paper**: "The key insight is that long prompts should not be fed into the neural network directly but should instead be treated as part of the environment."

## Why Embeddings Break Down at Scale

A legal firm's contract library:
- 1,000 page contract = ~3,000 chunks
- Thousands of contracts = millions of chunks
- All contracts are semantically similar (same language, same structure)
- Search "indemnification" → thousands of results with similar embeddings

**Embeddings = approximate similarity** → breaks down when documents look alike

**Code = exact filtering** → party names, dates, section titles, structural navigation

## The User Experience Flow

User sends email: "What are the payment terms in the Acme contract?"

Agent Aech:
1. **Identifies** which document (by name/metadata, not embedding similarity)
2. **Retrieves** full document from corpus
3. **Analyzes** with RLM (code-based navigation + sub-LLM)
4. **Responds** with delightful answer

**The corpus is the storage backend for RLM** - not just an embedding index.

## Investment at Conversion Time

**Philosophy**: Invest tokens during ingestion to make retrieval/navigation free.

VLM conversion should optimize structure for code-based navigation:
- Meaningful headers (not just "Section 3.2" but "Section 3.2: Scope of Services")
- Consistent heading hierarchy (H1 → H2 → H3, never skip)
- Preserve document's natural structure - don't impose external categories
- Normalize tables

**Tradeoff**: Structure decisions get "baked in" at ingestion. If wrong, requires reprocessing. Acceptable because reprocessing cost is amortized over many queries.

## Open Question: Page-Level Chunking

Instead of 3000 small chunks for a 1000-page document, what if we chunk by PAGE?

**Advantages:**
- 1000 pages = 1000 chunks (not 3000)
- Each page is a natural semantic unit
- VLM already processes page-by-page - we have natural boundaries
- A "Payment Terms" page has a DIFFERENT embedding than a "Definitions" page
- Semantic search actually works at page level

**The problem with small chunks:**
- "payment" appears in fragments across many chunks
- All chunks from same contract have similar embeddings (same language, same style)
- No meaningful distinction

**With page chunks:**
- Each page has distinct topic/content
- Semantic search finds "the page about X"
- Then RLM drills into that page for detailed analysis

**Overlap approach:**
- Include last paragraph of previous page + first paragraph of next page
- Handles content that spans page breaks

This is a middle ground between "embed everything small" and "skip embedding entirely."

## Two Modes of Operation

### Mode 1: Single Document Analysis

Load entire document as `context`. LLM writes code to navigate structure.

```bash
aech-documents analyze "Find all payment terms" --input ./contract.pdf
```

### Mode 2: Corpus Analysis

Retrieve document(s) from corpus, then analyze with RLM.

```bash
aech-documents analyze "Extract payment terms" --corpus ./corpus.db --doc "Acme Master Agreement"
```

## Relationship to Existing Features

**Keep existing**: chunking, embedding, FTS, hybrid search (for discovery)
**Add new**: `analyze` command for RLM-based deep analysis

They serve complementary purposes:
- Embeddings for semantic similarity ("find documents about X")
- Code for exact filtering and structural traversal ("extract Y from document Z")

## Implementation Phases

### Phase 1: Document Analysis Command
- Sandboxed REPL (vendor from pydantic-ai-rlm)
- Pydantic-ai RLM agent
- `analyze` command for single documents

### Phase 2: Corpus Integration
- Retrieve full markdown by doc ID/name
- `--skip-embedding` flag for large documents
- Page-level chunking option

### Phase 3: Enhanced VLM Prompts
- Optimize structure for code navigation

## Files to Create

```
aech_cli_documents/rlm/
├── __init__.py
├── repl.py          # Sandboxed Python REPL
├── agent.py         # Pydantic-ai RLM agent
└── prompts.py       # System instructions
```

## Next Steps

1. Decide on chunking strategy (page-level vs skip for large docs)
2. Implement Phase 1 (document analysis without corpus)
3. Test with real large documents
4. Iterate on VLM prompts for better structure

---

## Plan File

Full plan saved at: `/Users/steven/.claude/plans/peaceful-bubbling-kahn.md`
