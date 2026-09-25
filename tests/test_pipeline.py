"""Batches: error isolation, output layout, folders, temp files."""

from __future__ import annotations

import hashlib
import json
import shutil

from fakes import FakeEngine

from docpipe.config import Options
from docpipe.pipeline import process_batch
from docpipe.schema import DocumentResult

BAD = {
    "corrupt.pdf": "CorruptFile",
    "empty.txt": "EmptyFile",
    "encrypted.pdf": "PasswordProtected",
    "corrupt.docx": "CorruptFile",
    "broken.json": "CorruptFile",
    "missing.pdf": "FileNotFound",
}


def test_bad_inputs_become_error_records_and_batch_continues(fx, tmp_path):
    engine = FakeEngine()
    names = [*BAD, "nested.json", "en_born_digital.pdf", "en_image_only.pdf"]  # good files come AFTER the bad ones
    batch = process_batch([fx / n for n in names], tmp_path / "out", Options(), engine=engine)

    assert [d.source for d, _ in batch.documents] == [str(fx / n) for n in names]
    by_name = {(fx / n).name: d for n, (d, _) in zip(names, batch.documents)}
    for name, error_type in BAD.items():
        doc = by_name[name]
        assert doc.status == "error" and doc.error_type == error_type, (name, doc.error_type, doc.message)
        assert doc.units == [] and doc.message
    assert by_name["nested.json"].status == "ok"
    assert by_name["en_born_digital.pdf"].status == "ok"
    assert by_name["en_image_only.pdf"].status == "ok" and len(engine.calls) == 2

    for doc, folder in batch.documents:  # every input, good or bad, gets both files
        assert (folder / "document.json").is_file() and (folder / "document.md").is_file()
        assert json.loads((folder / "document.json").read_text(encoding="utf-8"))["status"] == doc.status
    failed_md = (tmp_path / "out" / "encrypted.pdf" / "document.md").read_text(encoding="utf-8")
    assert "Processing failed" in failed_md and "PasswordProtected" in failed_md


def test_output_layout_and_json_contents(fx, tmp_path):
    batch = process_batch([fx / "mixed.docx", fx / "हिंदी_पाठ.txt"], tmp_path, Options(), engine=FakeEngine())
    folder = tmp_path / "mixed.docx"
    raw = (folder / "document.json").read_bytes()
    data = json.loads(raw.decode("utf-8"))
    assert list(data)[:5] == ["source", "sha256", "format", "status", "unit_count"]
    assert data["unit_count"] == len(data["units"]) == 3
    assert data["sha256"] == hashlib.sha256((fx / "mixed.docx").read_bytes()).hexdigest()
    assert data["format"] == "docx" and data["status"] == "ok"
    assert data["model_attribution"] == "Built with IndicOCR from Bodhan AI / AI4Bharat."
    assert {"total_seconds", "ocr_seconds", "model_load_seconds", "peak_rss_mb"} <= set(data["timings"])
    assert data["tool_versions"]["docpipe"] and data["tool_versions"]["python-docx"] and data["tool_versions"]["ocr_engine"]
    for unit in data["units"]:
        assert {"index", "kind", "origin", "reason", "text", "markdown", "warnings"} <= set(unit)
    ocr = data["units"][1]
    assert {"render_dpi", "width_px", "height_px", "blocks"} <= set(ocr)
    assert "blocks" not in data["units"][0]  # native units carry no OCR fields

    hindi_raw = (tmp_path / "हिंदी_पाठ.txt" / "document.json").read_bytes()
    assert "भारत की भाषाएँ".encode("utf-8") in hindi_raw and b"\\u0" not in hindi_raw  # UTF-8, not escapes
    md = (tmp_path / "हिंदी_पाठ.txt" / "document.md").read_text(encoding="utf-8")
    assert md.startswith("भारत की भाषाएँ")
    assert DocumentResult.read(folder / "document.json").to_dict() == data  # JSON round trip


