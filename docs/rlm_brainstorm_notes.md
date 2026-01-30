# RLM + Documents CLI Brainstorm (Saved Conversation)

Date: 2026-01-28

## Core UX Goal
- **Caller (Agent Aech)** uses a single CLI command (`ask`).
- The CLI guides the question to be complete, runs **one RLM session**, and returns **one final answer** with **citations**.
- No intermediate output or streaming; agent only needs the final answer and provenance.

## Key Insight (Why RLM)
- Embeddings **break down** at scale when documents are large and semantically similar (e.g., large contracts).
- For large docs, semantic similarity across thousands of chunks is not meaningful.
- RLM can handle **arbitrarily large content** by **iterating in code** inside a REPL, not by packing everything into one prompt.
- The “document” for RLM can be **the entire result set** from DB search; RLM iterates over it and synthesizes a final answer.

## Retrieval Philosophy (No Embeddings)
- Embeddings feel limiting for LLM‑agent workflows when corpora are large and similar.
- **Prefer deterministic retrieval**:
  - Metadata filters (name, tags, dates, source)
  - FTS over **section summaries + key elements + anchor phrases**
  - Full markdown on disk for fidelity
- RLM performs **deep analysis** after identification, not similarity search.

## Canonical Unit: Sections (Not Pages)
- **Sections** are the primary unit of structure and retrieval.
- Section summaries are used for search; full section text is used for RLM analysis.
- Pages were discussed and rejected in favor of sections.

## Ingestion (Invest Tokens Upfront)
- VLM conversion should produce **highly navigable markdown**:
  - Meaningful headers (include topic, not just numbers)
  - Consistent heading hierarchy
  - Preserve natural document structure
  - Normalize tables
- This investment improves RLM’s code‑based navigation.

## RLM Execution Model
- One RLM run can handle **many documents** of any size.
- RLM iterates over results programmatically and returns a single synthesized answer.
- The caller should not care how the answer is derived, only that it’s correct and cited.

## Minimal “No‑Entities” Retrieval Stack (Accepted)
- **documents** table: id, name, tags, doc_type, source_path, markdown_path, created_at
- **sections** table: id, doc_id, title_path, level, start_offset, end_offset
- **section_summaries** table: section_id, summary, key_elements, anchor_phrases
- **FTS5** index over summary + key_elements + anchor_phrases
- Full markdown stays on disk; RLM loads by offsets/sections.
- **No embeddings, no entities table.**

## `ask` Flow (Single Call)
1. Question completion (clarify the user’s request).
2. DB search using metadata filters + FTS on section summaries.
3. RLM iterates over matched sections, extracts, synthesizes.
4. Final markdown answer with citations to doc/section offsets.

## Notes / Constraints
- The consumer is Agent Aech (CLI spec v6/v7).
- Output must be markdown and include citations.
- No human UX or streaming needed.

