"""TXT, CSV, JSON, XML: native, Unicode exact, no OCR."""

from __future__ import annotations

import json

import make_fixtures as mf


def test_json_pretty_printed_with_unicode_kept(process, engine, fx):
    doc = process("nested.json")
    assert doc.status == "ok" and doc.format == "json"
    (unit,) = doc.units
    assert unit.origin == "native" and unit.kind == "section"
    assert "नाम" in unit.text and "दिल्ली" in unit.text and "🙂" in unit.text and "日本語" in unit.text
    assert "\\u" not in unit.text  # never \uXXXX escapes
    assert unit.markdown.startswith("```json\n") and unit.markdown.rstrip().endswith("```")
    assert json.loads(unit.text) == json.loads((fx / "nested.json").read_text(encoding="utf-8"))
    assert engine.calls == []


def test_xml_pretty_printed_with_unicode_kept(process):
    doc = process("note.xml")
    (unit,) = doc.units
    assert unit.origin == "native"
    assert "<नोट" in unit.text and "नमस्ते दुनिया" in unit.text and "यह एक परीक्षण है।" in unit.text
    assert unit.markdown.startswith("```xml\n")
    assert "\n  <शीर्षक>" in unit.text  # indented, i.e. pretty-printed


def test_csv_becomes_a_markdown_table(process):
    doc = process("table.csv")
    (unit,) = doc.units
    assert unit.kind == "sheet" and unit.origin == "native"
    lines = unit.markdown.splitlines()
    assert lines[0] == "| नाम | शहर | टिप्पणी |"  # UTF-8 BOM stripped
    assert lines[2] == "| राम | दिल्ली | पहली, दूसरी |"
    assert "two<br>lines" in unit.markdown  # a newline inside a quoted field
    assert 'a "quoted" word' in unit.markdown and "x\\|y" in unit.markdown
    assert unit.text.splitlines()[1].split("\t") == ["राम", "दिल्ली", "पहली, दूसरी"]


def test_txt_hindi_filename_and_content(process):
    doc = process("हिंदी_पाठ.txt")
    (unit,) = doc.units
    assert doc.source == "हिंदी_पाठ.txt"
    assert unit.text == f"{mf.HI_TITLE}\n{mf.HI_P1}\n"
    assert doc.format == "txt"


def test_txt_line_endings_normalised(process):
    assert process("plain.txt").units[0].text == "first line\nsecond line\n"


def test_txt_not_utf8_falls_back_with_a_warning(process):
    doc = process("latin1_note.txt")
    (unit,) = doc.units
    assert unit.text == "café au lait"
    assert any("Windows-1252" in w for w in unit.warnings)


def test_invalid_json_and_xml_are_errors(process):
    for name, needle in (("broken.json", "invalid JSON"), ("broken.xml", "invalid XML")):
        doc = process(name)
        assert doc.status == "error" and doc.error_type == "CorruptFile" and needle in doc.message
        assert doc.units == []
