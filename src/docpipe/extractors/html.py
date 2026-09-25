"""HTML: visible text as Markdown in document order; local and data: images are OCR'd where they appear."""

from __future__ import annotations

from pathlib import Path

from ..errors import CorruptFile
from ..schema import Unit
from .base import Context, fence, local_image_bytes, md_table, ocr_embedded_image

SKIP = {"script", "style", "noscript", "template", "head", "svg", "canvas"}
BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "aside", "nav", "figure", "figcaption",
         "blockquote", "address", "details", "summary", "form", "fieldset", "dl", "dt", "dd", "body", "html", "center"}


def _squash(text: str) -> str:
    return " ".join(text.split())


def _rows(table) -> list[list[str]]:
    return [[_squash(cell.text_content()) for cell in row if cell.tag in ("td", "th")] for row in table.iter("tr")]


def _walk(el, out: list[tuple[str, str]]) -> None:
    inline: list[str] = []

    def flush() -> None:
        text = _squash("".join(inline))
        inline.clear()
        if text:
            out.append(("text", text))

    inline.append(el.text or "")
    for child in el:
        tag = child.tag.lower() if isinstance(child.tag, str) else None
        if tag is None or tag in SKIP:
            pass
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            flush()
            out.append(("text", "#" * int(tag[1]) + " " + _squash(child.text_content())))
        elif tag == "table":
            flush()
            rows = [r for r in _rows(child) if any(r)]
            if rows:
                out.append(("text", md_table(rows)))
        elif tag in ("ul", "ol"):
            flush()
            marks = (lambda i: "- ") if tag == "ul" else (lambda i: f"{i}. ")
            items = [marks(i) + _squash(li.text_content()) for i, li in enumerate(child.iter("li"), 1)]
            out.append(("text", "\n".join(items)))
        elif tag == "pre":
            flush()
            out.append(("text", fence(child.text_content().strip("\n"))))
        elif tag == "img":
            flush()
            if child.get("src"):
                out.append(("image", child.get("src")))
        elif tag == "br":
            inline.append(" ")
        elif tag in BLOCK:
            flush()
            _walk(child, out)
        else:
            inline.append(child.text_content())
        inline.append(child.tail or "")
    flush()


def extract(path: Path, ctx: Context) -> list[Unit]:
    import lxml.html
    from lxml import etree

    try:
        root = lxml.html.document_fromstring(path.read_bytes())
    except (etree.ParserError, etree.XMLSyntaxError, ValueError) as exc:
        raise CorruptFile(f"HTML could not be parsed: {exc}") from None

    items: list[tuple[str, str]] = []
    _walk(root, items)
    title = _squash(root.findtext(".//title") or "")
    if title and not any(t.startswith("# ") for k, t in items if k == "text"):
        items.insert(0, ("text", f"# {title}"))

    units: list[Unit] = []
    blocks: list[str] = []

    def flush() -> None:
        if blocks:
            units.append(Unit(0, "section", "native", "HTML text, read directly", text="\n".join(blocks), markdown="\n\n".join(blocks)))
            blocks.clear()

    for kind, value in items:
        if kind == "text":
            blocks.append(value)
            continue
        blob = local_image_bytes(ctx, path.parent, value)
        if blob is None:
            continue
        flush()
        unit = ocr_embedded_image(ctx, blob, name=value[:60], reason=f"image in HTML ({value[:60]})")
        if unit is not None:
            units.append(unit)
    flush()
    return units
