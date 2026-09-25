"""File type detection: magic bytes first, extension second."""

from __future__ import annotations

import shutil

import pytest

from docpipe.errors import CorruptFile, EmptyFile, PasswordProtected, UnsupportedFormat
from docpipe.router import EXTRACTORS, EXTENSIONS, detect_format


@pytest.mark.parametrize(
    "name, fmt",
    [
        ("en_born_digital.pdf", "pdf"), ("hi_page.png", "png"), ("hi_photo_exif.jpg", "jpeg"), ("en_two_pages.tif", "tiff"),
        ("mixed.docx", "docx"), ("book.xlsx", "xlsx"), ("notes.md", "md"), ("legacy.doc", "doc"),
    ],
)
def test_formats_are_detected(fx, name, fmt):
    assert detect_format(fx / name) == (fmt, [])


def test_every_extension_maps_to_an_extractor():
    assert set(EXTENSIONS.values()) <= set(EXTRACTORS)


def test_content_wins_over_a_wrong_extension(fx, tmp_path):
    misnamed = tmp_path / "photo.png"
    shutil.copy(fx / "hi_photo_exif.jpg", misnamed)
    fmt, warnings = detect_format(misnamed)
    assert fmt == "jpeg" and "extension .png says png but the content is jpeg" in warnings[0]
    workbook = tmp_path / "report.docx"
    shutil.copy(fx / "book.xlsx", workbook)
    assert detect_format(workbook)[0] == "xlsx"


def test_bad_files_raise_specific_errors(fx, tmp_path):
    with pytest.raises(EmptyFile):
        detect_format(fx / "empty.txt")
    with pytest.raises(CorruptFile, match="not a valid PNG"):
        detect_format(fx / "fake.png")
    with pytest.raises(CorruptFile):
        detect_format(fx / "corrupt.docx")
    unknown = tmp_path / "data.bin"
    unknown.write_bytes(b"abc")
    with pytest.raises(UnsupportedFormat, match="unsupported file type '.bin'"):
        detect_format(unknown)
    mail = tmp_path / "x.eml"
    mail.write_bytes(b"From: a@b\n")
    with pytest.raises(UnsupportedFormat, match="containers are not supported"):
        detect_format(mail)


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
