"""Model tier: the real IndicOCR weights on the generated fixtures. Slow on CPU: `pytest -m model`.

CER is measured against the ground truth written into make_fixtures.py. Exact OCR strings are never asserted.
The limits below come from the measured baseline (recorded in progress.txt) plus a margin; they are not to be
loosened to make a run pass: a failure means something in the pipeline changed (dpi, RGB/EXIF handling, order).
"""

from __future__ import annotations

import socket

import pytest
from cer import cer
from make_fixtures import EN_P2, HI_PAGE_TEXT, HI_SENTENCE

from docpipe.config import Options
from docpipe.model import IndicOcrEngine, model_dir_problems, runtime_problems
from docpipe.pipeline import process_document

pytestmark = pytest.mark.model

# Measured baseline + margin (see progress.txt). Clean synthetic fixtures: real scans will do worse.
LIMIT = {
    "en_image_only.pdf": 0.05,
    "hi_image_only.pdf": 0.05,
    "hi_broken_pua.pdf": 0.05,
    "hi_broken_legacy.pdf": 0.05,
    "hi_shaped_mupdf.pdf": 0.05,
    "hi_scan_degraded.pdf": 0.08,
    "docx_image": 0.05,
    "mixed_native_and_scan.pdf": 0.05,
}


def _skip_unless_model_ready() -> None:
    problems = model_dir_problems(Options().resolved_model_dir()) + runtime_problems()
    if problems:
        pytest.skip("; ".join(f"{p.message} ({p.fix})" for p in problems))


# Defined first on purpose: it builds its own engine and closes it, so two ~5 GB models never coexist.
def test_no_network_is_touched_while_loading_and_reading(fx, monkeypatch):
    """A fresh engine (so the weights load inside this test) must never open a socket."""
    _skip_unless_model_ready()

    def blocked(*args, **kwargs):
        raise AssertionError("network access attempted")

    for target in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, target, blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    engine = IndicOcrEngine(Options())
    try:
        doc = process_document(fx / "book_image.xlsx", "book_image.xlsx", Options(), engine)
    finally:
        engine.close()
    assert doc.status == "ok" and doc.units[1].origin == "ocr" and doc.units[1].status == "ok"


@pytest.fixture(scope="session")
def real_engine():
    _skip_unless_model_ready()
    engine = IndicOcrEngine(Options())
    yield engine
    engine.close()


def run(fx, real_engine, name, **overrides):
    return process_document(fx / name, name, Options(**overrides), real_engine)


def record(measurements, name, unit, expected, extra=""):
    value = cer(expected, unit.text)
    measurements.append(
        f"{name:<28} page={unit.page or '-'} origin={unit.origin} dpi={unit.render_dpi} {unit.seconds}s "
        f"blocks={len(unit.blocks or [])} CER={value:.4f} {extra}"
    )
    return value


@pytest.mark.parametrize("name", ["en_image_only.pdf", "hi_image_only.pdf"])
def test_image_only_pdfs_cer(fx, truth, real_engine, measurements, name):
    doc = run(fx, real_engine, name)
    assert doc.status == "ok"
    for unit, expected in zip(doc.units, truth[name]["pages"]):
        assert unit.origin == "ocr" and unit.reason == "no text layer"
        assert unit.blocks and unit.text.strip()
        assert record(measurements, name, unit, expected) < LIMIT[name]
    measurements.append(
        f"{name:<28} doc: total={doc.timings['total_seconds']}s ocr={doc.timings['ocr_seconds']}s "
        f"model_load={doc.timings['model_load_seconds']}s peakRSS={doc.timings['peak_rss_mb']}MB"
    )


@pytest.mark.parametrize("name", ["hi_broken_pua.pdf", "hi_broken_legacy.pdf", "hi_shaped_mupdf.pdf", "hi_scan_degraded.pdf"])
def test_broken_text_layer_pdfs_cer(fx, truth, real_engine, measurements, name):
    doc = run(fx, real_engine, name)
    (unit,) = doc.units
    assert unit.origin == "ocr"
    if name != "hi_scan_degraded.pdf":
        assert unit.reason.startswith("text layer failed validity check")
    assert record(measurements, name, unit, truth[name]["pages"][0], f"reason={unit.reason!r}") < LIMIT[name]


def test_mixed_pdf_native_page_and_ocr_page(fx, real_engine, measurements):
    doc = run(fx, real_engine, "mixed_native_and_scan.pdf")
    native, scanned = doc.units
    assert native.origin == "native" and scanned.origin == "ocr"
    assert record(measurements, "mixed_native_and_scan.pdf", scanned, EN_P2) < LIMIT["mixed_native_and_scan.pdf"]


def test_docx_embedded_image_cer(fx, real_engine, measurements):
    doc = run(fx, real_engine, "mixed.docx")
    assert [(u.kind, u.origin) for u in doc.units] == [("section", "native"), ("image", "ocr"), ("section", "native")]
    assert record(measurements, "mixed.docx (image)", doc.units[1], HI_SENTENCE) < LIMIT["docx_image"]
