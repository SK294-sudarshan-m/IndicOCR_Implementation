"""File type detection: magic bytes first, extension second."""

from __future__ import annotations

import shutil

import pytest

from docpipe.errors import CorruptFile, EmptyFile, PasswordProtected, UnsupportedFormat
from docpipe.router import EXTRACTORS, EXTENSIONS, detect_format


@pytest.mark.parametrize(
    "name, fmt",
    [
        ("en_born_digital.pdf", "pdf"),
        ("mixed.docx", "docx"), ("book.xlsx", "xlsx"), ("table.csv", "csv"), ("nested.json", "json"), ("note.xml", "xml"),
        ("plain.txt", "txt"),
    ],
)
def test_formats_are_detected(fx, name, fmt):
    assert detect_format(fx / name) == (fmt, [])


def test_every_extension_maps_to_an_extractor():
    assert set(EXTENSIONS.values()) <= set(EXTRACTORS)


def test_content_wins_over_a_wrong_extension(fx, tmp_path):
    workbook = tmp_path / "report.docx"
    shutil.copy(fx / "book.xlsx", workbook)
    fmt, warnings = detect_format(workbook)
    assert fmt == "xlsx" and "says docx but the content is xlsx" in warnings[0]


def test_bad_files_raise_specific_errors(fx, tmp_path):
    with pytest.raises(EmptyFile):
        detect_format(fx / "empty.txt")
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"just text")
    with pytest.raises(CorruptFile, match="not a valid PDF"):
        detect_format(fake)
    with pytest.raises(CorruptFile):
        detect_format(fx / "corrupt.docx")
    unknown = tmp_path / "data.bin"
    unknown.write_bytes(b"abc")
    with pytest.raises(UnsupportedFormat, match="unsupported file type '.bin'"):
        detect_format(unknown)


def test_zip_archives_and_password_protected_office_files(tmp_path):
    import zipfile

    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("a.txt", "hello")
    with pytest.raises(UnsupportedFormat, match="ZIP archives are not supported"):
        detect_format(archive)
    ole_as_docx = tmp_path / "locked.docx"
    ole_as_docx.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(600))
    with pytest.raises(PasswordProtected, match="password-protected"):
        detect_format(ole_as_docx)
