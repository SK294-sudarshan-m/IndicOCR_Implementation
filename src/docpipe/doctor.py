"""`docpipe doctor`: what is installed, what will run, and one concrete fix per problem."""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

from .config import LAYOUT_WEIGHTS, MODEL_REVISION, OCR_WEIGHTS, Options, resolve_device, resolve_dtype
from .model import Problem, model_dir_problems, package_version, runtime_problems


def _size(path: Path) -> str:
    return f"{path.stat().st_size / 2**20:,.0f} MB" if path.is_file() else "MISSING"


def run(opts: Options, out=None) -> int:
    out = out or sys.stdout
    say = lambda line="": print(line, file=out)  # noqa: E731
    model_dir = opts.resolved_model_dir()

    say(f"python         {platform.python_version()}  ({sys.executable})")
    for name in ("torch", "torchvision", "transformers", "accelerate", "PyMuPDF", "python-docx", "openpyxl", "lxml", "Pillow"):
        say(f"{name:<14} {package_version(name) or 'NOT INSTALLED'}")

    device = resolve_device(opts.device)
    say(f"device         {device}" + ("" if device == "cuda" else "  (no CUDA available or --device cpu)"))
    say(f"dtype          {resolve_dtype(opts.dtype, device)}")
    say(f"model dir      {model_dir}  (pinned revision {MODEL_REVISION[:7]})")
    say(f"layout weights {_size(model_dir / LAYOUT_WEIGHTS)}")
    say(f"OCR weights    {_size(model_dir / OCR_WEIGHTS)}")
    say(f"soffice        {shutil.which('soffice') or shutil.which('soffice.exe') or 'not found (legacy .doc/.xls/.ppt will be reported unsupported)'}")

    problems: list[Problem] = runtime_problems() + model_dir_problems(model_dir)
    say()
    if not problems:
        say("OK: OCR is ready.")
        return 0
    say(f"{len(problems)} problem(s):")
    for problem in problems:
        say(f"  - {problem.message}")
        say(f"    fix: {problem.fix}")
    return 1
