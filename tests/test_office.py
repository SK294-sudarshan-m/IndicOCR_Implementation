"""DOCX and XLSX: native text and tables, embedded images OCR'd in place."""

from __future__ import annotations

import make_fixtures as mf


def test_xlsx_one_unit_per_sheet(process, engine):
    doc = process("book.xlsx")
    assert doc.status == "ok" and doc.format == "xlsx"
    assert [(u.kind, u.origin, u.name) for u in doc.units] == [("sheet", "native", "Sales"), ("sheet", "native", "हिंदी")]
    sales, hindi = doc.units
    rows = [line.split("\t") for line in sales.text.splitlines()]
    assert rows[0] == ["Item", "Qty", "Price", "Total"]
    assert rows[1] == ["Rice", "5", "40", "200"]  # cached formula value, not "=B2*C2"
    assert rows[2] == ["Tea", "12", "10", "120"]
    assert rows[3] == ["", "", "Sum", ""]  # never calculated: empty, and reported
    assert any("1 formula cell(s) have no cached value" in w and "D4" in w for w in sales.warnings)
    assert [line.split("\t") for line in hindi.text.splitlines()] == [["नाम", "शहर"], ["राम", "दिल्ली"], ["सीता", "मुंबई"]]
    assert "| नाम | शहर |" in hindi.markdown and hindi.markdown.startswith("## हिंदी")
    assert engine.calls == []


def test_xlsx_embedded_image_is_ocrd(process, engine):
    doc = process("book_image.xlsx")
    assert [(u.kind, u.origin) for u in doc.units] == [("sheet", "native"), ("image", "ocr")]
    image = doc.units[1]
    assert len(engine.calls) == 1 and engine.calls[0]["mode"] == "RGB"
    assert image.render_dpi is None and image.width_px and image.height_px
    assert "Scan" in image.reason and "row 3, column 1" in image.reason


def test_docx_document_order(process, engine):
    doc = process("mixed.docx")
    assert doc.status == "ok" and doc.format == "docx"
    assert [(u.kind, u.origin) for u in doc.units] == [("section", "native"), ("image", "ocr"), ("section", "native")]
    assert [u.index for u in doc.units] == [0, 1, 2]

    before, image, after = doc.units
    md = before.markdown
    positions = [md.index(s) for s in ("# " + mf.EN_TITLE, mf.EN_P1, mf.HI_P2, "| Item | मद | Qty |", "| Rice | चावल | 5 |", "| Tea | चाय | 12 |", "Scanned sentence follows:")]
    assert positions == sorted(positions), "paragraphs and table must appear in document order"
    assert after.markdown.strip() == "End of document."

    assert len(engine.calls) == 1
    assert engine.calls[0]["mode"] == "RGB" and engine.calls[0]["existed"]
    assert image.text == "FAKE OCR 1"
    assert [b["text"] for b in image.blocks] == ["", "FAKE OCR 1", ""]  # skipped blocks stay, with text ""
    assert "word/media/" in image.name


def test_docx_keeps_unicode_paragraph_exact(process):
    doc = process("mixed.docx")
    assert mf.HI_P2 in doc.units[0].text


def test_tiny_embedded_images_are_skipped_with_a_note(process, engine):
    doc = process("book_image.xlsx", min_image_px=100_000)
    assert [u.kind for u in doc.units] == ["sheet"]
    assert engine.calls == [] and any("skipped" in w for w in doc.warnings)
