"""
Agent Aech Documents CLI - Universal Document Corpus

Commands:
- convert: Document → images (PDF/Office/Image → PNG pages)
- convert-to-markdown: Document → Markdown (VLM-based, no text extraction)
- convert-markdown: Markdown → Office/PDF (Pandoc)
- corpus: Corpus management (create, info, list)
- ingest: Add documents to corpus with optional enrichment
- search: Hybrid search across corpus
- export: Export documents or search results
"""

import json
import subprocess
import sys
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import typer
from pdf2image import convert_from_path
from PIL import Image
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer()
corpus_app = typer.Typer()
app.add_typer(corpus_app, name="corpus", help="Corpus management commands")

console = Console()


@lru_cache(maxsize=1)
def _load_manifest() -> dict:
    """Load the JSON manifest from disk, favoring the packaged copy."""
    package_manifest = Path(__file__).resolve().parent / "manifest.json"
    repo_manifest = package_manifest.parent.parent / "manifest.json"

    for candidate in (package_manifest, repo_manifest):
        if candidate.exists():
            with candidate.open(encoding="utf-8") as handle:
                return json.load(handle)

    raise FileNotFoundError("manifest.json not found alongside package or in project root")


def _should_emit_manifest(argv: list[str]) -> bool:
    """Return True when CLI should output the manifest instead of help text."""
    return len(argv) == 2 and argv[1] in ("-h", "--help")


def _print_manifest() -> None:
    print(json.dumps(_load_manifest(), indent=2))


def convert_office_to_pdf(input_path: Path, output_dir: Path) -> Optional[Path]:
    """Converts Office document to PDF using LibreOffice."""
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(input_path)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        pdf_path = output_dir / (input_path.stem + ".pdf")
        if pdf_path.exists():
            return pdf_path
    except subprocess.CalledProcessError as e:
        print(f"Error converting office doc: {e}")
    return None


@app.command()
def convert(
    input_path: str,
    output_dir: str = typer.Option(..., "--output-dir", "-o", help="Directory to save output images")
):
    """
    Converts a document (PDF, Office, Image) to a series of images.
    """
    input_file = Path(input_path)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not input_file.exists():
        typer.echo(f"Error: File {input_path} not found.")
        raise typer.Exit(code=1)

    images_created = []
    suffix = input_file.suffix.lower()
    temp_pdf = None

    try:
        # Handle Office Docs
        if suffix in ['.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', '.odt', '.odp', '.ods']:
            print(f"Converting Office document: {input_file}")
            temp_pdf = convert_office_to_pdf(input_file, out_path)
            if not temp_pdf:
                typer.echo("Failed to convert Office document to PDF.")
                raise typer.Exit(code=1)
            input_file = temp_pdf
            suffix = '.pdf'

        # Handle PDF
        if suffix == '.pdf':
            print(f"Converting PDF: {input_file}")
            try:
                images = convert_from_path(str(input_file))
                for i, image in enumerate(images):
                    image_filename = f"page_{i+1:03d}.png"
                    image_path = out_path / image_filename
                    image.save(image_path, "PNG")
                    images_created.append(str(image_path))
            except Exception as e:
                typer.echo(f"Error converting PDF: {e}")
                raise typer.Exit(code=1)

        # Handle Images
        elif suffix in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif']:
            print(f"Processing image: {input_file}")
            try:
                img = Image.open(input_file)
                image_filename = f"page_001.png"
                image_path = out_path / image_filename
                img.save(image_path, "PNG")
                images_created.append(str(image_path))
            except Exception as e:
                typer.echo(f"Error processing image: {e}")
                raise typer.Exit(code=1)
        else:
            typer.echo(f"Unsupported file type: {suffix}")
            raise typer.Exit(code=1)

    finally:
        pass  # Keep temp PDF for debugging if needed

    print(json.dumps({"images": images_created}))


