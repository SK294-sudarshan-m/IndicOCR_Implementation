"""The reference clone must stay exactly as it was.

Its `git status` was NOT clean before this project touched it (every tracked file staged as deleted, the same files
untracked, the OCR weight an LFS pointer with no file on disk: 65 lines). So "no changes" is checked as "identical to
the state recorded before any work began", plus HEAD unchanged.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

CLONE = Path(r"C:\Users\User\Desktop\IndicOCR_Huggingface\indic-ocr")
BASELINE_HEAD = "cd50d301d0e17e8ecb32fc49c8ccbd7914dcfc25"
BASELINE_STATUS_LINES = 65
BASELINE_STATUS_SHA256 = "b9d3ccdef7c359e9e784c6c217dd93498f3a1cd8f4a9c7e0b12f09452dfacee1"


def _git(*args: str) -> bytes:
    # --no-optional-locks: even `git status` may refresh .git/index otherwise
    return subprocess.run(["git", "--no-optional-locks", *args], cwd=CLONE, capture_output=True, check=True).stdout


@pytest.mark.skipif(not (CLONE / ".git").exists(), reason="reference clone not present on this machine")
def test_reference_clone_is_unchanged():
    assert _git("rev-parse", "HEAD").decode().strip() == BASELINE_HEAD
    status = _git("status", "--porcelain").replace(b"\r\n", b"\n")
    assert status.count(b"\n") == BASELINE_STATUS_LINES
    assert hashlib.sha256(status).hexdigest() == BASELINE_STATUS_SHA256
