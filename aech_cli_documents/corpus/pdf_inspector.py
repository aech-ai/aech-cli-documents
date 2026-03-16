"""Integration helpers for Firecrawl's pdf-inspector CLI tools.

This module provides strict routing for PDF ingestion:
- detect-pdf classifies the PDF
- high-confidence text PDFs are extracted locally with pdf2md
- everything else is routed to the VLM/OCR pipeline

There are no silent fallbacks.
Missing binaries or invalid JSON fail loudly.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


LOCAL_EXTRACTION_ROUTE = "local_extraction"
VLM_ROUTE = "vlm"


@dataclass(frozen=True)
class PdfInspectorDetection:
    """Normalized classification output from `detect-pdf --json`."""

    pdf_type: str
    confidence: float
    ocr_recommended: bool
    page_count: int
    pages_needing_ocr: list[int]


@dataclass(frozen=True)
class PdfRoutingDecision:
    """Routing result for a single PDF."""

    route: Literal["local_extraction", "vlm"]
    reason: str
    detection: PdfInspectorDetection


def is_smart_pdf_routing_enabled() -> bool:
    """Return True when smart routing should be used for PDFs.

    AECH_PDF_ROUTING_MODE:
    - smart (default): use pdf-inspector-based routing
    - vlm_only: skip routing and force VLM path
    """
    mode = os.getenv("AECH_PDF_ROUTING_MODE", "smart").strip().lower()
    return mode not in {"vlm_only", "vlm", "disabled", "off", "false", "0"}


def get_min_confidence() -> float:
    """Get minimum confidence required for local extraction."""
    raw = os.getenv("AECH_PDF_INSPECTOR_MIN_CONFIDENCE", "0.90").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"AECH_PDF_INSPECTOR_MIN_CONFIDENCE must be a float, got {raw!r}"
        ) from exc
    if value < 0.0 or value > 1.0:
        raise ValueError(
            "AECH_PDF_INSPECTOR_MIN_CONFIDENCE must be between 0.0 and 1.0"
        )
    return value


def detect_pdf_with_inspector(pdf_path: Path) -> PdfInspectorDetection:
    """Run pdf-inspector classification and return normalized output."""
    detect_bin = os.getenv("AECH_PDF_INSPECTOR_DETECT_BIN", "detect-pdf").strip() or "detect-pdf"
    payload = _run_json_command([detect_bin, str(pdf_path.resolve()), "--json"])
    return _parse_detection_payload(payload)


def decide_pdf_route(
    detection: PdfInspectorDetection,
    min_confidence: float,
) -> PdfRoutingDecision:
    """Choose local extraction or VLM routing based on classification."""
    if (
        detection.pdf_type == "text_based"
        and not detection.ocr_recommended
        and detection.confidence >= min_confidence
    ):
        return PdfRoutingDecision(
            route=LOCAL_EXTRACTION_ROUTE,
            reason=f"text_based with confidence {detection.confidence:.2f} >= {min_confidence:.2f}",
            detection=detection,
        )

    if detection.pdf_type != "text_based":
        reason = f"pdf_type={detection.pdf_type}"
    elif detection.ocr_recommended:
        reason = "ocr_recommended=true"
    else:
        reason = f"confidence {detection.confidence:.2f} < {min_confidence:.2f}"

    return PdfRoutingDecision(
        route=VLM_ROUTE,
        reason=reason,
        detection=detection,
    )


def extract_markdown_with_inspector(pdf_path: Path) -> str:
    """Extract markdown with pdf-inspector's pdf2md binary."""
    pdf2md_bin = os.getenv("AECH_PDF_INSPECTOR_PDF2MD_BIN", "pdf2md").strip() or "pdf2md"
    payload = _run_json_command([pdf2md_bin, str(pdf_path.resolve()), "--json"])

    markdown = payload.get("markdown")
    if not isinstance(markdown, str):
        raise RuntimeError(
            "pdf2md JSON output did not include a string 'markdown' field."
        )
    if not markdown.strip():
        raise RuntimeError("pdf2md returned empty markdown output.")
    return markdown


def _parse_detection_payload(payload: dict[str, Any]) -> PdfInspectorDetection:
    """Validate/normalize detect-pdf JSON."""
    pdf_type = payload.get("pdf_type")
    confidence = payload.get("confidence")
    ocr_recommended = payload.get("ocr_recommended")
    page_count = payload.get("page_count")
    pages_needing_ocr = payload.get("pages_needing_ocr")

    if not isinstance(pdf_type, str):
        raise RuntimeError("detect-pdf JSON missing string field 'pdf_type'.")
    if not isinstance(confidence, (int, float)):
        raise RuntimeError("detect-pdf JSON missing numeric field 'confidence'.")
    if not isinstance(ocr_recommended, bool):
        raise RuntimeError("detect-pdf JSON missing boolean field 'ocr_recommended'.")
    if not isinstance(page_count, int):
        raise RuntimeError("detect-pdf JSON missing integer field 'page_count'.")
    if not isinstance(pages_needing_ocr, list) or not all(
        isinstance(page, int) for page in pages_needing_ocr
    ):
        raise RuntimeError(
            "detect-pdf JSON missing list[int] field 'pages_needing_ocr'."
        )

    return PdfInspectorDetection(
        pdf_type=pdf_type,
        confidence=float(confidence),
        ocr_recommended=ocr_recommended,
        page_count=page_count,
        pages_needing_ocr=pages_needing_ocr,
    )


def _run_json_command(cmd: list[str]) -> dict[str, Any]:
    """Run command, enforce success, parse JSON payload."""
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Required binary '{cmd[0]}' is not installed or not on PATH. "
            "Install pdf-inspector in the worker image via the aech-main uv manager."
        ) from exc

    if completed.returncode != 0:
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(cmd)}\n"
            f"stdout: {stdout}\n"
            f"stderr: {stderr}"
        )

    raw = completed.stdout.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Command did not return valid JSON: {' '.join(cmd)}\nraw: {raw}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Command JSON payload must be an object: {' '.join(cmd)}"
        )
    if "error" in payload:
        raise RuntimeError(f"Command reported error: {payload['error']}")

    return payload