@app.command("convert-to-markdown")
def convert_to_markdown(
    input_path: str,
    output_dir: str = typer.Option(..., "--output-dir", "-o", help="Directory to save output markdown"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override (uses VLM_MODEL env var by default)"),
):
    """
    Converts a document to Markdown using VLM.

    Full visual understanding - no text extraction hacks.
    Requires VLM_MODEL and ANTHROPIC_API_KEY environment variables.
    """
    from .corpus.vlm import convert_to_markdown_vlm

    input_file = Path(input_path)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not input_file.exists():
        typer.echo(f"Error: File {input_path} not found.")
        raise typer.Exit(code=1)

    def progress_callback(current: int, total: int, message: str):
        console.print(f"[dim]{message}[/dim]")

    try:
        kwargs = {"progress_callback": progress_callback}
        if model:
            kwargs["model"] = model
        markdown = convert_to_markdown_vlm(input_file, **kwargs)

        output_filename = input_file.stem + ".md"
        output_file = out_path / output_filename
        output_file.write_text(markdown)

        print(json.dumps({"markdown_file": str(output_file)}))

    except Exception as e:
        typer.echo(f"Error converting to markdown: {e}")
        raise typer.Exit(code=1)


def _run_pandoc(
    input_file: Path,
    output_file: Path,
    target_format: str,
    reference_doc: Optional[Path] = None,
) -> None:
    """Invoke Pandoc with common flags to enforce consistent styling."""
    cmd = [
        "pandoc",
        str(input_file),
        "--from=markdown",
        "--to",
        target_format,
        "--output",
        str(output_file),
        "--standalone",
        "--quiet",
    ]
    if reference_doc and target_format in {"docx", "pptx", "odt"}:
        cmd.extend(["--reference-doc", str(reference_doc)])
    subprocess.run(cmd, check=True, capture_output=True)


@app.command("convert-markdown")
def convert_markdown(
    input_path: str,
    output_dir: str = typer.Option(..., "--output-dir", "-o", help="Directory for generated files"),
    formats: Optional[List[str]] = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format(s). Repeat flag to request multiple (default: docx,pdf).",
    ),
    reference_doc: Optional[str] = typer.Option(
        None,
        "--reference-doc",
        help="Optional reference document for Office outputs.",
    ),
):
    """
    Convert Markdown into Office/PDF outputs.
    """
    input_file = Path(input_path)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not input_file.exists():
        typer.echo(f"Error: File {input_path} not found.")
        raise typer.Exit(code=1)

    if not input_file.suffix.lower() in {".md", ".markdown"}:
        typer.echo("Only Markdown sources (.md/.markdown) are supported.")
        raise typer.Exit(code=1)

    resolved_formats = [fmt.lower().lstrip(".") for fmt in (formats or ["docx", "pdf"])]
    reference_path = Path(reference_doc) if reference_doc else None
    if reference_path and not reference_path.exists():
        typer.echo(f"Reference document {reference_doc} was not found.")
        raise typer.Exit(code=1)

    generated_files = []
    try:
        for fmt in resolved_formats:
            output_file = out_path / f"{input_file.stem}.{fmt}"
            print(f"Rendering {input_file.name} -> {output_file}")
            _run_pandoc(
                input_file,
                output_file,
                fmt,
                reference_doc=reference_path,
            )
            generated_files.append({"format": fmt, "path": str(output_file)})
    except subprocess.CalledProcessError as exc:
        typer.echo(f"Pandoc failed: {exc.stderr.decode().strip()}")
        raise typer.Exit(code=1)

    print(json.dumps({"files": generated_files}))


# =============================================================================
# CORPUS COMMANDS
# =============================================================================

@corpus_app.command("create")
def corpus_create(
    db_path: str,
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Corpus name"),
):
    """Create a new corpus database."""
    from .corpus.database import create_corpus

    db_file = Path(db_path)
    if db_file.exists():
        typer.echo(f"Error: {db_path} already exists")
        raise typer.Exit(code=1)

    corpus = create_corpus(db_file, name=name)
    info = corpus.get_info()

    console.print(f"[green]Created corpus:[/green] {info.name}")
    console.print(f"  Path: {info.path}")
    corpus.close()


@corpus_app.command("info")
def corpus_info(db_path: str):
    """Show corpus statistics."""
    from .corpus.database import Corpus

    db_file = Path(db_path)
    if not db_file.exists():
        typer.echo(f"Error: {db_path} not found")
        raise typer.Exit(code=1)

    corpus = Corpus(db_file)
    info = corpus.get_info()

    table = Table(title=f"Corpus: {info.name}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Path", info.path)
    table.add_row("Documents", str(info.document_count))
    table.add_row("Sections", str(info.section_count))
    table.add_row("Chunks", str(info.chunk_count))
    table.add_row("Size", f"{info.size_bytes / 1024 / 1024:.2f} MB")
    table.add_row("Embedding Model", info.embedding_model)
    table.add_row("Created", info.created_at.strftime("%Y-%m-%d %H:%M"))
    table.add_row("Updated", info.updated_at.strftime("%Y-%m-%d %H:%M"))

    console.print(table)
    corpus.close()


@corpus_app.command("list")
def corpus_list(
    db_path: str,
    source_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by source type"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max documents to show"),
):
    """List documents in a corpus."""
    from .corpus.database import Corpus

    db_file = Path(db_path)
    if not db_file.exists():
        typer.echo(f"Error: {db_path} not found")
        raise typer.Exit(code=1)

    corpus = Corpus(db_file)
    docs = corpus.list_documents(source_type=source_type, limit=limit)

    table = Table(title="Documents")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Sections", justify="right")
    table.add_column("Chunks", justify="right")
    table.add_column("Enriched", style="yellow")

    for doc in docs:
        table.add_row(
            doc.id[:12],
            doc.name[:40],
            doc.source_type,
            str(doc.section_count),
            str(doc.chunk_count),
            "Yes" if doc.enriched_at else "No",
        )

    console.print(table)
    corpus.close()


