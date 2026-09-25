"""Options, defaults, and the pinned model coordinates."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .quality import Thresholds

ATTRIBUTION = "Built with IndicOCR from Bodhan AI / AI4Bharat."

# The tool imports Python files straight from the model directory, so the revision is pinned.
MODEL_REPO = "bodhan-ai/indic-ocr"
MODEL_REVISION = "cd50d301d0e17e8ecb32fc49c8ccbd7914dcfc25"
LAYOUT_WEIGHTS = "weights/layout/model.safetensors"
OCR_WEIGHTS = "weights/ocr/model-00001-of-00001.safetensors"
MODEL_CODE_FILES = (
    "idp_offline.py",
    "idp_recognizer.py",
    "idp_types.py",
    "idp_contract.py",
    "idp_layout.py",
    "idp_crops.py",
    "idp_blocks.py",
    "idp_reconstruct.py",
    "idp_model_infer.py",
    "idp_model_labels.py",
    "idp_model_order_loss.py",
    "idp_model_ppdoc.py",
)
DOWNLOAD_COMMAND = f"hf download {MODEL_REPO} {{file}} --revision {MODEL_REVISION} --local-dir {{model_dir}}"
LOGIN_STEP = (
    f"run `hf auth login` in your own terminal (the model is gated: accept the license on huggingface.co/{MODEL_REPO})"
)


@dataclass
class Options:
    dpi: int = 200  # measured in Phase 0: no accuracy gain above 150-200 dpi on the fixtures, ~40% slower at 300
    force_ocr: bool = False
    pages: str | None = None  # "1-5,8"; applies to PDF pages
    table_format: str = "html"
    device: str = "auto"
    dtype: str = "auto"
    model_dir: Path | None = None
    max_pixels: int = 100_000_000  # per image, and per rendered PDF page
    min_image_px: int = 32  # embedded images smaller than this on either side are skipped
    thresholds: Thresholds = field(default_factory=Thresholds)

    def resolved_model_dir(self) -> Path:
        return Path(self.model_dir) if self.model_dir else default_model_dir()


def default_model_dir() -> Path:
    """``DOCPIPE_MODEL_DIR``, else ``./models/indic-ocr``, else the copy beside the source tree."""
    env = os.environ.get("DOCPIPE_MODEL_DIR")
    if env:
        return Path(env)
    here = Path.cwd() / "models" / "indic-ocr"
    if here.is_dir():
        return here
    beside_source = Path(__file__).resolve().parents[2] / "models" / "indic-ocr"
    return beside_source if beside_source.is_dir() else here


def resolve_device(requested: str) -> str:
    if requested in ("cpu", "cuda"):
        return requested
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def resolve_dtype(requested: str, device: str) -> str:
    if requested != "auto":
        return requested
    # Phase 0, i5-1135G7: float32 recognizer 16.9 s vs bfloat16 27.9 s on the same page (no AVX512-BF16).
    return "bfloat16" if device == "cuda" else "float32"


def parse_pages(spec: str) -> list[tuple[int, int | None]]:
    """``"1-3,5,8-"`` -> [(1, 3), (5, 5), (8, None)]. Raises ValueError on malformed input."""
    ranges: list[tuple[int, int | None]] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            raise ValueError(f"empty item in --pages {spec!r}")
        lo_s, dash, hi_s = part.partition("-")
        try:
            lo = int(lo_s)
            hi = (int(hi_s) if hi_s else None) if dash else lo
        except ValueError:
            raise ValueError(f"cannot read {part!r} in --pages {spec!r}; use e.g. 1-5,8") from None
        if lo < 1 or (hi is not None and hi < lo):
            raise ValueError(f"invalid range {part!r} in --pages {spec!r}")
        ranges.append((lo, hi))
    return ranges


def select_pages(spec: str | None, total: int) -> list[int]:
    """1-based page numbers to process, in ascending order, clipped to ``total``."""
    if not spec:
        return list(range(1, total + 1))
    picked: set[int] = set()
    for lo, hi in parse_pages(spec):
        picked.update(range(lo, min(hi if hi is not None else total, total) + 1))
    return sorted(picked)