def test_markdown_marks_units_only_when_there_are_several(fx, tmp_path):
    process_batch([fx / "mixed.docx", fx / "nested.json"], tmp_path, Options(), engine=FakeEngine())
    multi = (tmp_path / "mixed.docx" / "document.md").read_text(encoding="utf-8")
    assert "<!-- unit 0 | section | native -->" in multi and "<!-- unit 1 | image" in multi and "| ocr -->" in multi
    single = (tmp_path / "nested.json" / "document.md").read_text(encoding="utf-8")
    assert "<!--" not in single


def test_folder_input_recurses_mirrors_structure_and_skips_unsupported(fx, tmp_path):
    src = tmp_path / "input"
    (src / "sub").mkdir(parents=True)
    shutil.copy(fx / "nested.json", src / "a.json")
    shutil.copy(fx / "table.csv", src / "sub" / "b.csv")
    (src / "notes.bin").write_bytes(b"x")
    (src / "~$lock.docx").write_bytes(b"x")
    out = src / "out"  # output inside the input folder must not be ingested on a re-run
    for _ in range(2):
        batch = process_batch([src], out, Options(), engine=FakeEngine())
        assert sorted(d.source for d, _ in batch.documents) == sorted([str(src / "a.json"), str(src / "sub" / "b.csv")])
    assert (out / "a.json" / "document.json").is_file() and (out / "sub" / "b.csv" / "document.md").is_file()
    assert sorted(p.split("\\")[-1] for p in batch.skipped) == ["notes.bin", "~$lock.docx"]


def test_same_name_from_different_folders_does_not_overwrite(fx, tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    shutil.copy(fx / "nested.json", tmp_path / "x" / "same.json")
    shutil.copy(fx / "table.csv", tmp_path / "y" / "same.json")  # different content, same name
    batch = process_batch([tmp_path / "x" / "same.json", tmp_path / "y" / "same.json"], tmp_path / "out", Options(), engine=FakeEngine())
    assert [f.name for _, f in batch.documents] == ["same.json", "same.json-2"]
    assert any("same name" in w for w in batch.documents[1][0].warnings)


def test_temp_files_are_removed(fx, tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    names = ["en_image_only.pdf", "mixed.docx", "corrupt.pdf", "book_image.xlsx"]
    engine = FakeEngine(fail_on={2})
    process_batch([fx / n for n in names], tmp_path / "out", Options(), engine=engine)
    assert list((tmp_path / "tmp").iterdir()) == []


def test_engine_is_closed_only_when_the_batch_created_it(fx, tmp_path):
    engine = FakeEngine()
    process_batch([fx / "nested.json"], tmp_path, Options(), engine=engine)
    assert engine.closed is False  # caller-owned engine stays usable


def test_native_only_run_does_not_need_the_model(fx, tmp_path):
    """No engine injected and a model directory that does not exist: native formats must still work."""
    opts = Options(model_dir=tmp_path / "no-such-model-dir")
    batch = process_batch([fx / "nested.json", fx / "en_born_digital.pdf", fx / "book.xlsx"], tmp_path / "out", opts)
    assert [d.status for d, _ in batch.documents] == ["ok", "ok", "ok"]
    ocr_doc = process_batch([fx / "hi_image_only.pdf"], tmp_path / "out2", opts).documents[0][0]
    assert ocr_doc.status == "error" and ocr_doc.error_type == "ModelUnavailable"
    assert "model directory not found" in ocr_doc.message and "fix:" in ocr_doc.message


def test_model_load_failure_is_not_retried_for_every_page(fx, tmp_path, monkeypatch):
    import docpipe.model as model

    attempts = []
    real = model.model_dir_problems
    monkeypatch.setattr(model, "model_dir_problems", lambda *a, **k: attempts.append(1) or real(*a, **k))
    opts = Options(model_dir=tmp_path / "missing")
    engine = model.IndicOcrEngine(opts)
    doc = process_batch([fx / "en_image_only.pdf", fx / "hi_image_only.pdf"], tmp_path / "out", opts, engine=engine).documents[0][0]
    assert doc.status == "error" and doc.error_type == "ModelUnavailable"
    assert len(attempts) == 1, "two pages and a second document must reuse the first load failure"
