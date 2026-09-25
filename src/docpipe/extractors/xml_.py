"""XML: parsed without resolving entities or touching the network, then pretty-printed."""

from __future__ import annotations

from pathlib import Path

from ..errors import CorruptFile
from ..schema import Unit
from .base import Context, base64_image_warning, fence


def extract(path: Path, ctx: Context) -> list[Unit]:
    from lxml import etree

    # Documents are the user's own but may still be hostile: no entity expansion, no DTD loading, no network.
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False, remove_blank_text=True)
    try:
        tree = etree.parse(str(path), parser)
    except etree.XMLSyntaxError as exc:
        raise CorruptFile(f"invalid XML: {exc}") from None
    pretty = etree.tostring(tree, pretty_print=True, encoding="unicode").rstrip("\n")
    warnings = []
    warning = base64_image_warning(t for el in tree.iter() for t in (el.text, *el.attrib.values()))
    if warning:
        warnings.append(warning)
    return [Unit(0, "section", "native", "XML file, parsed and pretty-printed", text=pretty, markdown=fence(pretty, "xml"), warnings=warnings)]
