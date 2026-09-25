"""PDF routing: text layer versus OCR, per page, with a recorded reason."""

from __future__ import annotations

import os

import pytest
from cer import normalize

from docpipe.render import Workspace


def _blocks_well_formed(unit) -> None:
    assert unit.blocks, "an OCR page keeps its detected blocks"
    assert [b["order"] for b in unit.blocks] == list(range(len(unit.blocks)))  # gap-free, 0-based
    for b in unit.blocks:
        assert {"order", "label", "type", "bbox_xyxy", "conf", "text"} <= set(b)
        x0, y0, x1, y1 = b["bbox_xyxy"]
        assert 0 <= x0 < x1 <= unit.width_px + 0.5 and 0 <= y0 < y1 <= unit.height_px + 0.5  # rendered-pixel coordinates
    assert any(b["text"] == "" for b in unit.blocks), "detected-but-not-read blocks are kept with text ''"


@pytest.mark.parametrize("name", ["en_born_digital.pdf", "hi_born_digital.pdf"])
def test_born_digital_pdfs_are_native_and_exact(process, engine, truth, name):
    doc = process(name)
    assert doc.status == "ok" and doc.format == "pdf"
    assert len(doc.units) == len(truth[name]["pages"])
    for unit, expected in zip(doc.units, truth[name]["pages"]):
        assert unit.origin == "native" and unit.kind == "page"
        assert unit.reason.startswith("text layer valid")
        assert normalize(unit.text) == normalize(expected)
        assert unit.page_width_pt == 595.0 and unit.page_height_pt == 842.0
        assert unit.text_layer["chars"] > 0
        assert unit.blocks is None and unit.render_dpi is None
    assert engine.calls == []


@pytest.mark.parametrize("name", ["en_image_only.pdf", "hi_image_only.pdf"])
def test_image_only_pdfs_take_the_ocr_path(process, engine, name):
    doc = process(name)
    assert doc.status == "ok"
    for n, unit in enumerate(doc.units, 1):
        assert unit.origin == "ocr" and unit.reason == "no text layer" and unit.page == n
        assert unit.render_dpi == 200
        assert (unit.width_px, unit.height_px) == (1653, 2339)  # A4 at 200 dpi
        assert unit.page_width_pt == 595.0
        _blocks_well_formed(unit)
    assert len(engine.calls) == len(doc.units)


@pytest.mark.parametrize(
    "name, reason_part",
    [
        ("hi_broken_pua.pdf", "private-use characters 100%"),
        ("hi_broken_legacy.pdf", "outside the supported scripts"),
        ("hi_shaped_mupdf.pdf", "combining marks detached from their base letter"),
    ],
)
def test_broken_text_layers_are_routed_to_ocr(process, engine, name, reason_part):
    doc = process(name)
    (unit,) = doc.units
    assert unit.origin == "ocr"
    assert unit.reason.startswith("text layer failed validity check (") and reason_part in unit.reason
    assert unit.text.startswith("FAKE OCR"), "the damaged text layer must not leak into the output"
    assert not any(0xE000 <= ord(c) <= 0xF8FF or c == "�" for c in unit.text + unit.markdown)
    assert unit.text_layer["chars"] > 0  # the metrics behind the decision are kept
    assert len(engine.calls) == 1


def test_per_page_routing_in_one_pdf(process, engine):
    doc = process("mixed_native_and_scan.pdf")
    assert [(u.page, u.origin) for u in doc.units] == [(1, "native"), (2, "ocr")]
    assert len(engine.calls) == 1


def test_searchable_scan_uses_its_text_layer_but_says_it_is_unverified(process, engine):
    doc = process("en_searchable_scan.pdf")
    first, second = doc.units
    assert first.origin == "native" and any("scanner's own OCR" in w for w in first.warnings)
    assert second.origin == "ocr"


def test_blank_page_is_native_and_says_so(process, engine):
    (unit,) = process("blank.pdf").units
    assert unit.origin == "native" and unit.reason == "blank page (no text, no images)" and unit.text == ""
    assert engine.calls == []


def test_force_ocr_overrides_a_good_text_layer(process, engine):
    doc = process("en_born_digital.pdf", force_ocr=True)
    assert [u.origin for u in doc.units] == ["ocr", "ocr"]
    assert all(u.reason == "OCR forced by --force-ocr" for u in doc.units)


def test_page_selection(process, engine):
    doc = process("en_born_digital.pdf", pages="2")
    assert [(u.index, u.page) for u in doc.units] == [(0, 2)]
    assert process("en_born_digital.pdf", pages="1-1,9").units[0].page == 1


def test_render_size_is_capped_by_lowering_dpi(process, engine):
    doc = process("en_born_digital.pdf", force_ocr=True, max_pixels=1_000_000, pages="1")
    (unit,) = doc.units
    assert unit.render_dpi < 200 and unit.width_px * unit.height_px <= 1_000_000
    assert any("render dpi lowered" in w for w in unit.warnings)


def test_normalised_pages_are_deleted_as_soon_as_they_are_read(process, engine):
    process("en_image_only.pdf")
    assert engine.calls and all(c["existed"] for c in engine.calls)
    assert not any(os.path.exists(c["path"]) for c in engine.calls)


@pytest.mark.parametrize(
    "name, error_type, needle",
    [
        ("encrypted.pdf", "PasswordProtected", "PDF is encrypted; no text or images were read."),
        ("corrupt.pdf", "CorruptFile", "not a readable PDF"),
        ("empty.pdf", "EmptyFile", "0 bytes"),
    ],
)
def test_unreadable_pdfs_become_error_records(process, name, error_type, needle):
    doc = process(name)
    assert doc.status == "error" and doc.error_type == error_type and needle in doc.message
    assert doc.units == []


def test_a_page_that_fails_is_reported_and_the_others_survive(process):
    from fakes import FakeEngine

    doc = process("en_image_only.pdf", eng=FakeEngine(fail_on={1}))
    assert doc.status == "partial"
    assert [u.status for u in doc.units] == ["error", "ok"]
    assert doc.units[0].error_type == "RuntimeError" and "simulated" in doc.units[0].message


def test_no_temp_directory_survives(process, tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    process("en_image_only.pdf")
    assert list(tmp_path.iterdir()) == []


def test_workspace_removes_its_directory_even_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    with pytest.raises(RuntimeError):
        with Workspace() as ws:
            (ws.path / "x.png").write_bytes(b"x")
            raise RuntimeError("boom")
    assert list(tmp_path.iterdir()) == []