# =============================================================================
# INGEST COMMAND
# =============================================================================

@app.command()
def ingest(
    input_path: str,
    corpus_path: str = typer.Option(..., "--corpus", "-c", help="Path to corpus database"),
    enrich: bool = typer.Option(False, "--enrich", "-e", help="Enable LLM enrichment"),
    source_type: str = typer.Option("file", "--type", "-t", help="Source type"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Process directory recursively"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override (uses VLM_MODEL/ENRICHMENT_MODEL env vars by default)"),
):
    """
    Ingest document(s) into a corpus with optional LLM enrichment.

    Requires environment variables:
    - VLM_MODEL: For document conversion
    - ENRICHMENT_MODEL: For section enrichment (if --enrich)
    - ANTHROPIC_API_KEY: API key
    """
    from .corpus.database import Corpus
    from .corpus.vlm import convert_to_markdown_vlm
    from .corpus.structure import extract_structure
    from .corpus.chunker import chunk_document
    from .corpus.embeddings import encode_batch
    from .corpus.enrichment import enrich_document, apply_enrichment_to_section
    from .corpus.models import Document, Section

    corpus_file = Path(corpus_path)
    if not corpus_file.exists():
        typer.echo(f"Error: Corpus {corpus_path} not found. Create it first with 'corpus create'")
        raise typer.Exit(code=1)

    corpus = Corpus(corpus_file)

    input_path_obj = Path(input_path)
    if not input_path_obj.exists():
        typer.echo(f"Error: {input_path} not found")
        raise typer.Exit(code=1)

    # Collect files to process
    files_to_process = []
    if input_path_obj.is_dir():
        pattern = "**/*" if recursive else "*"
        for f in input_path_obj.glob(pattern):
            if f.is_file() and f.suffix.lower() in [
                '.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls',
                '.odt', '.odp', '.ods', '.png', '.jpg', '.jpeg', '.md', '.txt'
            ]:
                files_to_process.append(f)
    else:
        files_to_process.append(input_path_obj)

    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        for file_path in files_to_process:
            task = progress.add_task(f"Processing {file_path.name}...", total=None)

            try:
                # Generate document ID
                doc_id = str(uuid.uuid4())

                # Step 1: Convert to markdown (VLM)
                progress.update(task, description=f"[cyan]Converting {file_path.name} to markdown...[/cyan]")

                if file_path.suffix.lower() in ['.md', '.markdown', '.txt']:
                    markdown = file_path.read_text()
                else:
                    vlm_kwargs = {}
                    if model:
                        vlm_kwargs["model"] = model
                    markdown = convert_to_markdown_vlm(file_path, **vlm_kwargs)

                # Step 2: Extract structure
                progress.update(task, description=f"[cyan]Extracting structure...[/cyan]")
                tree = extract_structure(markdown, document_id=doc_id)

                # Step 3: Create document and sections
                doc = Document(
                    id=doc_id,
                    name=file_path.name,
                    source_type=source_type,
                    source_path=str(file_path.absolute()),
                    content_type=f"application/{file_path.suffix.lstrip('.')}",
                    raw_markdown=markdown,
                    title=file_path.stem,
                    tags=tag_list,
                    section_count=len(tree.all_nodes) - 1,  # Exclude root
                )

                # Create Section objects
                sections_dict = {}
                for node in tree.all_nodes:
                    if node.level == 0:  # Skip root
                        continue
                    section = Section(
                        id=node.id,
                        document_id=doc_id,
                        parent_id=node.parent.id if node.parent and node.parent.level > 0 else None,
                        level=node.level,
                        path=node.path,
                        position=node.parent.children.index(node) if node.parent else 0,
                        title=node.title,
                        content=node.content,
                        start_line=node.start_line,
                        end_line=node.end_line,
                    )
                    sections_dict[node.id] = section

                # Step 4: Enrichment (if enabled)
                if enrich and tree.all_nodes:
                    progress.update(task, description=f"[yellow]Enriching sections...[/yellow]")
                    enrich_kwargs = {}
                    if model:
                        enrich_kwargs["model"] = model
                    enrichments = enrich_document(
                        [n for n in tree.all_nodes if n.level > 0],
                        **enrich_kwargs,
                    )

                    for node_id, enrichment in enrichments.items():
                        if node_id in sections_dict:
                            apply_enrichment_to_section(sections_dict[node_id], enrichment)

                    doc.enriched_at = datetime.utcnow()

                # Step 5: Chunk
                progress.update(task, description=f"[cyan]Chunking...[/cyan]")
                chunks = chunk_document(tree, doc_id, sections_dict)
                doc.chunk_count = len(chunks)

                # Step 6: Generate embeddings
                progress.update(task, description=f"[cyan]Generating embeddings...[/cyan]")
                texts_to_embed = [c.enriched_content or c.content for c in chunks]
                embeddings = encode_batch(texts_to_embed)

                for chunk, embedding in zip(chunks, embeddings):
                    chunk.embedding = embedding

                # Step 7: Store in corpus
                progress.update(task, description=f"[green]Storing in corpus...[/green]")
                corpus.add_document(doc)

                for section in sections_dict.values():
                    corpus.add_section(section)

                corpus.add_chunks_batch(chunks)

                # Update corpus metadata
                corpus.set_meta('updated_at', datetime.utcnow().isoformat())

                progress.update(task, description=f"[green]Done: {file_path.name}[/green]")

            except Exception as e:
                progress.update(task, description=f"[red]Failed: {file_path.name} - {e}[/red]")
                console.print_exception()

    corpus.close()
    console.print(f"[green]Ingested {len(files_to_process)} document(s) into {corpus_path}[/green]")


