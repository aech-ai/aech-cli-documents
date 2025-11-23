# Agent Aech Documents CLI

Document normalization utilities used by Agent Aech. The CLI ingests PDFs,
Office formats, and raster images, then emits either per-page PNG renders or
Markdown that other capabilities can index.

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

## Manifest-Based `--help`

Aech installers call `--help` on every CLI. This entry point intercepts a bare
`aech-cli-documents --help` and prints the JSON manifest (same schema as
`manifest.json`). Sub-command help (`convert --help`, etc.) still renders Typer's
rich output.
