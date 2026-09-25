"""File type by magic bytes and extension -> format name -> extractor."""

from __future__ import annotations

import importlib
import zipfile
from collections.abc import Callable
from pathlib import Path

from .errors import CorruptFile, EmptyFile, PasswordProtected, UnsupportedFormat

# format -> (module in docpipe.extractors, function). Imported on first use so a JSON run never loads PyMuPDF.
EXTRACTORS: dict[str, tuple[str, str]] = {
    "pdf": ("pdf", "extract"),
    "docx": ("docx", "extract"),
    "xlsx": ("xlsx", "extract"),
    "pptx": ("pptx", "extract"),
    "csv": ("csv_", "extract"),
    "json": ("json_", "extract"),
    "xml": ("xml_", "extract"),
    "txt": ("text", "extract"),
    "html": ("html", "extract"),
}

EXTENSIONS = {
    ".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx", ".csv": "csv", ".tsv": "csv",
    ".json": "json", ".xml": "xml", ".txt": "txt", ".html": "html", ".htm": "html",
}
_OFFICE_ZIP = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml", "pptx": "ppt/presentation.xml"}
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_TEXT_FORMATS = {"csv", "json", "xml", "txt", "html"}


def get_extractor(fmt: str) -> Callable:
    module, name = EXTRACTORS[fmt]
    return getattr(importlib.import_module(f"docpipe.extractors.{module}"), name)


def _office_kind(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
    except zipfile.BadZipFile as exc:
        raise CorruptFile(f"not a valid ZIP/Office container: {exc}") from None
    for fmt, member in _OFFICE_ZIP.items():
        if member in names:
            return fmt
    raise UnsupportedFormat("ZIP archives are not supported; extract them first")


def detect_format(path: Path) -> tuple[str, list[str]]:
    """Return (format, warnings). Raises EmptyFile, UnsupportedFormat, CorruptFile or PasswordProtected."""
    if path.stat().st_size == 0:
        raise EmptyFile("file is empty (0 bytes)")
    with open(path, "rb") as fh:
        head = fh.read(4096)
    by_ext = EXTENSIONS.get(path.suffix.lower())
    warnings: list[str] = []

    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        magic = _office_kind(path)
    elif b"%PDF-" in head[:1024]:
        magic = "pdf"
    elif head.startswith(_OLE):
        if by_ext in ("docx", "xlsx", "pptx"):
            raise PasswordProtected(
                f"{path.suffix} file is an OLE container, not OOXML: it is password-protected or a legacy binary "
                "file with the wrong extension; no content was read"
            )
        raise UnsupportedFormat("legacy Office (.doc/.xls/.ppt) files are not supported")
    else:
        magic = None

    if magic is not None:  # binary content identified: it wins over the extension
        if by_ext is not None and by_ext != magic:
            warnings.append(f"extension {path.suffix} says {by_ext} but the content is {magic}; treated as {magic}")
        return magic, warnings
    if by_ext in _TEXT_FORMATS:
        return by_ext, warnings
    if by_ext is not None:
        raise CorruptFile(f"content is not a valid {by_ext.upper()} (extension {path.suffix})")
    raise UnsupportedFormat(f"unsupported file type {path.suffix or '(no extension)'!r}")