# =============================================================================
# SEARCH COMMAND
# =============================================================================

@app.command()
def search(
    query: str,
    corpus_path: str = typer.Option(..., "--corpus", "-c", help="Path to corpus database"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
    semantic_type: Optional[str] = typer.Option(None, "--semantic-type", "-s", help="Filter by semantic type"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json"),
    include_content: bool = typer.Option(False, "--include-content", help="Include full content in JSON output"),
):
    """
    Search across a corpus using hybrid search (FTS + vector + RRF).
    """
    from .corpus.database import Corpus
    from .corpus.search import hybrid_search, expand_context

    corpus_file = Path(corpus_path)
    if not corpus_file.exists():
        typer.echo(f"Error: Corpus {corpus_path} not found")
        raise typer.Exit(code=1)

    corpus = Corpus(corpus_file)

    semantic_types = [semantic_type] if semantic_type else None
    results = hybrid_search(corpus, query, limit=limit, semantic_types=semantic_types)
    results = expand_context(corpus, results)

    if format == "json":
        output = []
        for r in results:
            item = {
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "document_name": r.document_name,
                "section_path": r.section_path,
                "section_title": r.section_title,
                "score": r.score,
                "semantic_type": r.semantic_type,
                "content_preview": r.content_preview,
            }
            if include_content:
                item["content"] = r.content
                item["section_summary"] = r.section_summary
            output.append(item)
        print(json.dumps(output, indent=2))
    else:
        table = Table(title=f"Search Results for: {query}")
        table.add_column("Score", style="green", justify="right", width=6)
        table.add_column("Document", style="cyan", max_width=20)
        table.add_column("Section", style="yellow", max_width=20)
        table.add_column("Preview", max_width=50)

        for r in results:
            table.add_row(
                f"{r.score:.3f}",
                r.document_name[:20],
                r.section_title[:20] if r.section_title else "-",
                r.content_preview[:50] + "...",
            )

        console.print(table)

    corpus.close()


# =============================================================================
# EXPORT COMMAND
# =============================================================================

@app.command()
def export(
    doc_id: str,
    corpus_path: str = typer.Option(..., "--corpus", "-c", help="Path to corpus database"),
    format: str = typer.Option("markdown", "--format", "-f", help="Export format: markdown, json"),
):
    """
    Export a document from the corpus.
    """
    from .corpus.database import Corpus

    corpus_file = Path(corpus_path)
    if not corpus_file.exists():
        typer.echo(f"Error: Corpus {corpus_path} not found")
        raise typer.Exit(code=1)

    corpus = Corpus(corpus_file)
    doc = corpus.get_document(doc_id)

    if not doc:
        typer.echo(f"Error: Document {doc_id} not found")
        corpus.close()
        raise typer.Exit(code=1)

    if format == "markdown":
        print(doc.raw_markdown)
    else:
        output = {
            "id": doc.id,
            "name": doc.name,
            "source_type": doc.source_type,
            "title": doc.title,
            "tags": doc.tags,
            "section_count": doc.section_count,
            "chunk_count": doc.chunk_count,
            "enriched": doc.enriched_at is not None,
            "raw_markdown": doc.raw_markdown,
        }
        print(json.dumps(output, indent=2))

    corpus.close()


def run() -> None:
    """CLI entry point that handles manifest-aware help output."""
    if _should_emit_manifest(sys.argv):
        _print_manifest()
        return
    app()


if __name__ == "__main__":
    run()
