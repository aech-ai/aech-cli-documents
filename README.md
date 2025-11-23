# Agent Aech Documents CLI

Document normalization utilities used by Agent Aech. The CLI ingests PDFs,
Office formats, and raster images, then emits either per-page PNG renders or
Markdown that other capabilities can index. It can also round-trip Markdown into
polished DOCX/PDF deliverables via Pandoc for consistent presentation.

## Commands

### `convert`
- **Input**: path to a PDF, Office document (DOCX/PPTX/XLSX/etc.), or existing
  image file, plus `--output-dir` pointing to a writable folder inside the
  sandbox.
- **Behavior**: Office docs are converted to PDF via LibreOffice, PDFs are
  rasterized with `pdf2image`, and single images are normalized to PNG.
- **Output**: numbered files such as `page_001.png` saved in `output_dir`, and a
  JSON payload listing the generated file paths.
- **Example**:
  ```bash
  aech-cli-documents convert briefs/proposal.docx --output-dir build/proposal_images
  ```

### `convert-to-markdown`
- **Input**: supported document path plus `--output-dir`.
- **Behavior**: Legacy Office formats are first upgraded to DOCX so MarkItDown
  can parse them, then the command saves `<stem>.md` next to the other outputs.
- **Output**: `<original_stem>.md` and a JSON object containing its path.
- **Example**:
  ```bash
  aech-cli-documents convert-to-markdown scans/notes.pdf --output-dir build/notes_md
  ```

### `convert-markdown`
- **Input**: path to a Markdown file plus `--output-dir`. Pandoc must be
  installed and accessible on `PATH`.
- **Behavior**: Pandoc renders standardized outputs (DOCX/PDF by default) so
  downstream users see a consistent template. Repeat `--format` to request
  multiple targets (e.g. `--format docx --format pptx`). Optional
  `--reference-doc` and `--pdf-engine` arguments expose Pandoc's styling hooks.
- **Output**: one file per requested format plus a JSON payload summarizing the
  generated paths.
- **Example**:
  ```bash
  aech-cli-documents convert-markdown drafts/spec.md --output-dir build/specs --format docx --format pdf
  ```

> **Note:** Pandoc is an external dependency. Install it from
> https://pandoc.org/installing.html (or ship it with your runtime) before
> running `convert-markdown`.

## Manifest-Based `--help`

Aech installers call `--help` on every CLI. This entry point intercepts a bare
`aech-cli-documents --help` and prints the JSON manifest (same schema as
`manifest.json`). Sub-command help (`convert --help`, etc.) still renders Typer's
rich output.

## Manifest Documentation Block

The manifest also exposes a `documentation` object for richer, automation-ready
metadata:

- **readme**: Agent Aech document normalization CLI. Use `convert` to rasterize documents into per-page PNGs for OCR/classification, `convert-to-markdown` to extract clean Markdown for indexing, and `convert-markdown` to publish Markdown as DOCX/PDF (or other Pandoc formats). Provide local paths, set `--output-dir` inside the sandbox, and capture stdout JSON to know where files landed. Ensure LibreOffice, MarkItDown, and Pandoc are available when invoking their respective flows. QA: verify page counts vs. source, confirm Markdown preserves headings/lists, and skim rendered Office/PDF outputs for template fidelity before sharing.
- **usage**: `aech-cli-documents <convert|convert-to-markdown|convert-markdown> <input_path> --output-dir <dir> [--format <fmt>] [--reference-doc <path>] [--pdf-engine <engine>]`
- **inputs**:
  - `input_path`: Source file path: PDF/Office/image for convert/convert-to-markdown; Markdown for convert-markdown.
  - `output_dir`: Writable directory for all generated assets; must exist or be creatable inside the sandbox.
  - `format`: Optional, repeatable Pandoc output format for convert-markdown (docx/pdf/pptx/etc.).
  - `reference_doc`: Optional Pandoc reference template used for Office-style outputs.
  - `pdf_engine`: Optional Pandoc PDF engine, e.g., xelatex.
- **outputs**:
  - `page_images`: `output_dir/page_###.png` — numbered PNG pages emitted by convert; paths returned via stdout JSON list.
  - `markdown_file`: `output_dir/<stem>.md` — Markdown exported from convert-to-markdown; path returned via stdout JSON object.
  - `converted_files`: `output_dir/<stem>.<format>` — per-format deliverables from convert-markdown (docx/pdf/pptx/etc.) mirrored in stdout JSON.
- **automation_expectations**:
  - Call the appropriate command with explicit `--output-dir` and capture stdout JSON for downstream steps.
  - Bundle every file written to `output_dir` (page images, Markdown, Pandoc outputs) as artifacts or message attachments.
  - Attach a short QA note following `qa_report_format` when handing off results.
  - Flag missing dependencies (LibreOffice, MarkItDown, Pandoc) or conversion failures as blockers.
  - Keep original stems and numbering; do not rename outputs when packaging.
- **qa_report_format**:
  - Overall conversion quality and completeness (pages rendered, text preserved).
  - Notable discrepancies vs. source (missing pages, layout drift, encoding issues).
  - Dependency or tooling issues encountered (and whether retries were attempted).
  - Recommendations or next steps (e.g., rerun with different format/reference doc).
