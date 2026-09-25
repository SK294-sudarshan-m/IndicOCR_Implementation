"""PPTX and HTML."""

from __future__ import annotations

import make_fixtures as mf


def test_pptx_text_in_slide_order_and_picture_ocrd(process, engine):
    doc = process("deck.pptx")
    assert doc.status == "ok" and doc.format == "pptx"
    assert [(u.kind, u.origin, u.page) for u in doc.units] == [("page", "native", 1), ("image", "ocr", 1), ("page", "native", 2)]
    slide1 = doc.units[0].markdown
    assert slide1.index("## " + mf.EN_TITLE) < slide1.index(mf.HI_P2) < slide1.index("| Item | मद |")
    assert "| Rice | चावल |" in slide1 and doc.units[2].text == "End of deck"
    assert len(engine.calls) == 1 and "ppt/media/image1.png" in doc.units[1].name


def test_html_reads_visible_text_in_order_and_ocrs_local_images(process, engine):
    doc = process("page.html")
    assert doc.status == "ok" and doc.format == "html"
    assert [(u.kind, u.origin) for u in doc.units] == [("section", "native"), ("image", "ocr"), ("section", "native"), ("image", "ocr")]
    first = doc.units[0].markdown
    assert first.startswith("# Quarterly Report") and "var hidden" not in first  # scripts are not text
    assert mf.HI_P2 in first and "- one\n- दो" in first and "| Item | मद |" in first and "| Rice | चावल |" in first
    assert doc.units[2].text == "after the image"
    assert len(engine.calls) == 2  # the relative file and the data: URI
    assert any("remote image not fetched" in w for w in doc.warnings)
