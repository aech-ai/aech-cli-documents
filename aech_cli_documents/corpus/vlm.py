"""VLM-based document to markdown conversion.

This module provides pure VLM conversion:
Document → Images → VLM → Markdown

No text extraction hacks - full visual understanding.

Model configuration via environment variables:
- ANTHROPIC_API_KEY: API key for Anthropic
- VLM_MODEL: Model to use for vision tasks (required)
"""

import base64
import os
from pathlib import Path
from typing import Optional

import anthropic


def get_vlm_model() -> str:
    """Get VLM model from environment. Raises if not set."""
    model = os.environ.get("VLM_MODEL")
    if not model:
        raise ValueError(
            "VLM_MODEL environment variable not set. "
            "Set it in your .env file (e.g., VLM_MODEL=claude-sonnet-4-20250514)"
        )
    return model
from pdf2image import convert_from_path
from PIL import Image


# Prompt for markdown extraction
MARKDOWN_EXTRACTION_PROMPT = """Convert this document page to well-structured Markdown.

Instructions:
1. Preserve the document's hierarchical structure using appropriate header levels (# ## ### etc.)
2. Maintain all text content accurately
3. Format tables using Markdown table syntax
4. Describe images/figures in [brackets] if they contain meaningful content
5. Preserve lists (bullet points and numbered lists)
6. Keep any code blocks or technical content properly formatted
7. Maintain paragraph breaks and spacing

Output ONLY the Markdown content, no explanations or wrapper text."""

MULTI_PAGE_MERGE_PROMPT = """You are merging multiple pages of a document into a single coherent Markdown document.

The pages may have:
- Headers that should maintain consistent hierarchy across pages
- Tables that span pages (merge them)
- Lists that continue across pages (merge them)
- Section numbers that should be consistent

Merge these page contents into a single, well-structured Markdown document.
Fix any inconsistencies in header levels to maintain proper document hierarchy.
Remove any page break artifacts or repeated headers.

Output ONLY the merged Markdown content."""


def image_to_base64(image_path: Path) -> str:
    """Convert image file to base64 string."""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def pil_image_to_base64(image: Image.Image) -> str:
    """Convert PIL image to base64 string."""
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")


def get_media_type(image_path: Path) -> str:
    """Get MIME type for image."""
    suffix = image_path.suffix.lower()
    types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return types.get(suffix, "image/png")


def convert_page_to_markdown(
    client: anthropic.Anthropic,
    image_base64: str,
    media_type: str = "image/png",
    model: Optional[str] = None,
) -> str:
    """Convert a single page image to markdown using VLM."""
    model = model or get_vlm_model()
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": MARKDOWN_EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )
    return response.content[0].text


def merge_page_markdowns(
    client: anthropic.Anthropic,
    page_markdowns: list[str],
    model: Optional[str] = None,
) -> str:
    """Merge multiple page markdowns into a coherent document."""
    if len(page_markdowns) == 1:
        return page_markdowns[0]

    model = model or get_vlm_model()

    # For very long documents, merge in batches
    combined = "\n\n---PAGE BREAK---\n\n".join(
        f"## Page {i+1}\n\n{md}" for i, md in enumerate(page_markdowns)
    )

    response = client.messages.create(
        model=model,
        max_tokens=16384,
        messages=[
            {
                "role": "user",
                "content": f"{MULTI_PAGE_MERGE_PROMPT}\n\n{combined}",
            }
        ],
    )
    return response.content[0].text


def convert_to_markdown_vlm(
    input_path: Path,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    progress_callback: Optional[callable] = None,
) -> str:
    """
    Convert any document to Markdown using VLM.

    Args:
        input_path: Path to document (PDF, image, or office doc)
        model: Model to use (uses VLM_MODEL env var if not provided)
        api_key: API key (uses ANTHROPIC_API_KEY env var if not provided)
        progress_callback: Optional callback(current, total, message)

    Returns:
        Markdown string

    Environment Variables:
        VLM_MODEL: Required if model param not provided
        ANTHROPIC_API_KEY: Required if api_key param not provided
    """
    model = model or get_vlm_model()
    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    input_path = Path(input_path)
    suffix = input_path.suffix.lower()

    # Handle different input types
    if suffix == ".pdf":
        # Convert PDF to images
        if progress_callback:
            progress_callback(0, 1, "Converting PDF to images...")

        images = convert_from_path(str(input_path))

        if progress_callback:
            progress_callback(0, len(images), f"Processing {len(images)} pages...")

        # Convert each page to markdown
        page_markdowns = []
        for i, image in enumerate(images):
            if progress_callback:
                progress_callback(i, len(images), f"Processing page {i+1}/{len(images)}...")

            image_base64 = pil_image_to_base64(image)
            md = convert_page_to_markdown(client, image_base64, "image/png", model)
            page_markdowns.append(md)

        if progress_callback:
            progress_callback(len(images), len(images), "Merging pages...")

        # Merge pages
        return merge_page_markdowns(client, page_markdowns, model)

    elif suffix in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        # Single image
        if progress_callback:
            progress_callback(0, 1, "Processing image...")

        image_base64 = image_to_base64(input_path)
        media_type = get_media_type(input_path)
        result = convert_page_to_markdown(client, image_base64, media_type, model)

        if progress_callback:
            progress_callback(1, 1, "Done")

        return result

    elif suffix in [".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".odt", ".odp", ".ods"]:
        # Office documents - convert to PDF first, then process
        import subprocess
        import tempfile

        if progress_callback:
            progress_callback(0, 1, "Converting Office document to PDF...")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Convert to PDF using LibreOffice
            subprocess.run([
                "libreoffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", tmpdir,
                str(input_path)
            ], check=True, capture_output=True)

            pdf_path = Path(tmpdir) / (input_path.stem + ".pdf")

            if not pdf_path.exists():
                raise RuntimeError(f"Failed to convert {input_path} to PDF")

            # Recursively process the PDF
            return convert_to_markdown_vlm(
                pdf_path,
                model=model,
                api_key=api_key,
                progress_callback=progress_callback
            )

    elif suffix in [".md", ".markdown", ".txt"]:
        # Already text/markdown - just read it
        return input_path.read_text()

    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def convert_images_to_markdown(
    image_paths: list[Path],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    progress_callback: Optional[callable] = None,
) -> str:
    """
    Convert a list of images (e.g., from previous convert command) to Markdown.

    Args:
        image_paths: List of paths to images
        model: Model to use (uses VLM_MODEL env var if not provided)
        api_key: API key (uses ANTHROPIC_API_KEY env var if not provided)
        progress_callback: Optional callback(current, total, message)

    Returns:
        Markdown string
    """
    model = model or get_vlm_model()
    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    if progress_callback:
        progress_callback(0, len(image_paths), f"Processing {len(image_paths)} images...")

    page_markdowns = []
    for i, image_path in enumerate(sorted(image_paths)):
        if progress_callback:
            progress_callback(i, len(image_paths), f"Processing {image_path.name}...")

        image_base64 = image_to_base64(image_path)
        media_type = get_media_type(image_path)
        md = convert_page_to_markdown(client, image_base64, media_type, model)
        page_markdowns.append(md)

    if progress_callback:
        progress_callback(len(image_paths), len(image_paths), "Merging pages...")

    return merge_page_markdowns(client, page_markdowns, model)
