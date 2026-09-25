"""PNG / JPEG / TIFF / BMP / WEBP: normalised, written as a temporary PNG, OCR'd. One unit per frame."""

from __future__ import annotations

from pathlib import Path

from ..render import open_image, save_png
from ..schema import Unit
from .base import Context, ocr_unit


def extract(path: Path, ctx: Context) -> list[Unit]:
    units: list[Unit] = []
    for frame in open_image(path, ctx.opts, ctx.opts.pages):
        ctx.emit(f"frame {frame.index + 1}/{frame.total}")
        png = save_png(frame.image, ctx.workspace)
        try:
            units.append(
                ocr_unit(
                    ctx,
                    png,
                    kind="page" if frame.total > 1 else "image",
                    reason="image file (pixels only, no text layer)",
                    render_dpi=None,
                    page=frame.index + 1 if frame.total > 1 else None,
                )
            )
        finally:
            png.unlink(missing_ok=True)
    if not units:
        ctx.warnings.append(f"--pages {ctx.opts.pages!r} selected no frame of this image")
    return units
