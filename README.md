# Agent Aech Documents CLI

Universal Document Corpus CLI for Agent Aech. This tool provides VLM-powered document
intelligence with excellent retrieval through hybrid search (FTS + vector + RRF fusion).

**Key Principle**: Invest LLM tokens at index time (once per document) to crystallize
value for retrieval (free, fast, every query).

**PDF Smart Routing**: PDFs are classified with `detect-pdf`; high-confidence
text-based PDFs are extracted with `pdf2md`, and everything else is routed to
the VLM pipeline.

## Installation

```bash
pip install -e .
```

**Dependencies**:
- `pdf2image` requires poppler: `brew install poppler` (macOS) or `apt install poppler-utils` (Linux)
- `pandoc` for markdown conversion: https://pandoc.org/installing.html
- For PDF routing in workers:
  - `detect-pdf` and `pdf2md` must be installed in the worker image via the
    aech-main `uv` manager

## Configuration

Models are configured via environment variables (uses pydantic-ai):

```bash
# Model for VLM document conversion (falls back to AECH_LLM_MODEL)
VLM_MODEL=openai:gpt-4o

# Model for section enrichment (falls back to AECH_LLM_MODEL)
ENRICHMENT_MODEL=openai:gpt-4o-mini

# Default model (used if specific model not set)
AECH_LLM_MODEL=openai:gpt-4o

# OpenAI-compatible embedding endpoint for corpus ingest/search
EMBEDDING_BASE_URL=http://host.docker.internal:1234/v1
EMBEDDING_MODEL=text-embedding-bge-m3@fp16
EMBEDDING_API_KEY=lm-studio
EMBEDDING_BATCH_SIZE=8

# PDF routing mode: smart (default) or vlm_only
AECH_PDF_ROUTING_MODE=smart

# Min confidence for local text extraction when pdf_type=text_based
AECH_PDF_INSPECTOR_MIN_CONFIDENCE=0.90

# Optional binary overrides
AECH_PDF_INSPECTOR_DETECT_BIN=detect-pdf
AECH_PDF_INSPECTOR_PDF2MD_BIN=pdf2md
```

If `AECH_PDF_ROUTING_MODE=smart`, missing/invalid pdf-inspector binaries fail loudly.
Set `AECH_PDF_ROUTING_MODE=vlm_only` to force the legacy VLM path.
Corpus ingest/search also requires an OpenAI-compatible embedding server. The package no
longer runs local `sentence-transformers` models in-process.

Model format: `provider:model` (e.g., `openai:gpt-4o`, `anthropic:claude-sonnet-4`)

## Commands

### Document Conversion

#### `convert`
Convert documents to page images for VLM processing.

```bash
aech-cli-documents convert document.pdf --output-dir ./images
```

- **Input**: PDF, Office document (DOCX/PPTX/XLSX), or image file
- **Output**: Numbered PNG files (`page_001.png`, `page_002.png`, ...)

#### `convert-to-markdown`
Convert any document to markdown using smart PDF routing + VLM.

```bash
aech-cli-documents convert-to-markdown document.pdf --output-dir ./output
```

- **Input**: Any supported document format
- **Output**: Markdown file with full visual understanding
- **Flags**: `--model` to override the `VLM_MODEL` env var

**Note**: For PDFs, the CLI can route between local extraction (`pdf2md`) and the
VLM image pipeline based on `detect-pdf` classification. Non-PDF formats continue
through the existing VLM conversion flow.

#### `convert-markdown`
Convert markdown to polished deliverables (DOCX, PDF, PPTX).

```bash
aech-cli-documents convert-markdown spec.md --output-dir ./output --format docx --format pdf
```

- **Input**: Markdown file
- **Output**: Requested formats via Pandoc

---

### Corpus Management

#### `corpus create`
Create a new corpus database.

```bash
aech-cli-documents corpus create ./sales.db
aech-cli-documents corpus create ./legal.db --name "Legal Documents 2024"
```

#### `corpus info`
Show corpus statistics.

```bash
aech-cli-documents corpus info ./sales.db
```

Output:
```
Corpus: sales.db
Name: Sales Communications
Documents: 1,247
Sections: 8,432
Chunks: 12,891
Created: 2024-01-15
```

#### `corpus list`
List documents in a corpus.

```bash
aech-cli-documents corpus list ./sales.db
aech-cli-documents corpus list ./sales.db --limit 20
```

