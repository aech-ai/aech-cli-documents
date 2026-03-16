from __future__ import annotations

import subprocess

import pytest

from aech_cli_documents.corpus.pdf_inspector import (
    LOCAL_EXTRACTION_ROUTE,
    VLM_ROUTE,
    PdfInspectorDetection,
    _parse_detection_payload,
    _run_json_command,
    decide_pdf_route,
    get_min_confidence,
)


def test_decide_pdf_route_uses_local_extraction_for_high_confidence_text_pdf():
    detection = PdfInspectorDetection(
        pdf_type="text_based",
        confidence=0.97,
        ocr_recommended=False,
        page_count=5,
        pages_needing_ocr=[],
    )

    decision = decide_pdf_route(detection, min_confidence=0.90)

    assert decision.route == LOCAL_EXTRACTION_ROUTE
    assert "text_based" in decision.reason


def test_decide_pdf_route_uses_vlm_for_low_confidence_text_pdf():
    detection = PdfInspectorDetection(
        pdf_type="text_based",
        confidence=0.65,
        ocr_recommended=False,
        page_count=8,
        pages_needing_ocr=[3],
    )

    decision = decide_pdf_route(detection, min_confidence=0.90)

    assert decision.route == VLM_ROUTE
    assert "confidence" in decision.reason


def test_decide_pdf_route_uses_vlm_when_ocr_is_recommended():
    detection = PdfInspectorDetection(
        pdf_type="text_based",
        confidence=0.98,
        ocr_recommended=True,
        page_count=4,
        pages_needing_ocr=[2],
    )

    decision = decide_pdf_route(detection, min_confidence=0.90)

    assert decision.route == VLM_ROUTE
    assert decision.reason == "ocr_recommended=true"


def test_decide_pdf_route_uses_vlm_for_scanned_pdf():
    detection = PdfInspectorDetection(
        pdf_type="scanned",
        confidence=0.99,
        ocr_recommended=True,
        page_count=12,
        pages_needing_ocr=list(range(1, 13)),
    )

    decision = decide_pdf_route(detection, min_confidence=0.90)

    assert decision.route == VLM_ROUTE
    assert "pdf_type=scanned" == decision.reason


def test_parse_detection_payload_requires_expected_fields():
    with pytest.raises(RuntimeError, match="confidence"):
        _parse_detection_payload(
            {
                "pdf_type": "text_based",
                "ocr_recommended": False,
                "page_count": 2,
                "pages_needing_ocr": [],
            }
        )


def test_run_json_command_raises_when_binary_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="not installed"):
        _run_json_command(["detect-pdf", "doc.pdf", "--json"])


def test_get_min_confidence_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("AECH_PDF_INSPECTOR_MIN_CONFIDENCE", "1.5")

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        get_min_confidence()
