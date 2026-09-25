from __future__ import annotations

import json

import pytest

from docpipe.config import parse_pages, select_pages
from docpipe.schema import DocumentResult, Unit


def test_native_unit_has_no_ocr_fields_and_ocr_unit_always_has_them():
    native = Unit(0, "section", "native", "why", text="t", markdown="m").to_dict()
    assert {"index", "kind", "origin", "reason", "text", "markdown", "warnings", "status"} <= set(native)
    assert not ({"render_dpi", "width_px", "height_px", "blocks"} & set(native))
    ocr = Unit(1, "image", "ocr", "why").to_dict()
    assert ocr["render_dpi"] is None and ocr["blocks"] == [] and "width_px" in ocr


def test_error_document_shape():
    doc = DocumentResult(source="input\\bad.pdf", status="error", error_type="PasswordProtected", message="PDF is encrypted; no text or images were read.")
    d = doc.to_dict()
    assert d["status"] == "error" and d["error_type"] == "PasswordProtected" and d["units"] == [] and d["unit_count"] == 0
    assert json.loads(doc.to_json())["source"] == "input\\bad.pdf"


def test_round_trip_keeps_unicode(tmp_path):
    doc = DocumentResult(source="हिंदी.txt", format="txt", units=[Unit(0, "section", "native", "r", text="नमस्ते", markdown="नमस्ते")])
    path = tmp_path / "d.json"
    path.write_bytes(doc.to_json().encode("utf-8"))
    assert "नमस्ते".encode() in path.read_bytes()
    assert DocumentResult.read(path).to_dict() == doc.to_dict()


def test_lone_surrogates_do_not_crash_the_writer(tmp_path):
    from docpipe.output import write_document

    doc = DocumentResult(source="x", format="json", units=[Unit(0, "section", "native", "r", text="a\ud800b", markdown="a\ud800b")])
    write_document(doc, tmp_path)
    assert json.loads((tmp_path / "document.json").read_text(encoding="utf-8"))["units"][0]["text"] == "a\ud800b"
    assert any("cannot be encoded" in w for w in doc.warnings)


@pytest.mark.parametrize(
    "spec, total, expected",
    [(None, 4, [1, 2, 3, 4]), ("2", 4, [2]), ("1-2,4", 4, [1, 2, 4]), ("3-", 5, [3, 4, 5]), ("2-9", 3, [2, 3]), ("7", 3, [])],
)
def test_page_selection(spec, total, expected):
    assert select_pages(spec, total) == expected


@pytest.mark.parametrize("spec", ["", "0", "3-1", "a", "1,,2", "1-b"])
def test_bad_page_specs_raise(spec):
    with pytest.raises(ValueError):
        parse_pages(spec)
