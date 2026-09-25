"""TXT: read as text, unchanged apart from LF line endings."""

from __future__ import annotations

from pathlib import Path

from ..schema import Unit
from .base import Context, decode_text


def extract(path: Path, ctx: Context) -> list[Unit]:
    text, warnings = decode_text(path.read_bytes())
    return [Unit(0, "section", "native", "plain text file, read directly", text=text, markdown=text, warnings=warnings)]
