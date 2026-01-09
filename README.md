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
  `--reference-doc` argument allows custom styling templates.
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

## Manifest Documentation

The manifest exposes a `documentation` object with output paths and usage notes:

- **outputs**:
  - `page_images`: `output_dir/page_###.png` — numbered PNG pages from convert command.
  - `markdown_file`: `output_dir/<stem>.md` — Markdown file from convert-to-markdown command.
  - `converted_files`: `output_dir/<stem>.<format>` — output files from convert-markdown command.
- **notes**:
  - All commands return JSON to stdout with output file paths.
  - Use `--output-dir` to specify where files are written.
  - Check command exit code and JSON output for success/failure.
