"""Document-to-Markdown conversion.

This module provides:
- Smart PDF routing (pdf-inspector local extraction for text-based PDFs)
- VLM conversion path for scanned/mixed PDFs and non-PDF documents

Uses pydantic-ai for the VLM path with model configuration from
environment variables.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic_ai import Agent, BinaryContent

from pdf2image import convert_from_path
from PIL import Image

from .model_utils import parse_model_string, get_model_settings
from .pdf_inspector import (
    LOCAL_EXTRACTION_ROUTE,
    decide_pdf_route,
    detect_pdf_with_inspector,
    extract_markdown_with_inspector,
    get_min_confidence,
    is_smart_pdf_routing_enabled,
)


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


def _build_vlm_agent() -> Agent:
    """Build the pydantic-ai agent for VLM conversion."""
    model_string = os.getenv("VLM_MODEL", os.getenv("AECH_LLM_MODEL", "openai:gpt-4o"))
    model_name, _ = parse_model_string(model_string)
    model_settings = get_model_settings(model_string)

    return Agent(
        model_name,
        instructions=MARKDOWN_EXTRACTION_PROMPT,
        model_settings=model_settings,
    )


def _build_merge_agent() -> Agent:
    """Build the pydantic-ai agent for merging pages."""
    model_string = os.getenv("VLM_MODEL", os.getenv("AECH_LLM_MODEL", "openai:gpt-4o"))
    model_name, _ = parse_model_string(model_string)
    model_settings = get_model_settings(model_string)

    return Agent(
        model_name,
        instructions=MULTI_PAGE_MERGE_PROMPT,
        model_settings=model_settings,
    )


# Lazy-loaded agents
_vlm_agent: Agent | None = None
_merge_agent: Agent | None = None


def _get_vlm_agent() -> Agent:
    """Get or create the VLM agent."""
    global _vlm_agent
    if _vlm_agent is None:
        _vlm_agent = _build_vlm_agent()
    return _vlm_agent


def _get_merge_agent() -> Agent:
    """Get or create the merge agent."""
    global _merge_agent
    if _merge_agent is None:
        _merge_agent = _build_merge_agent()
    return _merge_agent


def image_to_bytes(image_path: Path) -> bytes:
    """Read image file as bytes."""
    with open(image_path, "rb") as f:
        return f.read()


def pil_image_to_bytes(image: Image.Image) -> bytes:
    """Convert PIL image to bytes."""
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


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


async def convert_page_to_markdown_async(image_bytes: bytes, media_type: str = "image/png") -> str:
    """Convert a single page image to markdown using VLM (async)."""
    agent = _get_vlm_agent()
    result = await agent.run(
        [
            "Convert this document page to well-structured Markdown.",
            BinaryContent(data=image_bytes, media_type=media_type),
        ]
    )
    return result.output


async def merge_page_markdowns_async(page_markdowns: list[str]) -> str:
    """Merge multiple page markdowns into a coherent document (async)."""
    if len(page_markdowns) == 1:
        return page_markdowns[0]

    agent = _get_merge_agent()

    combined = "\n\n---PAGE BREAK---\n\n".join(
        f"## Page {i+1}\n\n{md}" for i, md in enumerate(page_markdowns)
    )

    result = await agent.run(combined)
    return result.output


async def convert_to_markdown_vlm_async(
    input_path: Path,
    progress_callback: Optional[callable] = None,
) -> str:
    """
    Convert any document to Markdown using VLM (async).

    Args:
        input_path: Path to document (PDF, image, or office doc)
        progress_callback: Optional callback(current, total, message)

    Returns:
        Markdown string

    Environment Variables:
        VLM_MODEL or AECH_LLM_MODEL: Model to use for VLM conversion
    """
    input_path = Path(input_path)
    suffix = input_path.suffix.lower()

    # Handle different input types
    if suffix == ".pdf":
        if is_smart_pdf_routing_enabled():
            if progress_callback:
                progress_callback(0, 1, "Classifying PDF with pdf-inspector...")

            detection = detect_pdf_with_inspector(input_path)
            decision = decide_pdf_route(detection, get_min_confidence())

            if progress_callback:
                progress_callback(0, 1, f"Routing decision: {decision.route} ({decision.reason})")

            if decision.route == LOCAL_EXTRACTION_ROUTE:
                if progress_callback:
                    progress_callback(0, 1, "Extracting markdown locally with pdf-inspector...")

                markdown = extract_markdown_with_inspector(input_path)

                if progress_callback:
                    progress_callback(1, 1, "Done")
                return markdown

            if progress_callback:
                progress_callback(0, 1, "Routing to VLM pipeline...")

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

            image_bytes = pil_image_to_bytes(image)
            md = await convert_page_to_markdown_async(image_bytes, "image/png")
            page_markdowns.append(md)

        if progress_callback:
            progress_callback(len(images), len(images), "Merging pages...")

        # Merge pages
        return await merge_page_markdowns_async(page_markdowns)

    elif suffix in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        # Single image
        if progress_callback:
            progress_callback(0, 1, "Processing image...")

        image_bytes = image_to_bytes(input_path)
        media_type = get_media_type(input_path)
        result = await convert_page_to_markdown_async(image_bytes, media_type)

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
            return await convert_to_markdown_vlm_async(
                pdf_path,
                progress_callback=progress_callback
            )

    elif suffix in [".md", ".markdown", ".txt"]:
        # Already text/markdown - just read it
        return input_path.read_text()

    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def convert_to_markdown_vlm(
    input_path: Path,
    progress_callback: Optional[callable] = None,
    **kwargs,
) -> str:
    """
    Convert any document to Markdown using VLM (sync wrapper).

    Args:
        input_path: Path to document (PDF, image, or office doc)
        progress_callback: Optional callback(current, total, message)
        **kwargs: Ignored (for backward compatibility)

    Returns:
        Markdown string
    """
    import asyncio

    return asyncio.get_event_loop().run_until_complete(
        convert_to_markdown_vlm_async(input_path, progress_callback)
    )


async def convert_images_to_markdown_async(
    image_paths: list[Path],
    progress_callback: Optional[callable] = None,
) -> str:
    """
    Convert a list of images to Markdown (async).

    Args:
        image_paths: List of paths to images
        progress_callback: Optional callback(current, total, message)

    Returns:
        Markdown string
    """
    if progress_callback:
        progress_callback(0, len(image_paths), f"Processing {len(image_paths)} images...")

    page_markdowns = []
    for i, image_path in enumerate(sorted(image_paths)):
        if progress_callback:
            progress_callback(i, len(image_paths), f"Processing {image_path.name}...")

        image_bytes = image_to_bytes(image_path)
        media_type = get_media_type(image_path)
        md = await convert_page_to_markdown_async(image_bytes, media_type)
        page_markdowns.append(md)

    if progress_callback:
        progress_callback(len(image_paths), len(image_paths), "Merging pages...")

    return await merge_page_markdowns_async(page_markdowns)


def convert_images_to_markdown(
    image_paths: list[Path],
    progress_callback: Optional[callable] = None,
    **kwargs,
) -> str:
    """
    Convert a list of images to Markdown (sync wrapper).

    Args:
        image_paths: List of paths to images
        progress_callback: Optional callback(current, total, message)
        **kwargs: Ignored (for backward compatibility)

    Returns:
        Markdown string
    """
    import asyncio

    return asyncio.get_event_loop().run_until_complete(
        convert_images_to_markdown_async(image_paths, progress_callback)
    )
