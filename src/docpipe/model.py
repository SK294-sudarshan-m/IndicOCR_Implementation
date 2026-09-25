"""Lazy wrapper around IndicOCR (layout stage + recognizer stage), plus the checks ``doctor`` reuses.

Nothing here imports torch or transformers until the first OCR unit needs them. The IndicOCR Python files are
imported from the model directory (pinned revision, see config.MODEL_REVISION).
"""

from __future__ import annotations

import gc
import importlib.metadata as metadata
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .config import (
    DOWNLOAD_COMMAND,
    LAYOUT_WEIGHTS,
    LOGIN_STEP,
    MODEL_CODE_FILES,
    MODEL_REVISION,
    OCR_WEIGHTS,
    Options,
    resolve_device,
    resolve_dtype,
)
from .errors import ModelUnavailable


@dataclass
class OcrPage:
    """One page as IndicOCR returns it. ``blocks`` are its block records, unchanged."""

    width: int
    height: int
    blocks: list[dict]
    markdown: str
    warnings: list[str] = field(default_factory=list)


class OcrEngine(Protocol):
    def recognize(self, image_path: str) -> OcrPage: ...

    def info(self) -> dict: ...

    def close(self) -> None: ...


@dataclass
class Problem:
    message: str
    fix: str


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _major_minor(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("+")[0].split(".")[:2] if p.isdigit())


def model_dir_problems(model_dir: Path, code_only: bool = False) -> list[Problem]:
    problems: list[Problem] = []
    if not model_dir.is_dir():
        problems.append(
            Problem(
                f"model directory not found: {model_dir}",
                f"copy the IndicOCR repo files (without .git) into {model_dir}, or pass --model-dir / set DOCPIPE_MODEL_DIR",
            )
        )
        return problems
    missing = [f for f in MODEL_CODE_FILES if not (model_dir / f).is_file()]
    if missing:
        problems.append(
            Problem(
                f"IndicOCR code files missing in {model_dir}: {', '.join(missing)}",
                f"copy the repo files at revision {MODEL_REVISION[:7]} into {model_dir}",
            )
        )
    if code_only:
        return problems
    for label, weight in (("layout", LAYOUT_WEIGHTS), ("OCR", OCR_WEIGHTS)):
        path = model_dir / weight
        download = DOWNLOAD_COMMAND.format(file=weight, model_dir=model_dir)
        if not path.is_file():
            problems.append(Problem(f"{label} weights missing: {path}", f"{LOGIN_STEP}, then: {download}"))
    ocr = model_dir / OCR_WEIGHTS
    expected = _expected_ocr_bytes(model_dir)
    if ocr.is_file() and expected and ocr.stat().st_size < expected:
        problems.append(
            Problem(
                f"OCR weights look truncated ({ocr.stat().st_size} bytes, expected at least {expected})",
                f"delete {ocr}, then: {DOWNLOAD_COMMAND.format(file=OCR_WEIGHTS, model_dir=model_dir)}",
            )
        )
    return problems


def _expected_ocr_bytes(model_dir: Path) -> int | None:
    import json

    try:
        index = json.loads((model_dir / "weights" / "ocr" / "model.safetensors.index.json").read_text("utf-8"))
        return int(index["metadata"]["total_size"])
    except (OSError, KeyError, ValueError):
        return None


def runtime_problems() -> list[Problem]:
    """Versions IndicOCR needs (its own import check requires torch>=2.4 and transformers>=5.7)."""
    problems: list[Problem] = []
    install = "pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu"
    torch_v, tv_v = package_version("torch"), package_version("torchvision")
    if torch_v is None:
        problems.append(Problem("torch is not installed", install))
    elif _major_minor(torch_v) < (2, 4):
        problems.append(Problem(f"torch {torch_v} is too old (need >=2.4)", install))
    if tv_v is None:
        problems.append(Problem("torchvision is not installed (the recognizer's image processor needs it)", install))
    tf_v = package_version("transformers")
    if tf_v is None or _major_minor(tf_v) < (5, 7):
        problems.append(
            Problem(f"transformers {tf_v or 'missing'} (need >=5.7)", 'pip install "transformers>=5.7"')
        )
    if package_version("accelerate") is None:
        problems.append(Problem("accelerate is not installed (device_map loading needs it)", 'pip install "accelerate>=1.1"'))
    return problems


def _quiet_environment() -> None:
    # Processing must never touch the network, and the checkpoints are local.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


