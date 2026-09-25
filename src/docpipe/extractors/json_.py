"""JSON: parsed, then pretty-printed with Unicode kept as characters (never \\uXXXX escapes)."""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import CorruptFile
from ..schema import Unit
from .base import Context, base64_image_warning, decode_text, fence


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def extract(path: Path, ctx: Context) -> list[Unit]:
    text, warnings = decode_text(path.read_bytes())
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise CorruptFile(f"invalid JSON: {exc}") from None
    pretty = json.dumps(data, ensure_ascii=False, indent=2)
    warning = base64_image_warning(_strings(data))
    if warning:
        warnings.append(warning)
    return [Unit(0, "section", "native", "JSON file, parsed and pretty-printed", text=pretty, markdown=fence(pretty, "json"), warnings=warnings)]
