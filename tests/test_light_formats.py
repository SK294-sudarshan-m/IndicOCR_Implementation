"""PPTX, HTML, Markdown and legacy Office: the 'should' formats."""

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


def test_markdown_passes_through_and_links_are_followed(process, engine):
    doc = process("notes.md")
    assert [(u.kind, u.origin) for u in doc.units] == [("section", "native"), ("image", "ocr"), ("section", "native")]
    assert doc.units[0].markdown.startswith("# Notes") and "`code`" in doc.units[0].markdown
    assert doc.units[2].text.strip() == "More text."
    assert len(engine.calls) == 1


def test_markdown_without_images_is_one_unit(process, fx):
    (fx / "plain.md").write_text("# Title\n\ntext ![x](https://example.com/a.png) more\n", encoding="utf-8")
    doc = process("plain.md")
    assert len(doc.units) == 1 and doc.units[0].markdown.startswith("# Title")
    assert any("remote image not fetched" in w for w in doc.warnings)


def test_legacy_office_needs_libreoffice(process, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    doc = process("legacy.doc")
    assert doc.status == "error" and doc.error_type == "UnsupportedFormat"
    assert "unsupported" in doc.message and "needs LibreOffice" in doc.message and ".docx" in doc.message
