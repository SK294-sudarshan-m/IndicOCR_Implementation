"""CSV/TSV: one table, one unit."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

from ..errors import CorruptFile
from ..schema import Unit
from .base import Context, decode_text, md_table


def extract(path: Path, ctx: Context) -> list[Unit]:
    text, warnings = decode_text(path.read_bytes())
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    if path.suffix.lower() == ".tsv":
        dialect = csv.excel_tab
    else:
        try:
            dialect = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
    try:
        rows = [row for row in csv.reader(io.StringIO(text, newline=""), dialect)]
    except csv.Error as exc:
        raise CorruptFile(f"invalid CSV: {exc}") from None
    while rows and not any(cell.strip() for cell in rows[-1]):
        rows.pop()
    delimiter = {"\t": "tab", ",": "comma", ";": "semicolon", "|": "pipe"}.get(dialect.delimiter, repr(dialect.delimiter))
    return [
        Unit(
            0,
            "sheet",
            "native",
            f"CSV file ({delimiter}-delimited, {len(rows)} rows), read directly",
            text="\n".join("\t".join(row) for row in rows),
            markdown=md_table(rows),
            warnings=warnings,
            name=path.stem,
        )
    ]
