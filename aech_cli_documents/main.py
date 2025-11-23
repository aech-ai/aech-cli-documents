import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import typer
from pdf2image import convert_from_path
from PIL import Image

app = typer.Typer()


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
        # LibreOffice saves with same basename but .pdf extension
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
    
    # Determine file type
    suffix = input_file.suffix.lower()
    
    temp_pdf = None

    try:
        # 1. Handle Office Docs
        if suffix in ['.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', '.odt', '.odp', '.ods']:
            print(f"Converting Office document: {input_file}")
            temp_pdf = convert_office_to_pdf(input_file, out_path)
            if not temp_pdf:
                typer.echo("Failed to convert Office document to PDF.")
                raise typer.Exit(code=1)
            # Now treat as PDF
            input_file = temp_pdf
            suffix = '.pdf'

        # 2. Handle PDF
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

        # 3. Handle Images
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
        # Cleanup temp PDF if it was created from Office doc
        if temp_pdf and temp_pdf.exists():
            # We might want to keep it, but for now let's treat it as intermediate
            # Actually, keeping it might be useful. Let's leave it.
            pass

    # Output JSON list of images
    print(json.dumps({"images": images_created}))

def convert_office_to_docx(input_path: Path, output_dir: Path) -> Optional[Path]:
    """Converts legacy Office document to DOCX using LibreOffice."""
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        str(output_dir),
        str(input_path)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        # LibreOffice saves with same basename but .docx extension
        docx_path = output_dir / (input_path.stem + ".docx")
        if docx_path.exists():
            return docx_path
    except subprocess.CalledProcessError as e:
        print(f"Error converting office doc: {e}")
    return None

@app.command()
def convert_to_markdown(
    input_path: str,
    output_dir: str = typer.Option(..., "--output-dir", "-o", help="Directory to save output markdown")
):
    """
    Converts a document to Markdown using MarkItDown.
    """
    from markitdown import MarkItDown
    
    input_file = Path(input_path)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not input_file.exists():
        typer.echo(f"Error: File {input_path} not found.")
        raise typer.Exit(code=1)

    temp_docx = None
    try:
        # Handle legacy Office formats by converting to DOCX first
        suffix = input_file.suffix.lower()
        if suffix in ['.doc', '.ppt', '.xls', '.odt', '.odp', '.ods']:
             print(f"Converting legacy Office document to DOCX: {input_file}")
             temp_docx = convert_office_to_docx(input_file, out_path)
             if not temp_docx:
                 typer.echo("Failed to convert legacy Office document to DOCX.")
                 raise typer.Exit(code=1)
             input_file = temp_docx

        md = MarkItDown()
        result = md.convert(str(input_file))
        
        # Save to output file
        output_filename = Path(input_path).stem + ".md" # Use original stem
        output_file = out_path / output_filename
        output_file.write_text(result.text_content)
        
        print(json.dumps({"markdown_file": str(output_file)}))
        
    except Exception as e:
        typer.echo(f"Error converting to markdown: {e}")
        raise typer.Exit(code=1)
    finally:
        # Cleanup temp DOCX
        if temp_docx and temp_docx.exists():
            # Optional: remove temp file
            pass

def _run_pandoc(
    input_file: Path,
    output_file: Path,
    target_format: str,
    reference_doc: Optional[Path] = None,
    pdf_engine: Optional[str] = None,
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
    ]
    if reference_doc and target_format in {"docx", "pptx", "odt"}:
        cmd.extend(["--reference-doc", str(reference_doc)])
    if target_format == "pdf" and pdf_engine:
        cmd.extend(["--pdf-engine", pdf_engine])
    subprocess.run(cmd, check=True, capture_output=True)


@app.command("convert-markdown")
def convert_markdown(
    input_path: str,
    output_dir: str = typer.Option(..., "--output-dir", "-o", help="Directory for generated files"),
    formats: Optional[List[str]] = typer.Option(
        None,
        "--format",
        "-f",
        help="Pandoc output format(s). Repeat flag to request multiple (default: docx,pdf).",
    ),
    reference_doc: Optional[str] = typer.Option(
        None,
        "--reference-doc",
        help="Optional Pandoc reference document for Office outputs.",
    ),
    pdf_engine: Optional[str] = typer.Option(
        None,
        "--pdf-engine",
        help="Optional Pandoc PDF engine (e.g. xelatex).",
    ),
):
    """
    Use Pandoc to convert Markdown into standardized Office/PDF deliverables.
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
                pdf_engine=pdf_engine,
            )
            generated_files.append({"format": fmt, "path": str(output_file)})
    except subprocess.CalledProcessError as exc:
        typer.echo(f"Pandoc failed: {exc.stderr.decode().strip()}")
        raise typer.Exit(code=1)

    print(json.dumps({"files": generated_files}))

def run() -> None:
    """CLI entry point that handles manifest-aware help output."""

    if _should_emit_manifest(sys.argv):
        _print_manifest()
        return

    app()


if __name__ == "__main__":
    run()