---

### Document Ingestion

#### `ingest`
Add documents to a corpus with optional LLM enrichment.

```bash
# Basic ingestion
aech-cli-documents ingest report.pdf --corpus ./company.db

# With LLM enrichment (summaries, HyDE questions, classification)
aech-cli-documents ingest contract.pdf --corpus ./legal.db --enrich

# Recursive directory ingestion
aech-cli-documents ingest ./documents/ --corpus ./kb.db --recursive --enrich

# With metadata
aech-cli-documents ingest email.eml --corpus ./sales.db \
  --source-type email \
  --tags "q4,prospect,acme"
```

**Enrichment** (`--enrich` flag) generates for each section:
- Summary (1-2 sentences)
- Key terms (5-10 concepts)
- Hypothetical questions (HyDE - questions this section answers)
- Semantic classification (definitions, obligations, procedures, etc.)
- Named entities (people, companies, products)
- Importance score (filter boilerplate)

---

### Search

#### `search`
Hybrid search across a corpus using FTS + vector + RRF fusion.

```bash
# Basic search
aech-cli-documents search "payment terms" --corpus ./legal.db

# With semantic type filter
aech-cli-documents search "payment terms" --corpus ./legal.db \
  --semantic-type obligations \
  --limit 10

# JSON output with full content
aech-cli-documents search "python experience" --corpus ./hr.db \
  --format json \
  --include-content
```

**Semantic Types**:
- `definitions` - Term definitions, glossaries
- `obligations` - Requirements, duties, must-do items
- `rights` - Permissions, entitlements
- `procedures` - Step-by-step processes
- `background` - Context, history, explanations
- `technical` - Technical specifications, code
- `financial` - Numbers, budgets, pricing
- `legal` - Legal clauses, terms
- `boilerplate` - Standard text, disclaimers

---

### Export

#### `export`
Export documents or search results.

```bash
aech-cli-documents export doc-123 --corpus ./kb.db --format markdown
```

---

## Architecture

```
Document → Smart PDF Router → Markdown → Structure Extraction → Enrichment → Hybrid Search
             │
             ├─ text_based + high confidence → pdf2md (local)
             └─ otherwise → VLM (images)
                                           ↓
                              ┌─────────────────────────┐
                              │  Hierarchical Tree      │
                              │  (sections/subsections) │
                              └─────────────────────────┘
                                           ↓
                              ┌─────────────────────────┐
                              │  Structure-Aware Chunks │
                              │  (respect boundaries)   │
                              └─────────────────────────┘
                                           ↓
                              ┌─────────────────────────┐
                              │  OpenAI-compatible      │
                              │  bge-m3 Embeddings +    │
                              │  FTS5 Full-Text Index   │
                              └─────────────────────────┘
```

### Why Smart PDF Routing?

- **Lower latency/cost**: Text-based PDFs avoid expensive VLM/OCR passes
- **Still robust on hard PDFs**: Scanned/image-heavy PDFs route to VLM
- **Keeps full visual path**: Complex documents still use the existing image-based conversion

### Why Enrich at Index Time?

- **Index cost**: O(documents) - pay ONCE per document
- **Query cost**: O(1) - FREE, just vector similarity
- **Break-even**: ~10 queries per document

### Hybrid Search (RRF)

Combines:
1. **FTS5** (BM25) - Keyword matching, exact terms
2. **Vector** (bge-m3) - Semantic similarity
3. **RRF Fusion** - Best of both worlds

## Use Cases

- **Agent Aech**: Research & knowledge building capability
- **Sales**: Email database with searchable context
- **HR**: Resume knowledge base
- **Legal**: Contract search with semantic filtering
- **Inbox Assistant**: Email and attachment corpus

## Library Usage

```python
from aech_cli_documents.corpus import (
    Corpus,
    create_corpus,
    hybrid_search,
    chunk_document,
    extract_structure,
    enrich_document,
)

# Create corpus
corpus = create_corpus("./my_corpus.db", name="My Knowledge Base")

# Or open existing
corpus = Corpus("./my_corpus.db")

# Add document
doc = corpus.add_document(
    name="contract.pdf",
    source_type="file",
    raw_markdown=markdown_content,
)

# Search
results = hybrid_search(corpus, "payment terms", limit=10)
for r in results:
    print(f"{r.document_name} - {r.section_title}: {r.content_preview}")
```
