import typer
import subprocess
import shutil
import os
from pathlib import Path
from typing import List, Optional
from pdf2image import convert_from_path
from PIL import Image

app = typer.Typer()

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
    import json
    print(json.dumps({"images": images_created}))

if __name__ == "__main__":
    app()