class IndicOcrEngine:
    """Both IndicOCR stages behind one call. Loads on the first ``recognize``; loading is never retried
    after it failed. ``layout_backend`` / ``recognizer_backend`` inject fakes (no torch, no weights)."""

    def __init__(self, options: Options, layout_backend=None, recognizer_backend=None) -> None:
        self.opts = options
        self._layout_backend = layout_backend
        self._recognizer_backend = recognizer_backend
        self._layout = None
        self._ocr = None
        self._load_error: ModelUnavailable | None = None
        self._device = self._dtype = None
        self._truncated = 0
        self._max_tokens = 0
        self.load_seconds = 0.0
        self.status = lambda message: None  # the CLI points this at stderr so a 10+ s load is not silent

    @property
    def injected(self) -> bool:
        return self._layout_backend is not None and self._recognizer_backend is not None

    def _load(self) -> None:
        if self._ocr is not None:
            return
        if self._load_error is not None:
            raise self._load_error
        started = time.perf_counter()
        self.status("loading IndicOCR (first OCR page in this run)")
        try:
            self._load_unchecked()
        except ModelUnavailable as exc:
            self._load_error = exc
            raise
        finally:
            self.load_seconds += time.perf_counter() - started

    def _load_unchecked(self) -> None:
        model_dir = self.opts.resolved_model_dir()
        problems = model_dir_problems(model_dir, code_only=self.injected)
        if not self.injected:
            problems += runtime_problems()
        if problems:
            raise ModelUnavailable("; ".join(f"{p.message} (fix: {p.fix})" for p in problems))

        _quiet_environment()
        if str(model_dir) not in sys.path:
            sys.path.insert(0, str(model_dir))
        try:
            from idp_contract import TableFormat
            from idp_offline import IndicBlockOCR, IndicDocLayout
            from idp_types import LayoutConfig, RecognizerConfig
        except ImportError as exc:
            raise ModelUnavailable(f"cannot import IndicOCR from {model_dir}: {exc}") from exc

        self._device = "cpu" if self.injected else resolve_device(self.opts.device)
        self._dtype = resolve_dtype(self.opts.dtype, self._device)
        rec_cfg = RecognizerConfig(dtype=self._dtype, table_format=TableFormat(self.opts.table_format))

        if self.injected:
            self._layout = IndicDocLayout(backend=self._layout_backend)
            self._ocr = IndicBlockOCR(backend=self._recognizer_backend, config=rec_cfg)
            return

        try:
            import torch
            from idp_recognizer import HfRecognizer

            if self.opts.deterministic:
                torch.manual_seed(0)
                torch.use_deterministic_algorithms(True, warn_only=True)

            self._layout = IndicDocLayout(
                str(model_dir / "weights" / "layout"), LayoutConfig(device=self._device)
            )
            backend = HfRecognizer(str(model_dir / "weights" / "ocr"), rec_cfg, device=self._device)
        except Exception as exc:  # torch / transformers raise many types on a bad install or checkpoint
            self._layout = None
            raise ModelUnavailable(f"IndicOCR failed to load: {type(exc).__name__}: {exc}") from exc
        self._watch_truncation(backend, rec_cfg.max_tokens)
        self._ocr = IndicBlockOCR(backend=backend, config=rec_cfg)

    def _watch_truncation(self, backend, max_tokens: int) -> None:
        """HfRecognizer returns text only, so a block cut off at max_new_tokens is otherwise invisible.
        A row that finished contains an EOS or pad token after its text; one that hit the cap does not."""
        try:
            original = backend.model.generate
            stop_ids = {backend.eos_token_id, backend.pad_token_id}
        except AttributeError:
            return

        def generate(*args, **kwargs):
            out = original(*args, **kwargs)
            prompt_len = kwargs["input_ids"].shape[-1]
            for row in out[:, prompt_len:].tolist():
                if not stop_ids.intersection(row):
                    self._truncated += 1
            return out

        backend.model.generate = generate
        self._max_tokens = max_tokens

    def recognize(self, image_path: str) -> OcrPage:
        self._load()
        self._truncated = 0
        layout = self._layout.detect(image_path)
        page = self._ocr.run(image_path, layout)
        warnings = []
        if self._truncated:
            warnings.append(
                f"{self._truncated} block(s) reached the {self._max_tokens}-token limit; their text may be cut off"
            )
        return OcrPage(page.width, page.height, page.as_record()["blocks"], page.markdown or "", warnings)

    def info(self) -> dict:
        if self.injected:
            return {"engine": "injected test backends"}
        return {
            "device": self._device,
            "dtype": self._dtype,
            "model_dir": str(self.opts.resolved_model_dir()),
            "model_revision": MODEL_REVISION,
            "torch": package_version("torch"),
            "transformers": package_version("transformers"),
        }

    def close(self) -> None:
        for stage in (self._ocr, self._layout):
            if stage is not None:
                stage.close()
        self._ocr = self._layout = None
        gc.collect()
